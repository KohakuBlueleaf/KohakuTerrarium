"""Per-session filesystem + history helpers for the persistence layer.

Filesystem and per-store operations live here so HTTP and programmatic
surfaces share one implementation. Listing, search, and aggregation belong to
the session-index sidecar; this module handles resolution, file enumeration,
deletion, history, and disk usage for individual sessions.
"""

import gc
import json
import os
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from kohakuterrarium.session.history import (
    dedupe_adjacent_duplicate_events,
    normalize_resumable_events,
)
from kohakuterrarium.session.store import SessionStore, iter_kv_keys
from kohakuterrarium.session.store_lock import acquire_writer_lock, release_writer_lock
from kohakuterrarium.studio.persistence.delete_family import (
    detach_file_family,
    remove_detached_family,
)
from kohakuterrarium.studio.persistence.session_index import (
    get_session_index_default,
)
from kohakuterrarium.studio.persistence.viewer.paths import (
    all_session_files,
    all_versions_for_session,
    normalize_session_stem,
    pick_canonical_per_session,
    resolve_session_path,
)
from kohakuterrarium.utils import drive_migration_lock
from kohakuterrarium.utils.config_dir import config_dir
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

# Explicit session directories avoid this process-wide default when callers
# require namespace isolation. Tests also replace the default directly.
_SESSION_DIR = Path.home() / ".kohakuterrarium" / "sessions"


def _session_dir() -> Path:
    """Return the session directory shared by persistence and lifecycle APIs.

    ``KT_SESSION_DIR`` has highest precedence. A replaced module default is
    honored next; otherwise the configured application directory is used.
    Values are read on every call so environment and test overrides remain
    live.
    """
    env = os.environ.get("KT_SESSION_DIR")
    if env:
        return Path(env)
    # A replaced module default takes precedence; otherwise deriving from
    # ``config_dir`` keeps configuration-directory overrides isolated.
    _docs_default = Path.home() / ".kohakuterrarium" / "sessions"
    if _SESSION_DIR != _docs_default:
        return _SESSION_DIR
    return config_dir() / "sessions"


def all_session_files_default() -> list[Path]:
    """Return every supported session file under the default directory."""
    return all_session_files(_session_dir())


def _empty_disk_usage(session_dir: Path) -> dict[str, Any]:
    """Return the disk-usage shape for a directory with nothing measurable."""
    return {
        "count": 0,
        "session_bytes": 0,
        "artifacts_bytes": 0,
        "total_bytes": 0,
        "oldest_at": None,
        "newest_at": None,
        "session_dir": str(session_dir),
    }


def disk_usage() -> dict[str, Any]:
    """Return session and retained-artifact byte usage separately.

    Session bytes include SQLite ``-wal`` and ``-shm`` sidecars without opening
    any database. Artifact bytes include every direct ``*.artifacts`` directory,
    including media intentionally retained after its session was deleted.
    Timestamps come from canonical session files only.
    """
    session_dir = _session_dir()
    if not session_dir.exists():
        return _empty_disk_usage(session_dir)

    try:
        canonical = pick_canonical_per_session(session_dir)
    except OSError as exc:
        logger.warning(
            "session directory scan failed; reporting empty usage",
            path=str(session_dir),
            error=str(exc),
            exc_info=True,
        )
        return _empty_disk_usage(session_dir)
    session_bytes = 0
    oldest: float | None = None
    newest: float | None = None
    for path in canonical:
        try:
            st = path.stat()
        except OSError:
            continue
        session_bytes += st.st_size
        if oldest is None or st.st_mtime < oldest:
            oldest = st.st_mtime
        if newest is None or st.st_mtime > newest:
            newest = st.st_mtime
        # Sidecars are part of the session's observable disk footprint.
        for suffix in ("-wal", "-shm"):
            sidecar = str(path) + suffix
            if not os.path.exists(sidecar):
                continue
            try:
                session_bytes += os.stat(sidecar).st_size
            except OSError:
                continue

    artifacts_bytes = _artifacts_disk_usage(session_dir)

    return {
        "count": len(canonical),
        "session_bytes": session_bytes,
        "artifacts_bytes": artifacts_bytes,
        "total_bytes": session_bytes + artifacts_bytes,
        "oldest_at": oldest,
        "newest_at": newest,
        "session_dir": str(session_dir),
    }


def _artifacts_disk_usage(session_dir: Path) -> int:
    """Sum regular files below direct ``*.artifacts`` session companions."""
    total = 0
    for artifacts_dir in session_dir.glob("*.artifacts"):
        try:
            is_dir = artifacts_dir.is_dir()
        except OSError:
            continue
        if not is_dir:
            continue
        for root, _dirs, files in os.walk(artifacts_dir, followlinks=False):
            for filename in files:
                try:
                    total += os.stat(
                        Path(root) / filename, follow_symlinks=False
                    ).st_size
                except OSError:
                    continue
    return total


def resolve_session_path_default(session_name: str) -> Path | None:
    """Resolve ``session_name`` against the default ``_SESSION_DIR``."""
    return resolve_session_path(session_name, _session_dir())


def resolve_session_path_in(session_name: str, session_dir: Path) -> Path | None:
    """Resolve ``session_name`` against an explicit ``session_dir``.

    The saved-session Drive viewer resolves inside the authenticated user's L4
    namespace (R1-01); it must never fall back to the process-global directory,
    so this takes the directory explicitly rather than reading the module global.
    """
    return resolve_session_path(session_name, session_dir)


def all_versions_for_session_default(session_name: str) -> list[Path]:
    """Every file belonging to the given session (v1 + v2 rollback pair)."""
    return all_versions_for_session(session_name, _session_dir())


def session_targets(store: SessionStore, meta: dict[str, Any]) -> list[str]:
    """Return ordered history targets from metadata or storage discovery.

    Metadata-listed agents and channels are authoritative when present.
    Sessions without those records fall back to event and conversation keys.
    """
    targets: list[str] = []
    seen: set[str] = set()

    for target in meta.get("agents", []):
        if target and target not in seen:
            seen.add(target)
            targets.append(target)

    for ch in meta.get("terrarium_channels", []):
        name = ch.get("name", "")
        target = f"ch:{name}" if name else ""
        if target and target not in seen:
            seen.add(target)
            targets.append(target)

    if targets:
        return targets

    for key, _evt in store.get_all_events():
        if ":e" not in key:
            continue
        target = key.split(":e", 1)[0]
        if target and target not in seen:
            seen.add(target)
            targets.append(target)

    for key_bytes in store.conversation.keys(limit=2**31 - 1):
        target = key_bytes.decode() if isinstance(key_bytes, bytes) else key_bytes
        if target and target not in seen:
            seen.add(target)
            targets.append(target)

    return targets


def session_history_payload(
    store: SessionStore,
    target: str,
    *,
    live_job_ids: set[str] | None = None,
    limit: int = 0,
    before: int | None = None,
) -> dict[str, Any]:
    """Return history for an agent, root, or channel target.

    ``live_job_ids`` identifies work still running in a live session so it is
    not synthesized as interrupted. Saved-session callers omit it because any
    unfinished persisted job is no longer active.

    ``limit`` bounds the payload: with ``limit > 0`` only the most recent
    page (at most ``limit`` events or ``DEFAULT_HISTORY_PAGE_BYTES`` of
    event JSON, whichever fills first) is read from the store. ``before``
    is an exclusive pagination cursor — an ``event_id`` for agent targets,
    the per-channel message sequence for ``ch:`` targets — so the page
    contains only events strictly older than it. The default ``limit=0``
    keeps the full unbounded payload for programmatic callers; the HTTP
    route supplies its own bounded default. Pages after the newest one
    omit the conversation snapshot: it describes the whole conversation
    and belongs to the newest window, so re-sending it per page would
    duplicate megabytes.

    Every response carries ``has_more``, ``oldest_event_id``, and ``total``
    so clients can page backwards without gaps or overlap. ``total`` counts
    stored events for the target; the rendered count can differ slightly
    after adjacent-duplicate collapse and normalization.
    """
    if limit and limit > 0:
        if target.startswith("ch:"):
            return _paged_channel_events(store, target[3:], limit=limit, before=before)
        return _paged_agent_events(
            store, target, limit=limit, before=before, live_job_ids=live_job_ids
        )

    if target.startswith("ch:"):
        channel = target[3:]
        messages = store.get_channel_messages(channel)
        events = [
            {
                "type": "channel_message",
                "channel": channel,
                "sender": m.get("sender", ""),
                "content": m.get("content", ""),
                "ts": m.get("ts", 0),
            }
            for m in messages
        ]
        return {
            "target": target,
            "messages": [],
            "events": events,
            "has_more": False,
            "oldest_event_id": None,
            "total": len(events),
        }

    resumable = getattr(store, "get_resumable_events", None)
    if resumable is not None:
        events = resumable(target, live_job_ids=live_job_ids)
    else:
        events = store.get_events(target)
    events = list(events)
    return {
        "target": target,
        "messages": store.load_conversation(target) or [],
        "events": events,
        "has_more": False,
        "oldest_event_id": _event_id_of(events[0]) if events else None,
        "total": len(events),
    }


# Pagination bounds shared by every history page: at most
# ``DEFAULT_HISTORY_PAGE_LIMIT`` events AND at most this byte budget of
# serialized event JSON — whichever fills first ends the page.
DEFAULT_HISTORY_PAGE_LIMIT = 400
DEFAULT_HISTORY_PAGE_BYTES = 4 * 1024 * 1024


def _event_id_of(evt: Any) -> int | None:
    """Extract the session-global ``event_id`` from a raw event value."""
    if isinstance(evt, dict):
        eid = evt.get("event_id")
        if isinstance(eid, int):
            return eid
    return None


def _read_event(store: SessionStore, key: Any) -> dict | None:
    """Read one raw event value, logging instead of raising on failure."""
    try:
        evt = store.events[key]
    except Exception as e:
        logger.warning("Failed to read event", error=str(e), exc_info=True)
        return None
    return evt if isinstance(evt, dict) else None


def _cursor_position(store: SessionStore, keys: list[Any], before: int) -> int:
    """Count events strictly older than cursor ``before`` (page end index).

    Binary search over key positions with one value read per probe —
    ``O(log n)`` value reads instead of scanning the whole log. Per-agent
    ``event_id`` grows with key order by construction (both are assigned
    together in ``append_event``); mirrored events with imported
    identifiers are the documented exception and may shift a boundary by
    their displacement.
    """
    lo, hi = 0, len(keys)
    while lo < hi:
        mid = (lo + hi) // 2
        eid = _event_id_of(_read_event(store, keys[mid]))
        if eid is not None and eid < before:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _page_slice(
    store: SessionStore,
    keys: list[Any],
    *,
    end: int,
    limit: int,
    read: Callable[[SessionStore, Any], dict | None],
) -> tuple[list[Any], int]:
    """Walk a page backwards from ``end``, honoring both page bounds.

    Returns the page's ``(values oldest-first, start_index)``. Reading stops
    after ``limit`` values or once the serialized byte budget is exhausted;
    at least one value is always read so paging always makes progress. An
    unreadable value is skipped without consuming the budget.
    """
    values: list[Any] = []
    budget = DEFAULT_HISTORY_PAGE_BYTES
    start = end
    while start > 0 and len(values) < limit:
        start -= 1
        value = read(store, keys[start])
        if value is None:
            continue
        values.append(value)
        budget -= len(json.dumps(value, default=str))
        if budget <= 0:
            break
    values.reverse()
    return values, start


def _paged_agent_events(
    store: SessionStore,
    target: str,
    *,
    limit: int,
    before: int | None,
    live_job_ids: set[str] | None,
) -> dict[str, Any]:
    """Build one bounded page of a target's events (oldest-first).

    Only page values are read: keys are enumerated and sliced first, so the
    store work stays bounded regardless of log size. Cursor metadata comes
    from the RAW page (before dedupe/normalization) so pages stay anchored
    to real store events and cannot skip or repeat rows.
    """
    store.flush()
    keys = sorted(iter_kv_keys(store.events, prefix=f"{target}:e"))
    end = len(keys) if before is None else _cursor_position(store, keys, before)
    values, start = _page_slice(store, keys, end=end, limit=limit, read=_read_event)
    oldest = _event_id_of(values[0]) if values else None
    events = normalize_resumable_events(
        dedupe_adjacent_duplicate_events(values), live_job_ids=live_job_ids
    )
    messages: list[dict[str, Any]] = []
    if before is None:
        messages = store.load_conversation(target) or []
    return {
        "target": target,
        "messages": messages,
        "events": events,
        "has_more": start > 0 and oldest is not None,
        "oldest_event_id": oldest,
        "total": len(keys),
    }


def _channel_message_seq(key: Any) -> int | None:
    """Decode the per-channel sequence from a ``<channel>:mNNNNNN`` key."""
    text = key.decode() if isinstance(key, bytes) else key
    if not isinstance(text, str) or ":m" not in text:
        return None
    try:
        return int(text.rsplit(":m", 1)[1])
    except (IndexError, ValueError):
        return None


def _read_channel_message(store: SessionStore, key: Any) -> dict | None:
    """Read one raw channel message value, logging instead of raising."""
    try:
        message = store.channels[key]
    except Exception as e:
        logger.warning("Failed to read channel message", error=str(e), exc_info=True)
        return None
    return message if isinstance(message, dict) else None


def _paged_channel_events(
    store: SessionStore,
    channel: str,
    *,
    limit: int,
    before: int | None,
) -> dict[str, Any]:
    """Build one bounded page of channel messages (oldest-first).

    Channel messages carry no ``event_id``; the cursor is the per-channel
    message sequence decoded from the key, so cursor positioning needs no
    value reads at all.
    """
    store.channels.flush_cache()
    keys = sorted(iter_kv_keys(store.channels, prefix=f"{channel}:m"))
    if before is None:
        end = len(keys)
    else:
        end = sum(
            1
            for key in keys
            if (seq := _channel_message_seq(key)) is not None and seq < before
        )
    values, start = _page_slice(
        store, keys, end=end, limit=limit, read=_read_channel_message
    )
    oldest = _channel_message_seq(keys[start]) if values else None
    events = [
        {
            "type": "channel_message",
            "channel": channel,
            "sender": m.get("sender", ""),
            "content": m.get("content", ""),
            "ts": m.get("ts", 0),
        }
        for m in values
    ]
    return {
        "target": f"ch:{channel}",
        "messages": [],
        "events": events,
        "has_more": start > 0 and oldest is not None,
        "oldest_event_id": oldest,
        "total": len(keys),
    }


def _unlink_with_retry(path: Path, attempts: int = 5, base_delay: float = 0.05) -> None:
    """Unlink a file, retrying transient Windows handle contention.

    Native store handles can outlive ``SessionStore.close`` briefly while
    refcount-driven cleanup finishes. Exponential backoff gives those handles
    time to close; persistent permission failures are re-raised after the
    bounded retry window. POSIX normally succeeds on the first attempt.
    """
    last_exc: OSError | None = None
    for i in range(attempts):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError as e:
            last_exc = e
            # Collection can release refcount-owned native SQLite handles
            # before the next attempt.
            gc.collect()
            time.sleep(base_delay * (2**i))
    assert last_exc is not None
    raise last_exc


def _sidecars_for(path: Path) -> list[Path]:
    """Return existing ``-wal`` / ``-shm`` sidecars for a SQLite file."""
    out: list[Path] = []
    for suffix in ("-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            out.append(sidecar)
    return out


def _drive_sidecars_for(path: Path) -> list[Path]:
    """Return deletable Drive sidecars paired with a session database.

    The persistent ``.drives.migrate-lock`` is excluded because replacing its
    inode would allow processes to hold mutually ineffective locks.
    """
    return [
        candidate
        for suffix in (".drives", ".drives-wal", ".drives-shm")
        if (candidate := path.with_name(path.name + suffix)).exists()
    ]


def delete_session_files(session_name: str) -> list[Path]:
    """Delete a session file family and return the removed paths.

    Legacy raw stems use fuzzy resolution. An empty result means no matching
    session exists. Index entries are purged immediately so list and stats
    views do not retain deleted sessions until reconciliation.
    """
    targets = all_versions_for_session_default(session_name)
    if not targets:
        resolved = resolve_session_path_default(session_name)
        if resolved is not None:
            targets = all_versions_for_session_default(normalize_session_stem(resolved))
            if not targets:
                targets = [resolved]

    if not targets:
        return []

    # Holding every writer and Drive migration lock before inspection makes
    # deletion atomic with sidecar publication. Bounded acquisition fails before
    # any removal when an active migration remains busy.
    with ExitStack() as guards:
        for path in sorted(targets, key=str):
            lock = acquire_writer_lock(str(path))
            guards.callback(release_writer_lock, lock)
        for path in sorted(targets, key=str):
            guards.enter_context(drive_migration_lock.drive_migration_guard(path))

        family = []
        for path in targets:
            family.extend([path, *_sidecars_for(path), *_drive_sidecars_for(path)])
            family.extend(path.parent.glob(f"{path.name}.drives.split-intent.json*"))
        detached = detach_file_family(family)
        deleted = remove_detached_family(detached, _unlink_with_retry)

    _purge_index_entries(targets)
    return deleted


def _purge_index_entries(deleted_paths: list[Path]) -> None:
    """Best-effort removal of deleted filenames from the session index.

    Index failure cannot undo file deletion; reconciliation later removes any
    stale entries left behind.
    """
    try:
        session_dir = _session_dir()
        index = get_session_index_default(session_dir)
        for path in deleted_paths:
            index.delete(path.name)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning(
            "session-index purge after delete failed", error=str(exc), exc_info=True
        )

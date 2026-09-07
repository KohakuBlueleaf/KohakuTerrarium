"""Bounded, cursor-paged history reads shared by saved and live layers.

The paging primitives (sorted-key enumeration, exclusive-cursor binary
search, dual event-count/byte page budget) live here in the session tier so
the studio persistence payloads AND the terrarium live creature history page
through one implementation — the terrarium tier must not import studio, and
both tiers already depend on ``kohakuterrarium.session``. Cursor semantics
are therefore identical on every surface: an ``event_id`` cursor for agent
targets, the per-channel message sequence for ``ch:`` targets.

A page reads at most ``DEFAULT_HISTORY_PAGE_LIMIT`` events or
``DEFAULT_HISTORY_PAGE_BYTES`` of serialized event JSON, whichever fills
first. Only page values are read: keys are enumerated and sliced first, so
the store work stays bounded regardless of log size.
"""

import json
from collections.abc import Callable
from typing import Any

from kohakuterrarium.session.history import (
    dedupe_adjacent_duplicate_events,
    normalize_resumable_events,
    normalize_tool_call_events,
)
from kohakuterrarium.session.store import SessionStore, iter_kv_keys
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

# Pagination bounds shared by every history page: at most
# ``DEFAULT_HISTORY_PAGE_LIMIT`` events AND at most this byte budget of
# serialized event JSON — whichever fills first ends the page.
DEFAULT_HISTORY_PAGE_LIMIT = 400
DEFAULT_HISTORY_PAGE_BYTES = 4 * 1024 * 1024


def event_id_of(evt: Any) -> int | None:
    """Extract the session-global ``event_id`` from a raw event value."""
    if isinstance(evt, dict):
        eid = evt.get("event_id")
        if isinstance(eid, int):
            return eid
    return None


def read_event(store: SessionStore, key: Any) -> dict | None:
    """Read one raw event value, logging instead of raising on failure."""
    try:
        evt = store.events[key]
    except Exception as e:
        logger.warning("Failed to read event", error=str(e), exc_info=True)
        return None
    return evt if isinstance(evt, dict) else None


def cursor_position(store: SessionStore, keys: list[Any], before: int) -> int:
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
        eid = event_id_of(read_event(store, keys[mid]))
        if eid is not None and eid < before:
            lo = mid + 1
        else:
            hi = mid
    return lo


def page_slice(
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


def paged_agent_events(
    store: SessionStore,
    target: str,
    *,
    limit: int,
    before: int | None,
    live_job_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build one bounded page of a target's events (oldest-first).

    Only page values are read: keys are enumerated and sliced first, so the
    store work stays bounded regardless of log size. Cursor metadata comes
    from the RAW page (before dedupe/normalization) so pages stay anchored
    to real store events and cannot skip or repeat rows.

    ``live_job_ids`` keeps in-flight work from being synthesized as
    interrupted on the newest page. Older pages (``before`` set) skip the
    interrupt synthesis entirely — see the boundary note below.
    """
    store.flush()
    keys = sorted(iter_kv_keys(store.events, prefix=f"{target}:e"))
    end = len(keys) if before is None else cursor_position(store, keys, before)
    values, start = page_slice(store, keys, end=end, limit=limit, read=read_event)
    oldest = event_id_of(values[0]) if values else None
    events = dedupe_adjacent_duplicate_events(values)
    if before is None:
        events = normalize_resumable_events(events, live_job_ids=live_job_ids)
    else:
        # PAGE-BOUNDARY TRADEOFF: an older page must not synthesize
        # "Interrupted by session resume" terminals. A page boundary can
        # split a tool_call/tool_result pair whose real result lives in a
        # NEWER page the client may already have rendered — synthesizing
        # here would fabricate an interrupt bubble that then coexists with
        # the genuine result. The cost: a job that genuinely died long ago
        # renders on older pages without its terminal marker until that
        # page is the newest window. Announcement repair is kept so replay
        # pairing still works.
        events = normalize_tool_call_events(events)
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


def channel_message_seq(key: Any) -> int | None:
    """Decode the per-channel sequence from a ``<channel>:mNNNNNN`` key."""
    text = key.decode() if isinstance(key, bytes) else key
    if not isinstance(text, str) or ":m" not in text:
        return None
    try:
        return int(text.rsplit(":m", 1)[1])
    except (IndexError, ValueError):
        return None


def read_channel_message(store: SessionStore, key: Any) -> dict | None:
    """Read one raw channel message value, logging instead of raising."""
    try:
        message = store.channels[key]
    except Exception as e:
        logger.warning("Failed to read channel message", error=str(e), exc_info=True)
        return None
    return message if isinstance(message, dict) else None


def paged_channel_events(
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
            if (seq := channel_message_seq(key)) is not None and seq < before
        )
    values, start = page_slice(
        store, keys, end=end, limit=limit, read=read_channel_message
    )
    oldest = channel_message_seq(keys[start]) if values else None
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


def session_max_event_id(store: Any, events: list[dict[str, Any]]) -> int:
    """Return the FULL log's true maximum ``event_id`` for cursor contracts.

    Prefers the store's monotonic session-global counter (O(1), and mirrored
    events ratchet it upward); falls back to scanning ``events`` when the
    store exposes no counter. Callers serving paginated payloads MUST NOT
    report a page-local maximum: a client advancing its incremental cursor
    from a page-bounded value would skip or re-fetch events on the next
    request.
    """
    if store is not None:
        max_fn = getattr(store, "max_event_id", None)
        if callable(max_fn):
            try:
                return int(max_fn(""))
            except Exception as e:
                logger.warning("max_event_id read failed", error=str(e))
    out = 0
    for evt in events:
        eid = event_id_of(evt)
        if eid is not None and eid > out:
            out = eid
    return out

"""Live per-creature chat-history and branch-metadata reads.

Split out of :mod:`kohakuterrarium.terrarium.creature_ops` (the shared
agent-read surface) so the history builders own one cohesive area. Every
function takes the engine + creature id and touches only ``Agent`` +
``SessionStore`` — same tier rules as creature_ops: no ``studio`` / ``api``
imports, so the session-tier paging helpers in
:mod:`kohakuterrarium.session.history_paging` are the shared ground truth
for saved and live cursors.
"""

from typing import Any

from kohakuterrarium.session.history import project_branch_metadata
from kohakuterrarium.session.history_paging import (
    event_id_of,
    paged_agent_events,
    session_max_event_id,
)
from kohakuterrarium.terrarium.engine import Terrarium


def _resumable_events(
    store: Any, name: str, live_jobs: set[str]
) -> list[dict[str, Any]]:
    if store is None:
        return []
    try:
        return store.get_resumable_events(name, live_job_ids=live_jobs)
    except Exception:
        return []


def agent_live_job_ids(agent: Any) -> set[str]:
    """Best-effort union of "still actually running" job ids on an agent.

    ``_direct_job_meta`` only tracks jobs the controller is *currently*
    awaiting in the foreground turn. A background-promoted sub-agent
    (or executor-backed background tool) is dropped from
    ``_direct_job_meta`` the moment it's promoted, even though
    ``subagent_manager`` / ``executor`` still own its live task. Bug 1
    surfaces because ``normalize_resumable_events`` synthesised an
    "Interrupted by session resume" terminal for those background jobs
    — the frontend then rendered the still-live bubble as interrupted.
    Union all three sources so the synthesis only fires for genuinely
    dead jobs.
    """
    live: set[str] = set(getattr(agent, "_direct_job_meta", {}).keys())
    sub_mgr = getattr(agent, "subagent_manager", None)
    if sub_mgr is not None:
        try:
            for status in sub_mgr.get_running_jobs():
                jid = getattr(status, "job_id", None)
                if isinstance(jid, str) and jid:
                    live.add(jid)
        except Exception:  # pragma: no cover - defensive
            pass
    executor = getattr(agent, "executor", None)
    if executor is not None:
        get_running = getattr(executor, "get_running_jobs", None)
        if callable(get_running):
            try:
                for status in get_running():
                    jid = getattr(status, "job_id", None)
                    if isinstance(jid, str) and jid:
                        live.add(jid)
            except Exception:  # pragma: no cover - defensive
                pass
    return live


def chat_history_for(
    engine: Terrarium,
    creature_id: str,
    *,
    limit: int = 0,
    before: int | None = None,
) -> dict[str, Any]:
    """Conversation snapshot + event log for one live creature.

    ``limit`` / ``before`` page the event log AT THE STORE READ, with the
    same cursor contract as the saved-session history route: at most
    ``limit`` events (or ~4MB of event JSON), ``before`` an exclusive
    ``event_id`` cursor. Only the page's values are read, so a 75k-event
    log costs one key enumeration plus one page of reads instead of the
    multi-second full build. The default ``limit=0`` keeps the full build
    for branch/rewind resyncs that need the whole log.

    ``max_event_id`` always reports the FULL log's true maximum (the
    session-global counter) — never the page maximum, which would desync a
    client's incremental cursor. Older pages (``before`` set) omit the
    conversation snapshot, mirroring the saved-route contract.
    """
    creature = engine.get_creature(creature_id)
    agent = creature.agent
    live_jobs = agent_live_job_ids(agent)
    # Agent-attached store is primary; the engine's lifecycle-attached
    # store (``_session_stores[graph_id]``) is the fallback for agents
    # that never got an agent-level attach (older terrarium recipes).
    agent_store = getattr(agent, "session_store", None)
    fallback = engine._session_stores.get(creature.graph_id)
    if limit and limit > 0:
        store = agent_store if agent_store is not None else fallback
        if store is None:
            page: dict[str, Any] = {
                "events": [],
                "has_more": False,
                "oldest_event_id": None,
                "total": 0,
            }
        else:
            page = paged_agent_events(
                store,
                creature.name,
                limit=limit,
                before=before,
                live_job_ids=live_jobs,
            )
        return {
            **page,
            "creature_id": creature_id,
            "session_id": creature.graph_id,
            # Snapshot only on the newest page — it describes the whole
            # conversation; per-page copies would duplicate megabytes.
            "messages": (
                []
                if before is not None
                else list(getattr(agent, "conversation_history", []) or [])
            ),
            "is_processing": bool(agent.is_processing),
            "max_event_id": session_max_event_id(store, page["events"]),
        }
    events = _resumable_events(agent_store, creature.name, live_jobs)
    if not events:
        events = _resumable_events(fallback, creature.name, live_jobs)
    return {
        "creature_id": creature_id,
        "session_id": creature.graph_id,
        "messages": list(getattr(agent, "conversation_history", []) or []),
        "events": events,
        "is_processing": bool(agent.is_processing),
        "has_more": False,
        "oldest_event_id": event_id_of(events[0]) if events else None,
        "total": len(events),
        "max_event_id": session_max_event_id(
            agent_store if agent_store is not None else fallback, events
        ),
    }


def chat_branches_for(engine: Terrarium, creature_id: str) -> list[dict[str, Any]]:
    creature = engine.get_creature(creature_id)
    agent = creature.agent
    live_jobs = agent_live_job_ids(agent)
    events = _resumable_events(
        getattr(agent, "session_store", None), creature.name, live_jobs
    )
    if not events:
        fallback = engine._session_stores.get(creature.graph_id)
        events = _resumable_events(fallback, creature.name, live_jobs)
    projection = project_branch_metadata(events)
    return [
        {"turn_index": turn_index, **metadata}
        for turn_index, metadata in projection.items()
    ]

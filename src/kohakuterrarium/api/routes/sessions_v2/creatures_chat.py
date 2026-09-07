"""Expose per-creature chat, editing, history, and branch operations.

Service routing sends remote creature operations to their home workers.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from kohakuterrarium.api.deps import get_service
from kohakuterrarium.api.routes.persistence.live_paths import live_store_entry
from kohakuterrarium.api.routes.sessions_v2._helpers import resolve_creature_id
from kohakuterrarium.session.history_paging import (
    DEFAULT_HISTORY_PAGE_LIMIT,
    paged_channel_events,
)
from kohakuterrarium.api.schemas import (
    AgentChat,
    BranchMutationResponse,
    MessageEdit,
    RegenerateRequest,
)
from kohakuterrarium.errors import ConflictError, NotFoundError
from kohakuterrarium.session.raw_history import UserMessageSelector
from kohakuterrarium.terrarium.service import TerrariumService

router = APIRouter()


@router.post("/{session_id}/creatures/{creature_id}/chat")
async def chat_creature(
    session_id: str,
    creature_id: str,
    req: AgentChat,
    service: TerrariumService = Depends(get_service),
):
    """Non-streaming HTTP chat fallback — collects the streaming chunks."""
    cid = await resolve_creature_id(service, creature_id, session_id)
    content = req.content if req.content is not None else (req.message or "")
    try:
        chunks: list[str] = []
        async for chunk in service.chat(cid, content):
            chunks.append(chunk)
        return {"response": "".join(chunks)}
    except KeyError:
        raise HTTPException(404, f"creature {creature_id!r} not found")


@router.post(
    "/{session_id}/creatures/{creature_id}/regenerate",
    response_model=BranchMutationResponse,
)
async def regenerate_creature(
    session_id: str,
    creature_id: str,
    req: RegenerateRequest | None = None,
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    service: TerrariumService = Depends(get_service),
):
    cid = await resolve_creature_id(service, creature_id, session_id)
    turn_index = req.turn_index if req is not None else None
    branch_view = req.branch_view if req is not None else None
    request_id = request_id or (req.request_id if req is not None else None)
    target = (
        UserMessageSelector(**req.target.model_dump())
        if req is not None and req.target is not None
        else None
    )
    try:
        kwargs = {
            "turn_index": turn_index,
            "branch_view": branch_view,
            "request_id": request_id,
        }
        if target is not None:
            kwargs["target"] = target
        return await service.regenerate(cid, **kwargs)
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ConflictError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/{session_id}/creatures/{creature_id}/messages/{msg_idx}/edit",
    response_model=BranchMutationResponse,
)
async def edit_creature_message(
    session_id: str,
    creature_id: str,
    msg_idx: int,
    req: MessageEdit,
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    service: TerrariumService = Depends(get_service),
):
    if isinstance(req.content, list):
        content: str | list[dict] = [
            part.model_dump() if hasattr(part, "model_dump") else part
            for part in req.content
        ]
    else:
        content = req.content
    cid = await resolve_creature_id(service, creature_id, session_id)
    request_id = request_id or req.request_id
    try:
        target = UserMessageSelector(**req.target.model_dump()) if req.target else None
        kwargs = {
            "turn_index": req.turn_index,
            "user_position": req.user_position,
            "branch_view": req.branch_view,
            "request_id": request_id,
        }
        if target is not None:
            kwargs["target"] = target
        edited = await service.edit_message(cid, msg_idx, content, **kwargs)
        return edited
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ConflictError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{session_id}/creatures/{creature_id}/messages/{msg_idx}/rewind")
async def rewind_creature(
    session_id: str,
    creature_id: str,
    msg_idx: int,
    service: TerrariumService = Depends(get_service),
):
    cid = await resolve_creature_id(service, creature_id, session_id)
    try:
        await service.rewind(cid, msg_idx)
        return {"status": "rewound"}
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ConflictError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


def _history_max_event_id(events: list) -> int:
    out = 0
    for evt in events:
        eid = evt.get("event_id") if isinstance(evt, dict) else None
        if isinstance(eid, int) and eid > out:
            out = eid
    return out


@router.get("/{session_id}/creatures/{creature_id}/history")
async def creature_history(
    session_id: str,
    creature_id: str,
    since_event_id: int | None = None,
    limit: int = Query(DEFAULT_HISTORY_PAGE_LIMIT, ge=0),
    before: int | None = Query(None, ge=0),
    service: TerrariumService = Depends(get_service),
):
    """History payload with cursor paging and an incremental cursor.

    The response carries the most recent ``limit`` events (400 by default,
    or ~4MB of event JSON, whichever fills first) plus the paging fields
    ``has_more`` / ``oldest_event_id`` / ``total``; pass
    ``oldest_event_id`` back as ``before`` to fetch the next-older page,
    and ``limit=0`` restores the FULL payload for the rewind/branch/compact
    resync path that needs the whole log. Paging is applied at the store
    read (``service.chat_history`` -> ``chat_history_for``), so a 75k-event
    log costs one key enumeration plus one page of value reads — not the
    multi-second full build — while still reusing the engine-owned store on
    the event loop (a second connection to an actively written SQLite file
    raises ``SQLITE_IOERR`` on POSIX).

    ``since_event_id`` trims the page to events after that id so the client
    can append incrementally instead of re-fetching. Combined with the
    default bound the page is the newest ``limit`` events of the log with
    the already-applied prefix removed; ``has_more`` / ``oldest_event_id``
    still walk any remainder. Incremental payloads omit the conversation
    snapshot — it is only valid for the whole conversation and would
    mislead an appending client. ``max_event_id`` reports the FULL log's
    true maximum (the session-global counter), never the page maximum,
    which would desync a client's cursor.

    For ``ch:`` targets the cursor is the per-channel message sequence
    because channel messages carry no ``event_id``; the page is read from
    the engine's live store with the same semantics as the saved-session
    history route. Surfaces without a host-local store (multi-node
    coordination) keep the legacy full cross-node merge — the merged log
    has no stable sequence cursor (documented limitation).
    """
    # Channel tabs share this endpoint through the ``ch:`` prefix.
    if creature_id.startswith("ch:"):
        return await _channel_history_page(
            service, session_id, creature_id[3:], limit=limit, before=before
        )
    cid = await resolve_creature_id(service, creature_id, session_id)
    try:
        payload = await service.chat_history(cid, limit=limit, before=before)
    except KeyError:
        raise HTTPException(404, f"creature {creature_id!r} not found")
    events = payload.get("events") or []
    if since_event_id is not None:
        payload["events"] = [
            evt
            for evt in events
            if isinstance(evt, dict)
            and isinstance(evt.get("event_id"), int)
            and evt["event_id"] > since_event_id
        ]
        # Incremental payloads omit the conversation snapshot; it is only
        # valid for the full log and would mislead an appending client.
        payload.pop("messages", None)
    payload.setdefault("max_event_id", _history_max_event_id(events))
    return payload


async def _channel_history_page(
    service: TerrariumService,
    session_id: str,
    channel_name: str,
    *,
    limit: int,
    before: int | None,
) -> dict:
    """Paged channel history, or the legacy full merge without a local store."""
    entry = live_store_entry(service, session_id)
    if entry is not None:
        _graph_id, store = entry
        page = paged_channel_events(store, channel_name, limit=limit, before=before)
        return {
            "creature_id": f"ch:{channel_name}",
            "session_id": session_id,
            "messages": [],
            "events": page["events"],
            "is_processing": False,
            # Channel events carry no event_id; report the contract field
            # explicitly so clients can read it unconditionally.
            "max_event_id": 0,
            "has_more": page["has_more"],
            "oldest_event_id": page["oldest_event_id"],
            "total": page["total"],
        }
    try:
        messages = await service.channel_history(session_id, channel_name)
    except KeyError:
        messages = []
    events = [
        {
            "type": "channel_message",
            "channel": channel_name,
            "sender": message.get("sender", ""),
            "content": message.get("content", ""),
            "ts": message.get("timestamp", message.get("ts", 0)),
        }
        for message in messages
    ]
    return {
        "creature_id": f"ch:{channel_name}",
        "session_id": session_id,
        "messages": [],
        "events": events,
        "is_processing": False,
        "max_event_id": 0,
        "has_more": False,
        "oldest_event_id": None,
        "total": len(events),
    }


@router.get("/{session_id}/creatures/{creature_id}/events/{event_id}")
async def creature_event(
    session_id: str,
    creature_id: str,
    event_id: int,
    service: TerrariumService = Depends(get_service),
):
    """Lazy single-event fetch: full tool/subagent output on expand.

    History payloads carry bounded ``output_preview`` strings; the client
    calls this to load the full ``output``/``result`` of one event.
    """
    cid = await resolve_creature_id(service, creature_id, session_id)
    try:
        return await service.chat_event(cid, event_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{session_id}/creatures/{creature_id}/branches")
async def creature_branches(
    session_id: str,
    creature_id: str,
    service: TerrariumService = Depends(get_service),
):
    cid = await resolve_creature_id(service, creature_id, session_id)
    try:
        return await service.chat_branches(cid)
    except KeyError:
        raise HTTPException(404, f"creature {creature_id!r} not found")

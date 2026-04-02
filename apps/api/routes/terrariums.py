"""Terrarium CRUD + lifecycle + chat routes."""

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_manager
from apps.api.events import get_event_log
from apps.api.schemas import AgentChat, ChannelAdd, TerrariumCreate

router = APIRouter()


@router.post("")
async def create_terrarium(req: TerrariumCreate, manager=Depends(get_manager)):
    """Create and start a terrarium from a config path."""
    try:
        tid = await manager.terrarium_create(config_path=req.config_path)
        return {"terrarium_id": tid, "status": "running"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_terrariums(manager=Depends(get_manager)):
    """List all running terrariums."""
    return manager.terrarium_list()


@router.get("/{terrarium_id}")
def get_terrarium(terrarium_id: str, manager=Depends(get_manager)):
    """Get status of a specific terrarium."""
    try:
        return manager.terrarium_status(terrarium_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{terrarium_id}")
async def stop_terrarium(terrarium_id: str, manager=Depends(get_manager)):
    """Stop and cleanup a terrarium."""
    try:
        await manager.terrarium_stop(terrarium_id)
        return {"status": "stopped"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{terrarium_id}/channels")
async def add_channel(terrarium_id: str, req: ChannelAdd, manager=Depends(get_manager)):
    """Add a channel to a running terrarium."""
    try:
        await manager.terrarium_channel_add(
            terrarium_id, req.name, req.channel_type, req.description
        )
        return {"status": "created", "channel": req.name}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/{terrarium_id}/history/{target}")
def terrarium_history(terrarium_id: str, target: str, manager=Depends(get_manager)):
    """Get full history for a creature or root agent.

    target: "root" for root agent, or creature name.
    Returns conversation messages + event log.

    Events are read from the SessionStore (persistent, survives resume)
    with fallback to the in-memory event log.
    """
    try:
        session = manager.terrarium_mount(terrarium_id, target)
        mount_key = f"{terrarium_id}:{target}"

        # Prefer SessionStore events (persistent, works after resume)
        events = []
        agent = session.agent
        if hasattr(agent, "session_store") and agent.session_store:
            try:
                events = agent.session_store.get_events(target)
            except Exception:
                pass

        # Fallback to in-memory log
        if not events:
            events = get_event_log(mount_key)

        return {
            "terrarium_id": terrarium_id,
            "target": target,
            "messages": agent.conversation_history,
            "events": events,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{terrarium_id}/chat/{target}")
async def chat_terrarium(
    terrarium_id: str,
    target: str,
    req: AgentChat,
    manager=Depends(get_manager),
):
    """Non-streaming chat with a creature or root agent."""
    try:
        chunks = []
        async for chunk in manager.terrarium_chat(terrarium_id, target, req.message):
            chunks.append(chunk)
        return {"response": "".join(chunks)}
    except ValueError as e:
        raise HTTPException(404, str(e))

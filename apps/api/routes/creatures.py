"""Creature status + control routes."""

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_manager
from apps.api.schemas import CreatureAdd, WireChannel
from kohakuterrarium.terrarium.config import CreatureConfig

router = APIRouter()


@router.get("")
def list_creatures(terrarium_id: str, manager=Depends(get_manager)):
    """List all creatures in a terrarium."""
    try:
        status = manager.terrarium_status(terrarium_id)
        return status.get("creatures", {})
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("")
async def add_creature(
    terrarium_id: str, req: CreatureAdd, manager=Depends(get_manager)
):
    """Add a creature to a running terrarium."""
    config = CreatureConfig(
        name=req.name,
        config_path=req.config_path,
        listen_channels=req.listen_channels,
        send_channels=req.send_channels,
    )
    try:
        name = await manager.creature_add(terrarium_id, config)
        return {"creature": name, "status": "running"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/{name}")
async def remove_creature(terrarium_id: str, name: str, manager=Depends(get_manager)):
    """Remove a creature from a running terrarium."""
    try:
        removed = await manager.creature_remove(terrarium_id, name)
        if not removed:
            raise HTTPException(404, f"Creature not found: {name}")
        return {"status": "removed"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/interrupt")
async def interrupt_creature(
    terrarium_id: str, name: str, manager=Depends(get_manager)
):
    """Interrupt a creature's current processing. Creature stays alive."""
    try:
        runtime = manager._get_runtime(terrarium_id)
        if name == "root":
            agent = runtime.root_agent
        else:
            agent = runtime.get_creature_agent(name)
        if not agent:
            raise HTTPException(404, f"Creature not found: {name}")
        agent.interrupt()
        return {"status": "interrupted", "creature": name}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/wire")
async def wire_channel(
    terrarium_id: str, name: str, req: WireChannel, manager=Depends(get_manager)
):
    """Wire a creature to a channel (listen or send)."""
    try:
        await manager.creature_wire(terrarium_id, name, req.channel, req.direction)
        return {"status": "wired"}
    except Exception as e:
        raise HTTPException(400, str(e))

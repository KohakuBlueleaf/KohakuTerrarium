"""Creature status + control routes."""

from fastapi import APIRouter, Depends, HTTPException

from kohakuterrarium.api.deps import get_manager
from kohakuterrarium.api.schemas import CreatureAdd, ModelSwitch, WireChannel
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
        await manager.creature_interrupt(terrarium_id, name)
        return {"status": "interrupted", "creature": name}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{name}/jobs")
def creature_jobs(terrarium_id: str, name: str, manager=Depends(get_manager)):
    """List running background jobs for a creature."""
    try:
        return manager.creature_get_jobs(terrarium_id, name)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/tasks/{job_id}/stop")
async def stop_creature_task(
    terrarium_id: str, name: str, job_id: str, manager=Depends(get_manager)
):
    """Stop a specific background task on a creature."""
    try:
        if await manager.creature_cancel_job(terrarium_id, name, job_id):
            return {"status": "cancelled", "job_id": job_id}
        raise HTTPException(404, f"Task not found or already completed: {job_id}")
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/model")
def switch_creature_model(
    terrarium_id: str, name: str, req: ModelSwitch, manager=Depends(get_manager)
):
    """Switch a creature's LLM model mid-session."""
    try:
        model = manager.creature_switch_model(terrarium_id, name, req.model)
        return {"status": "switched", "creature": name, "model": model}
    except ValueError as e:
        raise HTTPException(400, str(e))


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

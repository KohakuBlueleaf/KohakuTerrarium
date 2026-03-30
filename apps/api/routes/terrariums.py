"""Terrarium CRUD + lifecycle + hot-plug routes."""

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_manager
from apps.api.schemas import ChannelAdd, TerrariumCreate

router = APIRouter()


@router.post("")
async def create_terrarium(req: TerrariumCreate, manager=Depends(get_manager)):
    """Create and start a terrarium from a config path."""
    try:
        tid = await manager.create_terrarium(config_path=req.config_path)
        return {"terrarium_id": tid, "status": "running"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_terrariums(manager=Depends(get_manager)):
    """List all running terrariums."""
    return manager.list_terrariums()


@router.get("/{terrarium_id}")
def get_terrarium(terrarium_id: str, manager=Depends(get_manager)):
    """Get status of a specific terrarium."""
    try:
        return manager.get_terrarium_status(terrarium_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{terrarium_id}")
async def stop_terrarium(terrarium_id: str, manager=Depends(get_manager)):
    """Stop and cleanup a terrarium."""
    try:
        await manager.stop_terrarium(terrarium_id)
        return {"status": "stopped"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{terrarium_id}/channels")
async def add_channel(terrarium_id: str, req: ChannelAdd, manager=Depends(get_manager)):
    """Add a channel to a running terrarium."""
    try:
        await manager.add_channel(
            terrarium_id, req.name, req.channel_type, req.description
        )
        return {"status": "created", "channel": req.name}
    except Exception as e:
        raise HTTPException(400, str(e))

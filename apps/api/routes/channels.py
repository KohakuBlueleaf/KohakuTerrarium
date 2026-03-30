"""Channel list + send routes."""

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_manager
from apps.api.schemas import ChannelSend

router = APIRouter()


@router.get("")
def list_channels(terrarium_id: str, manager=Depends(get_manager)):
    """List all channels in a terrarium."""
    try:
        return manager.terrarium_channel_list(terrarium_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{channel_name}/send")
async def send_message(
    terrarium_id: str,
    channel_name: str,
    req: ChannelSend,
    manager=Depends(get_manager),
):
    """Send a message to a channel."""
    try:
        msg_id = await manager.terrarium_channel_send(
            terrarium_id, channel_name, req.content, req.sender
        )
        return {"message_id": msg_id, "status": "sent"}
    except Exception as e:
        raise HTTPException(400, str(e))

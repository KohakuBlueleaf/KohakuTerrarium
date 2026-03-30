"""Pydantic request/response models for the HTTP API."""

from pydantic import BaseModel


class TerrariumCreate(BaseModel):
    """Request body for creating a terrarium."""

    config_path: str


class TerrariumStatus(BaseModel):
    """Response model for terrarium status."""

    terrarium_id: str
    name: str
    running: bool
    creatures: dict
    channels: list


class CreatureAdd(BaseModel):
    """Request body for adding a creature to a terrarium."""

    name: str
    config_path: str
    listen_channels: list[str] = []
    send_channels: list[str] = []


class ChannelSend(BaseModel):
    """Request body for sending a message to a channel."""

    content: str
    sender: str = "human"


class ChannelAdd(BaseModel):
    """Request body for adding a channel to a terrarium."""

    name: str
    channel_type: str = "queue"
    description: str = ""


class WireChannel(BaseModel):
    """Request body for wiring a creature to a channel."""

    channel: str
    direction: str  # "listen" or "send"


class AgentCreate(BaseModel):
    """Request body for creating a standalone agent."""

    config_path: str


class AgentChat(BaseModel):
    """Request body for sending a chat message to an agent."""

    message: str

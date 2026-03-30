"""Unified service manager for agents and terrariums.

All runtime operations go through KohakuManager.
Transport-agnostic -- used by any interface (CLI, TUI, Web, Gradio).
"""

import asyncio
from typing import AsyncIterator
from uuid import uuid4

from kohakuterrarium.serving.agent_session import AgentSession
from kohakuterrarium.serving.events import ChannelEvent, OutputEvent
from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.terrarium.config import (
    CreatureConfig,
    TerrariumConfig,
    load_terrarium_config,
)
from kohakuterrarium.terrarium.observer import ChannelObserver
from kohakuterrarium.terrarium.runtime import TerrariumRuntime
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class KohakuManager:
    """Unified service manager. All runtime operations go through here."""

    def __init__(self) -> None:
        self._terrariums: dict[str, TerrariumRuntime] = {}
        self._terrarium_tasks: dict[str, asyncio.Task] = {}
        self._agents: dict[str, AgentSession] = {}
        self._observers: dict[str, ChannelObserver] = {}

    # =================================================================
    # Standalone Agent Serving
    # =================================================================

    async def create_agent(
        self,
        config_path: str | None = None,
        config: AgentConfig | None = None,
    ) -> str:
        """Create and start a standalone agent. Returns agent_id."""
        if config_path:
            session = await AgentSession.from_path(config_path)
        elif config:
            session = await AgentSession.from_config(config)
        else:
            raise ValueError("Must provide config_path or config")

        self._agents[session.agent_id] = session
        logger.info("Agent created", agent_id=session.agent_id)
        return session.agent_id

    async def stop_agent(self, agent_id: str) -> None:
        """Stop and cleanup an agent."""
        session = self._agents.pop(agent_id, None)
        if session:
            await session.stop()

    async def chat(self, agent_id: str, message: str) -> AsyncIterator[str]:
        """Send a message and stream the response."""
        session = self._agents.get(agent_id)
        if not session:
            raise ValueError(f"Agent not found: {agent_id}")
        async for chunk in session.chat(message):
            yield chunk

    def get_agent_status(self, agent_id: str) -> dict:
        """Get agent status (running, tools, subagents)."""
        session = self._agents.get(agent_id)
        if not session:
            raise ValueError(f"Agent not found: {agent_id}")
        return session.get_status()

    def list_agents(self) -> list[dict]:
        """List all running agents with basic status."""
        return [s.get_status() for s in self._agents.values()]

    # =================================================================
    # Terrarium Serving
    # =================================================================

    async def create_terrarium(
        self,
        config_path: str | None = None,
        config: TerrariumConfig | None = None,
    ) -> str:
        """Create and start a terrarium. Returns terrarium_id."""
        if config_path:
            cfg = load_terrarium_config(config_path)
        elif config:
            cfg = config
        else:
            raise ValueError("Must provide config_path or config")

        from kohakuterrarium.core.environment import Environment

        terrarium_id = f"terrarium_{uuid4().hex[:8]}"
        env = Environment(env_id=f"terrarium_{cfg.name}_{uuid4().hex[:8]}")
        runtime = TerrariumRuntime(cfg, environment=env)
        self._terrariums[terrarium_id] = runtime

        # Start in background task so create returns quickly
        task = asyncio.create_task(runtime.run())
        self._terrarium_tasks[terrarium_id] = task

        # Brief yield so the runtime.start() coroutine can run
        await asyncio.sleep(0.1)

        logger.info("Terrarium created", terrarium_id=terrarium_id)
        return terrarium_id

    async def stop_terrarium(self, terrarium_id: str) -> None:
        """Stop all creatures and cleanup."""
        # Stop observer if any
        observer = self._observers.pop(terrarium_id, None)
        if observer:
            await observer.stop()

        # Stop runtime
        runtime = self._terrariums.pop(terrarium_id, None)
        if runtime:
            await runtime.stop()

        # Cancel background task
        task = self._terrarium_tasks.pop(terrarium_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def get_terrarium(self, terrarium_id: str) -> TerrariumRuntime:
        """Get the runtime instance for direct API access."""
        runtime = self._terrariums.get(terrarium_id)
        if not runtime:
            raise ValueError(f"Terrarium not found: {terrarium_id}")
        return runtime

    def get_terrarium_status(self, terrarium_id: str) -> dict:
        """Get terrarium status (creatures, channels, running state)."""
        runtime = self.get_terrarium(terrarium_id)
        status = runtime.get_status()
        status["terrarium_id"] = terrarium_id
        return status

    def list_terrariums(self) -> list[dict]:
        """List all running terrariums."""
        return [
            {**rt.get_status(), "terrarium_id": tid}
            for tid, rt in self._terrariums.items()
        ]

    # =================================================================
    # Terrarium Hot-Plug
    # =================================================================

    async def add_creature(self, terrarium_id: str, config: CreatureConfig) -> str:
        """Add a creature to a running terrarium. Returns creature name."""
        runtime = self.get_terrarium(terrarium_id)
        handle = await runtime.add_creature(config)
        return handle.name

    async def remove_creature(self, terrarium_id: str, name: str) -> bool:
        """Remove a creature from a running terrarium."""
        runtime = self.get_terrarium(terrarium_id)
        return await runtime.remove_creature(name)

    async def add_channel(
        self,
        terrarium_id: str,
        name: str,
        channel_type: str = "queue",
        description: str = "",
    ) -> None:
        """Add a channel to a running terrarium."""
        runtime = self.get_terrarium(terrarium_id)
        await runtime.add_channel(name, channel_type, description)

    async def wire_channel(
        self,
        terrarium_id: str,
        creature: str,
        channel: str,
        direction: str,
    ) -> None:
        """Wire a creature to a channel (listen or send)."""
        runtime = self.get_terrarium(terrarium_id)
        await runtime.wire_channel(creature, channel, direction)

    async def send_to_channel(
        self,
        terrarium_id: str,
        channel: str,
        content: str,
        sender: str = "human",
    ) -> str:
        """Send a message to a terrarium channel. Returns message_id."""
        runtime = self.get_terrarium(terrarium_id)
        return await runtime.api.send_to_channel(channel, content, sender)

    # =================================================================
    # Event Streams
    # =================================================================

    async def stream_channel_events(
        self,
        terrarium_id: str,
        channels: list[str] | None = None,
    ) -> AsyncIterator[ChannelEvent]:
        """Stream channel messages. Async iterator, transport-agnostic.

        If channels is None, stream all channels.
        """
        runtime = self.get_terrarium(terrarium_id)

        # Use or create observer
        if terrarium_id not in self._observers:
            observer = ChannelObserver(runtime._session)
            self._observers[terrarium_id] = observer
        observer = self._observers[terrarium_id]

        # Setup queue to bridge callback -> async iterator
        event_queue: asyncio.Queue[ChannelEvent] = asyncio.Queue()

        def on_message(msg):
            event_queue.put_nowait(
                ChannelEvent(
                    terrarium_id=terrarium_id,
                    channel=msg.channel,
                    sender=msg.sender,
                    content=msg.content,
                    message_id=msg.message_id,
                    timestamp=msg.timestamp,
                )
            )

        observer.on_message(on_message)

        # Observe requested channels (or all)
        all_channels = [c["name"] for c in runtime._session.channels.get_channel_info()]
        observe_channels = channels or all_channels
        for ch_name in observe_channels:
            await observer.observe(ch_name)

        # Yield events until runtime stops
        try:
            while runtime._running:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    continue
        finally:
            await observer.stop()
            self._observers.pop(terrarium_id, None)

    # =================================================================
    # Cleanup
    # =================================================================

    async def shutdown(self) -> None:
        """Stop everything."""
        for agent_id in list(self._agents.keys()):
            await self.stop_agent(agent_id)
        for tid in list(self._terrariums.keys()):
            await self.stop_terrarium(tid)

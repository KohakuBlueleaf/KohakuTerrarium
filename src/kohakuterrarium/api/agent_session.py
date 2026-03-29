"""Standalone agent chat session.

Wraps an Agent instance with streaming chat: inject input, collect
output chunks via an async iterator.
"""

import asyncio
from typing import AsyncIterator
from uuid import uuid4

from kohakuterrarium.api.events import OutputEvent
from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import AgentConfig, load_agent_config
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class AgentSession:
    """A running standalone agent with chat interface.

    Wraps Agent with streaming chat: inject input, collect output
    chunks via an async iterator.
    """

    def __init__(self, agent: Agent, agent_id: str | None = None):
        self.agent_id = agent_id or f"agent_{uuid4().hex[:8]}"
        self.agent = agent
        self._output_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._running = False

        # Wire output to our queue
        agent.set_output_handler(self._on_output_chunk)

    def _on_output_chunk(self, text: str) -> None:
        """Callback from agent's output module."""
        self._output_queue.put_nowait(text)

    @classmethod
    async def from_path(cls, config_path: str) -> "AgentSession":
        """Create session from agent config path."""
        agent = Agent.from_path(config_path)
        session = cls(agent)
        await session.start()
        return session

    @classmethod
    async def from_config(cls, config: AgentConfig) -> "AgentSession":
        """Create session from AgentConfig object."""
        agent = Agent(config)
        session = cls(agent)
        await session.start()
        return session

    async def start(self) -> None:
        """Start the agent."""
        await self.agent.start()
        self._running = True
        logger.info("Agent session started", agent_id=self.agent_id)

    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self._output_queue.put_nowait(None)  # Signal end
        await self.agent.stop()
        logger.info("Agent session stopped", agent_id=self.agent_id)

    async def chat(self, message: str) -> AsyncIterator[str]:
        """Send a message and stream the response.

        Injects input, then yields output chunks as they arrive.
        Yields until the agent finishes processing.
        """
        # Clear any stale output
        while not self._output_queue.empty():
            self._output_queue.get_nowait()

        # Inject input concurrently so we can yield output as it arrives
        inject_task = asyncio.create_task(
            self.agent.inject_input(message, source="chat")
        )

        # Yield output chunks until processing finishes
        while not inject_task.done():
            try:
                chunk = await asyncio.wait_for(self._output_queue.get(), timeout=0.1)
                if chunk is None:
                    break
                yield chunk
            except asyncio.TimeoutError:
                continue

        # Drain remaining output after inject completes
        while not self._output_queue.empty():
            chunk = self._output_queue.get_nowait()
            if chunk is None:
                break
            yield chunk

        # Wait for inject to fully complete (handles exceptions)
        await inject_task

    def get_status(self) -> dict:
        """Get agent status."""
        return {
            "agent_id": self.agent_id,
            "name": self.agent.config.name,
            "running": self._running and self.agent.is_running,
            "tools": self.agent.tools,
            "subagents": self.agent.subagents,
        }

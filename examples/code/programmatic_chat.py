"""
Programmatic chat - send messages to an agent and get responses.

Shows how to embed an agent in your own application by injecting
events and collecting output programmatically.
"""

import asyncio

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.events import TriggerEvent, EventType


async def main() -> None:
    agent = Agent.from_path("examples/agent-apps/swe_agent")
    await agent.start()

    try:
        # Inject a user message as a trigger event
        event = TriggerEvent(
            type=EventType.USER_INPUT,
            content="What files are in the src/ directory?",
        )

        # Process the event (runs LLM + tools, returns when done)
        await agent.process_event(event)

        # The agent's conversation now contains the response
        history = agent.conversation.messages
        for msg in history[-2:]:
            role = msg.role
            text = msg.content[:200] if msg.content else "(no content)"
            print(f"[{role}] {text}")

    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())

"""
Basic agent usage - load config and run interactively.

Shows the simplest way to use KohakuTerrarium: load an agent
from a config directory and run it in an interactive loop.
"""

import asyncio

from kohakuterrarium.core.agent import Agent


async def main() -> None:
    # Load agent from a creature config (inherits tools, prompts, etc.)
    agent = Agent.from_path("examples/agent-apps/swe_agent")

    try:
        await agent.run()  # Interactive CLI loop
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())

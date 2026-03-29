"""
Terrarium runtime - multi-agent orchestration.

Creates channels, wires triggers, manages lifecycle.
Not an agent -- pure wiring.
"""

import asyncio
from typing import Any

from kohakuterrarium.builtins.inputs.none import NoneInput
from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import load_agent_config
from kohakuterrarium.core.session import Session, get_session, set_session
from kohakuterrarium.modules.trigger.channel import ChannelTrigger
from kohakuterrarium.terrarium.config import CreatureConfig, TerrariumConfig
from kohakuterrarium.terrarium.creature import CreatureHandle
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def _build_channel_topology_prompt(
    config: TerrariumConfig,
    creature: CreatureConfig,
) -> str:
    """
    Build a prompt section describing the channel topology visible
    to a given creature.

    Only channels that the creature listens to or can send on are
    included, plus any broadcast channels (visible to everyone).
    """
    # Index channel configs by name for quick lookup
    ch_by_name: dict[str, Any] = {}
    for ch in config.channels:
        ch_by_name[ch.name] = ch

    # Determine which channels this creature should know about
    relevant_names: set[str] = set()
    relevant_names.update(creature.listen_channels)
    relevant_names.update(creature.send_channels)

    # Also include broadcast channels -- they are visible to everyone
    for ch in config.channels:
        if ch.channel_type == "broadcast":
            relevant_names.add(ch.name)

    if not relevant_names:
        return ""

    lines: list[str] = [
        "## Terrarium Channels",
        "",
        "You are part of a multi-agent team. "
        "Use channels to communicate with other agents.",
        "",
    ]

    listen_set = set(creature.listen_channels)
    send_set = set(creature.send_channels)

    for ch_name in sorted(relevant_names):
        ch_cfg = ch_by_name.get(ch_name)
        if ch_cfg is None:
            continue

        desc = f" -- {ch_cfg.description}" if ch_cfg.description else ""
        roles: list[str] = []
        if ch_name in listen_set:
            roles.append("listen")
        if ch_name in send_set:
            roles.append("send")
        role_str = f" ({', '.join(roles)})" if roles else ""

        lines.append(f"- `{ch_name}` [{ch_cfg.channel_type}]{role_str}{desc}")

    lines.append("")

    if send_set:
        lines.append(
            "Send messages with: "
            "`[/send_message]@@channel=<name>\\nYour message[send_message/]`"
        )
    if listen_set:
        lines.append("Messages on your listen channels arrive automatically as events.")

    return "\n".join(lines)


class TerrariumRuntime:
    """
    Multi-agent orchestration runtime.

    Loads creature configs, creates channels, wires triggers,
    and manages lifecycle.  No intelligence -- pure wiring.
    """

    def __init__(self, config: TerrariumConfig):
        self.config = config
        self._creatures: dict[str, CreatureHandle] = {}
        self._session_key = f"terrarium_{config.name}"
        self._session: Session | None = None
        self._running = False
        self._creature_tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the terrarium.

        1. Create shared session with channel registry.
        2. Pre-create all declared channels.
        3. For each creature:
           a. Load agent config.
           b. Create Agent instance with shared session.
           c. Inject ChannelTriggers for listen channels.
           d. Inject channel topology into system prompt.
        4. Start all creature agents.
        """
        if self._running:
            logger.warning("Terrarium already running")
            return

        logger.info("Starting terrarium", terrarium_name=self.config.name)

        # 1. Shared session
        self._session = get_session(self._session_key)
        set_session(self._session, key=self._session_key)

        # 2. Pre-create channels
        for ch_cfg in self.config.channels:
            self._session.channels.get_or_create(
                ch_cfg.name,
                channel_type=ch_cfg.channel_type,
                description=ch_cfg.description,
            )
            logger.debug(
                "Channel created",
                channel=ch_cfg.name,
                channel_type=ch_cfg.channel_type,
            )

        # 3. Build creatures
        for creature_cfg in self.config.creatures:
            handle = self._build_creature(creature_cfg)
            self._creatures[creature_cfg.name] = handle

        # 4. Start all creature agents
        for handle in self._creatures.values():
            await handle.agent.start()
            logger.info("Creature started", creature=handle.name)

        self._running = True
        logger.info(
            "Terrarium started",
            terrarium_name=self.config.name,
            creatures=len(self._creatures),
        )

    async def stop(self) -> None:
        """Stop all creatures and clean up."""
        if not self._running:
            return

        logger.info("Stopping terrarium", terrarium_name=self.config.name)
        self._running = False

        # Cancel running creature tasks
        for task in self._creature_tasks:
            task.cancel()
        if self._creature_tasks:
            await asyncio.gather(*self._creature_tasks, return_exceptions=True)
        self._creature_tasks.clear()

        # Stop each creature agent
        for handle in self._creatures.values():
            try:
                await handle.agent.stop()
                logger.info("Creature stopped", creature=handle.name)
            except Exception as exc:
                logger.error(
                    "Error stopping creature",
                    creature=handle.name,
                    error=str(exc),
                )

    async def run(self) -> None:
        """
        Run all creatures until interrupted or all stop.

        Each creature runs its own event loop as a concurrent task.
        The runtime waits for all tasks to finish (or cancellation).
        """
        await self.start()

        try:
            # Fire startup triggers and run agents concurrently
            for handle in self._creatures.values():
                task = asyncio.create_task(
                    self._run_creature(handle),
                    name=f"creature_{handle.name}",
                )
                self._creature_tasks.append(task)

            # Wait until all creature tasks are done
            await asyncio.gather(*self._creature_tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Terrarium interrupted")
        except asyncio.CancelledError:
            logger.info("Terrarium cancelled")
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return a status dict for monitoring."""
        creature_states: dict[str, dict[str, Any]] = {}
        for name, handle in self._creatures.items():
            creature_states[name] = {
                "running": handle.is_running,
                "listen_channels": handle.listen_channels,
                "send_channels": handle.send_channels,
            }

        channel_info: list[dict[str, str]] = []
        if self._session:
            channel_info = self._session.channels.get_channel_info()

        return {
            "name": self.config.name,
            "running": self._running,
            "creatures": creature_states,
            "channels": channel_info,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_creature(self, creature_cfg: CreatureConfig) -> CreatureHandle:
        """
        Build a single creature: load config, create Agent, wire channels.
        """
        logger.info(
            "Building creature",
            creature=creature_cfg.name,
            config_path=creature_cfg.config_path,
        )

        # Load the agent config from the creature's config path
        agent_config = load_agent_config(creature_cfg.config_path)

        # Point the agent at the shared session so all creatures
        # share the same ChannelRegistry (and therefore the same channels).
        agent_config.session_key = self._session_key

        # For creatures with no interactive user input, override input
        # to NoneInput so the agent loop blocks on triggers instead of stdin.
        input_module = NoneInput()

        # Create the agent (full init: LLM, registry, executor, controller, etc.)
        agent = Agent(agent_config, input_module=input_module)

        # -- Inject ChannelTriggers for listen channels --
        for ch_name in creature_cfg.listen_channels:
            trigger = ChannelTrigger(
                channel_name=ch_name,
                subscriber_id=creature_cfg.name,
                session=self._session,
            )
            agent._triggers.append(trigger)
            logger.debug(
                "Injected channel trigger",
                creature=creature_cfg.name,
                channel=ch_name,
            )

        # -- Inject channel topology into the system prompt --
        topology_prompt = _build_channel_topology_prompt(self.config, creature_cfg)
        if topology_prompt:
            self._inject_prompt_section(agent, topology_prompt)

        return CreatureHandle(
            name=creature_cfg.name,
            agent=agent,
            config=creature_cfg,
            listen_channels=list(creature_cfg.listen_channels),
            send_channels=list(creature_cfg.send_channels),
        )

    @staticmethod
    def _inject_prompt_section(agent: Agent, section: str) -> None:
        """
        Append *section* to the system message already stored in the
        agent's controller conversation.

        The controller sets up the system message during ``__init__``,
        so by the time we get here it is the first message in the list.
        """
        sys_msg = agent.controller.conversation.get_system_message()
        if sys_msg is None:
            return

        if isinstance(sys_msg.content, str):
            sys_msg.content = sys_msg.content + "\n\n" + section
        # If somehow multimodal, leave as-is (unlikely for system prompt)

    async def _run_creature(self, handle: CreatureHandle) -> None:
        """
        Run a single creature's event loop.

        Mirrors ``Agent.run()`` but without calling ``start()`` / ``stop()``
        (those are managed by the runtime).
        """
        agent = handle.agent

        try:
            # Fire startup trigger if configured
            await agent._fire_startup_trigger()

            idle_logged = False
            while agent._running:
                if not idle_logged:
                    logger.debug(
                        "Creature idle, waiting for input",
                        creature=handle.name,
                    )
                    idle_logged = True

                event = await agent.input.get_input()

                if event is None:
                    if (
                        hasattr(agent.input, "exit_requested")
                        and agent.input.exit_requested
                    ):
                        logger.info("Creature exit requested", creature=handle.name)
                        break
                    continue

                idle_logged = False
                logger.info(
                    "Creature received input",
                    creature=handle.name,
                    event_type=event.type,
                )
                await agent._process_event(event)

        except asyncio.CancelledError:
            logger.info("Creature task cancelled", creature=handle.name)
        except Exception as exc:
            logger.error(
                "Creature error",
                creature=handle.name,
                error=str(exc),
            )
            raise

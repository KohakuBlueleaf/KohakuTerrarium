"""
Terrarium runtime - multi-agent orchestration.

Creates channels, wires triggers, manages lifecycle.
Not an agent -- pure wiring.
"""

import asyncio
from typing import Any
from uuid import uuid4

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import load_agent_config
from kohakuterrarium.core.environment import Environment
from kohakuterrarium.core.session import Session
from kohakuterrarium.terrarium.config import CreatureConfig, TerrariumConfig
from kohakuterrarium.terrarium.creature import CreatureHandle
from kohakuterrarium.terrarium.hotplug import HotPlugMixin
from kohakuterrarium.terrarium.output_log import OutputLogCapture
from kohakuterrarium.utils.logging import get_logger
from kohakuterrarium.builtins.inputs.none import NoneInput
from kohakuterrarium.modules.trigger.channel import ChannelTrigger

logger = get_logger(__name__)


def _build_channel_topology_prompt(
    config: TerrariumConfig,
    creature: CreatureConfig,
) -> str:
    """
    Build a prompt section describing channel topology and semantics.

    Teaches the creature:
    - How channels work (messages vs requests)
    - Which channels it listens on and sends to
    - The difference between queue and broadcast
    - That receiving a message does NOT require a reply
    """
    ch_by_name: dict[str, Any] = {}
    for ch in config.channels:
        ch_by_name[ch.name] = ch

    relevant_names: set[str] = set()
    relevant_names.update(creature.listen_channels)
    relevant_names.update(creature.send_channels)
    for ch in config.channels:
        if ch.channel_type == "broadcast":
            relevant_names.add(ch.name)

    if not relevant_names:
        return ""

    listen_set = set(creature.listen_channels)
    send_set = set(creature.send_channels)

    lines: list[str] = [
        "## Team Communication",
        "",
        "You are part of a multi-agent team. You communicate through channels.",
        "",
        "IMPORTANT - How channels work:",
        "- Messages arrive on your channels automatically. A message is INFORMATION, not a request.",
        "- Receiving a message does NOT mean you must reply or send a message back.",
        "- Only send a message when YOUR WORKFLOW requires it (e.g. sending your output to the next agent).",
        "- Queue channels deliver to one recipient. Broadcast channels deliver to all team members.",
        "- After you complete your task and output your termination keyword, you are DONE. Do not process further messages.",
        "",
        "### Your Channels",
        "",
    ]

    for ch_name in sorted(relevant_names):
        ch_cfg = ch_by_name.get(ch_name)
        if ch_cfg is None:
            continue

        desc = f" - {ch_cfg.description}" if ch_cfg.description else ""
        roles: list[str] = []
        if ch_name in listen_set:
            roles.append("listen")
        if ch_name in send_set:
            roles.append("send")
        role_str = f" ({', '.join(roles)})" if roles else ""

        lines.append(f"- `{ch_name}` [{ch_cfg.channel_type}]{role_str}{desc}")

    lines.append("")

    # List other creatures for context
    other_creatures = [c.name for c in config.creatures if c.name != creature.name]
    if other_creatures:
        lines.append(f"### Team Members: {', '.join(other_creatures)}")
        lines.append("")

    return "\n".join(lines)


class TerrariumRuntime(HotPlugMixin):
    """
    Multi-agent orchestration runtime.

    Loads creature configs, creates channels, wires triggers,
    and manages lifecycle.  No intelligence -- pure wiring.

    Hot-plug methods (add_creature, remove_creature, add_channel,
    wire_channel) are provided by HotPlugMixin.
    """

    def __init__(
        self,
        config: TerrariumConfig,
        *,
        environment: Environment | None = None,
    ):
        self.config = config
        # Use provided environment or create one
        self.environment = environment or Environment(
            env_id=f"terrarium_{config.name}_{uuid4().hex[:8]}"
        )
        self._creatures: dict[str, CreatureHandle] = {}
        self._session_key = self.environment.env_id  # for backward compat
        self._session: Session | None = None  # kept for backward compat
        self._running = False
        self._creature_tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lazy-initialized API / observer
    # ------------------------------------------------------------------

    @property
    def api(self) -> "TerrariumAPI":
        """Get the programmatic API for this runtime."""
        if not hasattr(self, "_api"):
            from kohakuterrarium.terrarium.api import TerrariumAPI

            self._api = TerrariumAPI(self)
        return self._api

    @property
    def observer(self) -> "ChannelObserver":
        """Get the channel observer."""
        if not hasattr(self, "_observer"):
            from kohakuterrarium.terrarium.observer import ChannelObserver

            if self._session is None:
                raise RuntimeError("Cannot create observer before terrarium is started")
            self._observer = ChannelObserver(self._session)
        return self._observer

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the terrarium.

        1. Pre-create shared channels in the environment.
        2. Create backward-compat session pointing at shared channels.
        3. For each creature:
           a. Load agent config.
           b. Create Agent with private session + shared environment.
           c. Inject ChannelTriggers for listen channels.
           d. Inject channel topology into system prompt.
        4. Start all creature agents.
        """
        if self._running:
            logger.warning("Terrarium already running")
            return

        logger.info("Starting terrarium", terrarium_name=self.config.name)

        # 1. Pre-create shared channels in the environment
        for ch_cfg in self.config.channels:
            self.environment.shared_channels.get_or_create(
                ch_cfg.name,
                channel_type=ch_cfg.channel_type,
                description=ch_cfg.description,
            )
            logger.debug(
                "Channel created",
                channel=ch_cfg.name,
                channel_type=ch_cfg.channel_type,
            )

        # 2. Backward-compat session - observer and API use _session.channels
        self._session = Session(key=self._session_key)
        self._session.channels = self.environment.shared_channels

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
        channel_info = self.environment.shared_channels.get_channel_info()

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

        # Each creature gets a PRIVATE session from the environment
        creature_session = self.environment.get_session(creature_cfg.name)

        # For creatures with no interactive user input, override input
        # to NoneInput so the agent loop blocks on triggers instead of stdin.
        input_module = NoneInput()

        # Create the agent with explicit session and environment
        agent = Agent(
            agent_config,
            input_module=input_module,
            session=creature_session,
            environment=self.environment,
        )

        # -- Inject ChannelTriggers for listen channels --
        # Triggers listen on SHARED channels (environment.shared_channels)
        # Broadcast channels get a prompt that frames messages as informational
        broadcast_names = {
            ch.name for ch in self.config.channels if ch.channel_type == "broadcast"
        }
        for ch_name in creature_cfg.listen_channels:
            prompt = None
            if ch_name in broadcast_names:
                prompt = (
                    "[Broadcast on '{channel}' from '{sender}']: {content}\n\n"
                    "This message was broadcast to all team members on '{channel}'. "
                    "Only act on it if it is relevant to your current task."
                )
            trigger = ChannelTrigger(
                channel_name=ch_name,
                subscriber_id=creature_cfg.name,
                prompt=prompt,
                registry=self.environment.shared_channels,
            )
            agent._triggers.append(trigger)
            logger.debug(
                "Injected channel trigger",
                creature=creature_cfg.name,
                channel=ch_name,
                broadcast=ch_name in broadcast_names,
            )

        # -- Inject channel topology into the system prompt --
        topology_prompt = _build_channel_topology_prompt(self.config, creature_cfg)
        if topology_prompt:
            self._inject_prompt_section(agent, topology_prompt)

        # -- Output log capture --
        capture: OutputLogCapture | None = None
        if creature_cfg.output_log:
            capture = OutputLogCapture(
                agent.output_router.default_output,
                max_entries=creature_cfg.output_log_size,
            )
            agent.output_router.default_output = capture
            logger.debug("Output log attached", creature=creature_cfg.name)

        return CreatureHandle(
            name=creature_cfg.name,
            agent=agent,
            config=creature_cfg,
            listen_channels=list(creature_cfg.listen_channels),
            send_channels=list(creature_cfg.send_channels),
            output_log=capture,
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

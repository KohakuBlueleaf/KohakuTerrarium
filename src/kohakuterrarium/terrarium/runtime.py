"""
Terrarium runtime - multi-agent orchestration.

Creates channels, wires triggers, manages lifecycle.
Not an agent -- pure wiring.
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

from kohakuterrarium.builtins.inputs.none import NoneInput
from kohakuterrarium.builtins.tools.registry import get_builtin_tool
from kohakuterrarium.terrarium.tool_manager import (
    TERRARIUM_MANAGER_KEY,
    TerrariumToolManager,
)
from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import build_agent_config
from kohakuterrarium.core.conversation import Conversation
from kohakuterrarium.core.environment import Environment
from kohakuterrarium.core.session import Session
from kohakuterrarium.modules.trigger.channel import ChannelTrigger
from kohakuterrarium.terrarium.api import TerrariumAPI
from kohakuterrarium.terrarium.config import (
    CreatureConfig,
    TerrariumConfig,
    build_channel_topology_prompt,
)
from kohakuterrarium.terrarium.creature import CreatureHandle
from kohakuterrarium.terrarium.hotplug import HotPlugMixin
from kohakuterrarium.terrarium.observer import ChannelObserver
from kohakuterrarium.terrarium.output_log import OutputLogCapture
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def _build_conversation_from_messages(messages: list[dict]) -> Conversation:
    """Build a Conversation from a list of message dicts (for resume)."""
    conv = Conversation()
    for msg in messages:
        kwargs = {}
        if msg.get("tool_calls"):
            kwargs["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            kwargs["tool_call_id"] = msg["tool_call_id"]
        if msg.get("name"):
            kwargs["name"] = msg["name"]
        conv.append(msg.get("role", "user"), msg.get("content", ""), **kwargs)
    return conv


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
        self._root_agent: Agent | None = None

    # ------------------------------------------------------------------
    # Lazy-initialized API / observer
    # ------------------------------------------------------------------

    @property
    def api(self) -> TerrariumAPI:
        """Get the programmatic API for this runtime."""
        if not hasattr(self, "_api"):
            self._api = TerrariumAPI(self)
        return self._api

    @property
    def observer(self) -> ChannelObserver:
        """Get the channel observer."""
        if not hasattr(self, "_observer"):
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

        # 1a. Pre-create shared channels from config
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

        # 1b. Auto-create a direct queue channel for each creature (named after it).
        # This lets the root agent or other creatures send messages directly
        # to a specific creature without extra config.
        for creature_cfg in self.config.creatures:
            self.environment.shared_channels.get_or_create(
                creature_cfg.name,
                channel_type="queue",
                description=f"Direct channel to {creature_cfg.name}",
            )
            logger.debug("Auto-created creature channel", channel=creature_cfg.name)

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

        # 5. Build root agent if configured (OUTSIDE the terrarium)
        # Don't start it here - run() will call agent.run() which handles start
        if self.config.root:
            self._root_agent = self._build_root_agent()
            logger.info(
                "Root agent built",
                base_config=self.config.root.config_data.get("base_config"),
            )

        self._running = True
        logger.info(
            "Terrarium started",
            terrarium_name=self.config.name,
            creatures=len(self._creatures),
            has_root=self._root_agent is not None,
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

        # Signal root agent to exit (its own run() handles cleanup)
        if self._root_agent is not None:
            self._root_agent._running = False

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

        # Attach pending session store (set before run, applied after start)
        if hasattr(self, "_pending_session_store") and self._pending_session_store:
            self.attach_session_store(self._pending_session_store)
            self._pending_session_store = None

        try:
            for handle in self._creatures.values():
                task = asyncio.create_task(
                    self._run_creature(handle),
                    name=f"creature_{handle.name}",
                )
                self._creature_tasks.append(task)

            # If root agent is present, run it as the user-facing loop
            if self._root_agent is not None:
                root_task = asyncio.create_task(
                    self._root_agent.run(),
                    name="root_agent",
                )
                # Root agent is the primary: when user exits root, stop everything
                await root_task
            else:
                # No root: wait for all creature tasks
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

    def attach_session_store(self, store: Any) -> None:
        """Attach a SessionStore to all creatures, root agent, and channels.

        Must be called AFTER start() (when creatures exist) but works
        at any time during the runtime lifecycle.
        """
        self._session_store = store

        # Attach to all creature agents
        for name, handle in self._creatures.items():
            handle.agent.attach_session_store(store)

        # Attach to root agent
        if self._root_agent is not None:
            self._root_agent.attach_session_store(store)

        # Register on_send callbacks for all shared channels
        for ch in self.environment.shared_channels._channels.values():

            def _make_cb(ch_name):
                def _cb(channel_name, message):
                    try:
                        ts = (
                            message.timestamp.isoformat()
                            if hasattr(message.timestamp, "isoformat")
                            else str(message.timestamp)
                        )
                        store.save_channel_message(
                            channel_name,
                            {
                                "sender": message.sender,
                                "content": (
                                    message.content
                                    if isinstance(message.content, str)
                                    else str(message.content)
                                ),
                                "msg_id": message.message_id,
                                "ts": ts,
                            },
                        )
                    except Exception:
                        pass

                return _cb

            ch.on_send(_make_cb(ch.name))

        # Inject resume data if present (conversations + scratchpads)
        if hasattr(self, "_pending_resume_data") and self._pending_resume_data:
            for name, data in self._pending_resume_data.items():
                agent = self.get_creature_agent(name)
                if name == "root" and agent is None:
                    agent = self._root_agent
                if not agent:
                    continue

                saved_messages = data.get("conversation")
                if saved_messages and isinstance(saved_messages, list):
                    agent.controller.conversation = _build_conversation_from_messages(
                        saved_messages
                    )
                    logger.info("Conversation restored", agent=name)

                pad = data.get("scratchpad", {})
                if pad and agent.session:
                    for k, v in pad.items():
                        agent.session.scratchpad.set(k, v)

            self._pending_resume_data = None

        logger.info(
            "Session store attached to terrarium",
            creatures=list(self._creatures.keys()),
            channels=len(self.environment.shared_channels._channels),
        )

    @property
    def root_agent(self) -> Agent | None:
        """The root agent, if configured."""
        return self._root_agent

    def get_creature_agent(self, name: str) -> Agent | None:
        """Get a creature's Agent instance by name. For API mounting."""
        handle = self._creatures.get(name)
        return handle.agent if handle else None

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
            "has_root": self._root_agent is not None,
            "creatures": creature_states,
            "channels": channel_info,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_root_agent(self) -> Agent:
        """
        Build the root agent OUTSIDE the terrarium.

        The root agent:
        - Loads from its own creature config (e.g. creatures/root)
        - Gets a TerrariumToolManager pre-bound to this runtime
        - Has its own I/O (cli/tui) for user interaction
        - Is NOT a peer of terrarium creatures
        """
        root_cfg = self.config.root
        assert root_cfg is not None

        logger.info("Building root agent")

        # Build root agent config from inline dict (supports base_config inheritance)
        agent_config = build_agent_config(root_cfg.config_data, root_cfg.base_dir)

        # Create a separate environment for the root agent
        # with a TerrariumToolManager pre-bound to this runtime
        root_env = Environment(env_id=f"root_{self.environment.env_id}")
        manager = TerrariumToolManager()
        manager.register_runtime(self.config.name, self)
        root_env.register(TERRARIUM_MANAGER_KEY, manager)

        root_session = root_env.get_session("root")

        # Root agent uses its own I/O from its creature config
        agent = Agent(
            agent_config,
            session=root_session,
            environment=root_env,
        )

        # Force-add all terrarium tools regardless of creature config
        self._force_register_terrarium_tools(agent)

        # Inject terrarium awareness into root's system prompt
        awareness = self._build_root_awareness_prompt()
        self._inject_prompt_section(agent, awareness)

        return agent

    @staticmethod
    def _force_register_terrarium_tools(agent: Agent) -> None:
        """Force-register all terrarium management tools on the root agent."""
        terrarium_tool_names = [
            "terrarium_create",
            "terrarium_status",
            "terrarium_stop",
            "terrarium_send",
            "terrarium_observe",
            "terrarium_history",
            "creature_start",
            "creature_stop",
            "list_triggers",
        ]
        for name in terrarium_tool_names:
            if agent.registry.get_tool(name) is None:
                tool = get_builtin_tool(name)
                if tool:
                    agent.registry.register_tool(tool)
                    agent.executor.register_tool(tool)
                    logger.debug("Force-registered terrarium tool", tool_name=name)

    def _build_root_awareness_prompt(self) -> str:
        """Build prompt section telling root about the bound terrarium."""
        creature_names = [c.name for c in self.config.creatures]

        channel_lines: list[str] = []
        for ch in self.config.channels:
            desc = f" - {ch.description}" if ch.description else ""
            channel_lines.append(f"- `{ch.name}` ({ch.channel_type}){desc}")

        # Document auto-created direct channels
        direct_lines: list[str] = []
        for name in creature_names:
            direct_lines.append(f"- `{name}` (queue) - direct channel to {name}")

        parts = [
            f"## Bound Terrarium: {self.config.name}",
            "",
            f"Use terrarium_id='{self.config.name}' for all terrarium tool calls.",
            "",
            "### Creatures",
            ", ".join(creature_names),
            "",
            "### Channels",
            *channel_lines,
            "",
            "### Direct Channels",
            "Every creature has a direct queue channel named after it.",
            "Use these to send messages to a specific creature:",
            *direct_lines,
        ]
        return "\n".join(parts)

    def _build_creature(self, creature_cfg: CreatureConfig) -> CreatureHandle:
        """
        Build a single creature: load config, create Agent, wire channels.
        """
        logger.info(
            "Building creature",
            creature=creature_cfg.name,
        )

        # Build agent config from inline dict (same format as standalone)
        agent_config = build_agent_config(
            creature_cfg.config_data, creature_cfg.base_dir
        )

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

        # Always listen on the creature's own direct channel
        all_listen = list(creature_cfg.listen_channels)
        if creature_cfg.name not in all_listen:
            all_listen.append(creature_cfg.name)

        for ch_name in all_listen:
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
            trigger_id = f"channel_{creature_cfg.name}_{ch_name}"
            agent.trigger_manager._triggers[trigger_id] = trigger
            agent.trigger_manager._created_at[trigger_id] = datetime.now()
            logger.debug(
                "Injected channel trigger",
                creature=creature_cfg.name,
                channel=ch_name,
                trigger_id=trigger_id,
                broadcast=ch_name in broadcast_names,
            )

        # -- Inject channel topology into the system prompt --
        topology_prompt = build_channel_topology_prompt(self.config, creature_cfg)
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

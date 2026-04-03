"""
Creature and root agent construction.

Pure functions that build Agent instances from config, wire channel
triggers, inject topology prompts, and attach output log captures.
Extracted from TerrariumRuntime to keep the runtime focused on
lifecycle orchestration.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from kohakuterrarium.builtins.inputs.none import NoneInput
from kohakuterrarium.builtins.tool_catalog import get_builtin_tool
from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import build_agent_config
from kohakuterrarium.core.environment import Environment
from kohakuterrarium.modules.trigger.channel import ChannelTrigger
from kohakuterrarium.terrarium.config import (
    CreatureConfig,
    TerrariumConfig,
    build_channel_topology_prompt,
)
from kohakuterrarium.terrarium.creature import CreatureHandle
from kohakuterrarium.terrarium.output_log import OutputLogCapture
from kohakuterrarium.terrarium.tool_manager import (
    TERRARIUM_MANAGER_KEY,
    TerrariumToolManager,
)
from kohakuterrarium.terrarium.tool_registration import (
    ensure_terrarium_tools_registered,
)
from kohakuterrarium.utils.logging import get_logger

if TYPE_CHECKING:
    from kohakuterrarium.terrarium.runtime import TerrariumRuntime

logger = get_logger(__name__)


def build_root_agent(
    config: TerrariumConfig,
    environment: Environment,
    runtime: TerrariumRuntime,
) -> Agent:
    """
    Build the root agent OUTSIDE the terrarium.

    The root agent:
    - Loads from its own creature config (e.g. creatures/root)
    - Gets a TerrariumToolManager pre-bound to this runtime
    - Has its own I/O (cli/tui) for user interaction
    - Is NOT a peer of terrarium creatures

    Args:
        config: The terrarium config (must have ``root`` set).
        environment: The terrarium's shared environment.
        runtime: The TerrariumRuntime instance to bind tools to.

    Returns:
        A fully wired root Agent.
    """
    root_cfg = config.root
    assert root_cfg is not None

    logger.info("Building root agent")

    # Build root agent config from inline dict (supports base_config inheritance)
    agent_config = build_agent_config(root_cfg.config_data, root_cfg.base_dir)

    # Create a separate environment for the root agent
    # with a TerrariumToolManager pre-bound to this runtime
    root_env = Environment(env_id=f"root_{environment.env_id}")
    manager = TerrariumToolManager()
    manager.register_runtime(config.name, runtime)
    root_env.register(TERRARIUM_MANAGER_KEY, manager)

    root_session = root_env.get_session("root")

    # Root agent uses NoneInput by default (terrarium TUI handles I/O).
    # If running headless (web API), this is correct.
    # If running with TUI, the terrarium CLI creates the TUI separately.
    from kohakuterrarium.builtins.inputs.none import NoneInput

    agent = Agent(
        agent_config,
        input_module=NoneInput(),
        session=root_session,
        environment=root_env,
    )

    # Force-add all terrarium tools regardless of creature config
    force_register_terrarium_tools(agent)

    # Inject terrarium awareness into root's system prompt
    awareness = build_root_awareness_prompt(config)
    inject_prompt_section(agent, awareness)

    # Auto-inject channel triggers for ALL channels (root hears everything)
    broadcast_names = {
        ch.name for ch in config.channels if ch.channel_type == "broadcast"
    }
    for ch in config.channels:
        if ch.channel_type == "broadcast":
            prompt = (
                "[Channel '{channel}' (broadcast) from {sender}]: {content}\n\n"
                "You are listening to all channels as the team coordinator. "
                "This was broadcast on '{channel}'. "
                "You do NOT need to respond to every message."
            )
        else:
            prompt = (
                "[Channel '{channel}' from {sender}]: {content}\n\n"
                "A message arrived on '{channel}'. "
                "Evaluate if you need to act on it or relay information."
            )
        trigger = ChannelTrigger(
            channel_name=ch.name,
            subscriber_id=f"root_{ch.name}",
            prompt=prompt,
            ignore_sender="root",
            registry=environment.shared_channels,
        )
        trigger_id = f"channel_root_{ch.name}"
        agent.trigger_manager._triggers[trigger_id] = trigger
        agent.trigger_manager._created_at[trigger_id] = datetime.now()
        logger.debug(
            "Injected root channel trigger",
            channel=ch.name,
            broadcast=ch.name in broadcast_names,
        )

    return agent


def force_register_terrarium_tools(agent: Agent) -> None:
    """Force-register all terrarium management tools on the root agent.

    Calls ``ensure_terrarium_tools_registered()`` to make sure the
    terrarium tool decorators have fired before looking them up.
    """
    ensure_terrarium_tools_registered()

    terrarium_tool_names = [
        "terrarium_create",
        "terrarium_status",
        "terrarium_stop",
        "terrarium_send",
        "terrarium_history",
        "creature_start",
        "creature_stop",
        "creature_interrupt",
        "list_triggers",
        "create_trigger",
    ]
    for name in terrarium_tool_names:
        if agent.registry.get_tool(name) is None:
            tool = get_builtin_tool(name)
            if tool:
                agent.registry.register_tool(tool)
                agent.executor.register_tool(tool)
                logger.debug("Force-registered terrarium tool", tool_name=name)


def build_root_awareness_prompt(config: TerrariumConfig) -> str:
    """Build prompt section telling root about the bound terrarium."""
    creature_names = [c.name for c in config.creatures]

    channel_lines: list[str] = []
    for ch in config.channels:
        desc = f" - {ch.description}" if ch.description else ""
        channel_lines.append(f"- `{ch.name}` ({ch.channel_type}){desc}")

    # Document auto-created direct channels
    direct_lines: list[str] = []
    for name in creature_names:
        direct_lines.append(f"- `{name}` (queue) - direct channel to {name}")

    parts = [
        f"## Bound Terrarium: {config.name}",
        "",
        f"Use terrarium_id='{config.name}' for all terrarium tool calls.",
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


def build_creature(
    creature_cfg: CreatureConfig,
    environment: Environment,
    config: TerrariumConfig,
) -> CreatureHandle:
    """
    Build a single creature: load config, create Agent, wire channels.

    Args:
        creature_cfg: Configuration for this creature.
        environment: The terrarium's shared environment.
        config: The full terrarium config (needed for topology prompt).

    Returns:
        A fully wired CreatureHandle.
    """
    logger.info(
        "Building creature",
        creature=creature_cfg.name,
    )

    # Build agent config from inline dict (same format as standalone)
    agent_config = build_agent_config(creature_cfg.config_data, creature_cfg.base_dir)

    # Each creature gets a PRIVATE session from the environment
    creature_session = environment.get_session(creature_cfg.name)

    # For creatures with no interactive user input, override input
    # to NoneInput so the agent loop blocks on triggers instead of stdin.
    input_module = NoneInput()

    # Create the agent with explicit session and environment
    agent = Agent(
        agent_config,
        input_module=input_module,
        session=creature_session,
        environment=environment,
    )

    # -- Inject ChannelTriggers for listen channels --
    # Triggers listen on SHARED channels (environment.shared_channels)
    # Broadcast channels get a prompt that frames messages as informational
    broadcast_names = {
        ch.name for ch in config.channels if ch.channel_type == "broadcast"
    }

    # Always listen on the creature's own direct channel
    all_listen = list(creature_cfg.listen_channels)
    if creature_cfg.name not in all_listen:
        all_listen.append(creature_cfg.name)

    for ch_name in all_listen:
        if ch_name in broadcast_names:
            prompt = (
                "[Channel '{channel}' (broadcast) from {sender}]: {content}\n\n"
                "This was broadcast to all listeners on '{channel}'. "
                "Only respond if relevant to your current task."
            )
        else:
            prompt = "[Channel '{channel}' from {sender}]: {content}"
        trigger = ChannelTrigger(
            channel_name=ch_name,
            subscriber_id=creature_cfg.name,
            prompt=prompt,
            ignore_sender=creature_cfg.name,
            registry=environment.shared_channels,
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
    topology_prompt = build_channel_topology_prompt(config, creature_cfg)
    if topology_prompt:
        inject_prompt_section(agent, topology_prompt)

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


def inject_prompt_section(agent: Agent, section: str) -> None:
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

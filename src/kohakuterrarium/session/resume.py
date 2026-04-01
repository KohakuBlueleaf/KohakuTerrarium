"""
Resume agents and terrariums from .kt session files.

Rebuilds from config, injects saved conversation + scratchpad,
re-attaches session store for continued recording.
"""

import os
from pathlib import Path

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.conversation import Conversation
from kohakuterrarium.session.store import SessionStore
from kohakuterrarium.terrarium.config import load_terrarium_config
from kohakuterrarium.terrarium.runtime import TerrariumRuntime
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def _build_conversation(messages: list[dict]) -> Conversation:
    """Build a Conversation from a list of message dicts.

    Each dict has at minimum {role, content}. May also have
    tool_calls, tool_call_id, name, metadata.
    """
    conv = Conversation()
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        kwargs = {}
        if msg.get("tool_calls"):
            kwargs["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            kwargs["tool_call_id"] = msg["tool_call_id"]
        if msg.get("name"):
            kwargs["name"] = msg["name"]
        if msg.get("metadata"):
            kwargs["metadata"] = msg["metadata"]
        conv.append(role, content, **kwargs)
    return conv


def resume_agent(
    session_path: str | Path,
    pwd_override: str | None = None,
) -> tuple[Agent, SessionStore]:
    """Resume a standalone agent from a .kt session file.

    Args:
        session_path: Path to the .kt session file.
        pwd_override: Override the working directory (uses saved pwd if None).

    Returns:
        (agent, store) tuple. Caller should run agent.run() then store.close().
    """
    store = SessionStore(session_path)
    meta = store.load_meta()

    if meta.get("config_type") != "agent":
        raise ValueError(
            f"Session is a {meta.get('config_type')}, not an agent. "
            "Use resume_terrarium() instead."
        )

    config_path = meta.get("config_path", "")
    if not config_path:
        raise ValueError("Session has no config_path in metadata")

    pwd = pwd_override or meta.get("pwd", ".")
    if pwd and os.path.isdir(pwd):
        os.chdir(pwd)

    # Rebuild agent from config
    agent = Agent.from_path(config_path)
    agent_name = meta.get("agents", [agent.config.name])[0]

    # Inject saved conversation
    saved_messages = store.load_conversation(agent_name)
    if saved_messages:
        conv = _build_conversation(saved_messages)
        agent.controller.conversation = conv
        logger.info(
            "Conversation restored", agent=agent_name, messages=len(saved_messages)
        )

    # Restore scratchpad
    pad_data = store.load_scratchpad(agent_name)
    if pad_data:
        for k, v in pad_data.items():
            agent.session.scratchpad.set(k, v)
        logger.info("Scratchpad restored", agent=agent_name, keys=len(pad_data))

    # Re-attach session store for continued recording
    store.update_status("running")
    agent.attach_session_store(store)

    logger.info("Agent resumed", agent=agent_name, session=str(session_path))
    return agent, store


def resume_terrarium(
    session_path: str | Path,
    pwd_override: str | None = None,
) -> tuple[TerrariumRuntime, SessionStore]:
    """Resume a terrarium from a .kt session file.

    Args:
        session_path: Path to the .kt session file.
        pwd_override: Override the working directory (uses saved pwd if None).

    Returns:
        (runtime, store) tuple. Caller should run runtime.run() then store.close().
        The runtime will auto-inject conversations via attach_session_store.
    """
    store = SessionStore(session_path)
    meta = store.load_meta()

    if meta.get("config_type") != "terrarium":
        raise ValueError(
            f"Session is a {meta.get('config_type')}, not a terrarium. "
            "Use resume_agent() instead."
        )

    config_path = meta.get("config_path", "")
    if not config_path:
        raise ValueError("Session has no config_path in metadata")

    pwd = pwd_override or meta.get("pwd", ".")
    if pwd and os.path.isdir(pwd):
        os.chdir(pwd)

    # Rebuild runtime from config
    config = load_terrarium_config(config_path)
    runtime = TerrariumRuntime(config)

    # Prepare resume data (injected during attach_session_store in run())
    agents = meta.get("agents", [])
    resume_data = {}
    for name in agents:
        resume_data[name] = {
            "conversation": store.load_conversation(name),
            "scratchpad": store.load_scratchpad(name),
        }

    runtime._pending_session_store = store
    runtime._pending_resume_data = resume_data

    store.update_status("running")

    logger.info(
        "Terrarium resume prepared",
        terrarium=config.name,
        agents=agents,
        session=str(session_path),
    )
    return runtime, store


def detect_session_type(session_path: str | Path) -> str:
    """Detect whether a session file is an agent or terrarium.

    Returns "agent" or "terrarium".
    """
    store = SessionStore(session_path)
    try:
        meta = store.load_meta()
        return meta.get("config_type", "agent")
    finally:
        store.close()

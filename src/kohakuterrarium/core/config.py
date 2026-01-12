"""
Configuration loading and validation for KohakuTerrarium agents.

Supports YAML, JSON, and TOML formats with environment variable interpolation.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InputConfig:
    """Configuration for input module."""

    type: str = "cli"  # builtin type or "custom"/"package"
    module: str | None = None  # For custom: "./custom/input.py", for package: "pkg.mod"
    class_name: str | None = None  # Class name to instantiate
    prompt: str = "> "
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerConfig:
    """Configuration for a trigger."""

    type: str  # builtin type (timer, idle, etc.) or "custom"/"package"
    module: str | None = None  # For custom: "./custom/trigger.py"
    class_name: str | None = None  # Class name to instantiate
    prompt: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolConfigItem:
    """Configuration for a tool."""

    name: str
    type: str = "builtin"  # "builtin", "custom", or "package"
    module: str | None = None  # For custom: "./custom/tools/my_tool.py"
    class_name: str | None = None  # Class name to instantiate
    doc: str | None = None  # Override skill doc path
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutputConfig:
    """Configuration for output module."""

    type: str = "stdout"  # builtin type or "custom"/"package"
    module: str | None = None  # For custom: "./custom/output.py"
    class_name: str | None = None  # Class name to instantiate
    controller_direct: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubAgentConfigItem:
    """Configuration for a sub-agent."""

    name: str
    type: str = "builtin"  # "builtin", "custom", or "package"
    module: str | None = None  # For custom: "./custom/subagents/my_agent.py"
    config_name: str | None = (
        None  # Config object name in module (e.g., "MY_AGENT_CONFIG")
    )
    description: str | None = None
    tools: list[str] = field(default_factory=list)
    can_modify: bool = False
    interactive: bool = False  # Whether agent stays alive for context updates
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """
    Complete configuration for an agent.

    Loaded from a config file (YAML/JSON/TOML) in the agent folder.
    """

    name: str
    version: str = "1.0"

    # LLM settings
    model: str = "openai/gpt-4o-mini"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.7
    max_tokens: int = 4096

    # System prompt (loaded from file or inline)
    system_prompt: str = "You are a helpful assistant."
    system_prompt_file: str | None = None

    # Files to inject into system prompt as template variables
    # Maps variable name to file path (relative to agent folder)
    # Example: { "character": "memory/character.md" }
    # Use in system.md: {{ character }}
    prompt_context_files: dict[str, str] = field(default_factory=dict)

    # Skill loading mode: "dynamic" or "static"
    # - dynamic: Model uses [/info] to read tool docs on demand (less tokens upfront)
    # - static: All tool docs included in system prompt (no [/info] needed)
    skill_mode: str = "dynamic"

    # Context management - limits LLM conversation history
    max_messages: int = 50  # Max messages to keep (0 = unlimited)
    max_context_chars: int = 100000  # Max chars (~25k tokens, 0 = unlimited)

    # Module configs
    input: InputConfig = field(default_factory=InputConfig)
    triggers: list[TriggerConfig] = field(default_factory=list)
    tools: list[ToolConfigItem] = field(default_factory=list)
    subagents: list[SubAgentConfigItem] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)

    # Startup trigger (fires once when agent starts)
    startup_trigger: dict[str, Any] | None = None

    # Path to agent folder
    agent_path: Path | None = None

    def get_api_key(self) -> str | None:
        """Get API key from environment."""
        return os.environ.get(self.api_key_env)


# Environment variable pattern: ${VAR} or ${VAR:default}
ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _interpolate_env_vars(value: Any) -> Any:
    """Recursively interpolate environment variables in config values."""
    if isinstance(value, str):

        def replace_env(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            return os.environ.get(var_name, default if default is not None else "")

        return ENV_VAR_PATTERN.sub(replace_env, value)
    elif isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_interpolate_env_vars(v) for v in value]
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file."""
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON file."""
    import json

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_toml(path: Path) -> dict[str, Any]:
    """Load TOML file."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    with open(path, "rb") as f:
        return tomllib.load(f)


def _find_config_file(agent_path: Path) -> Path | None:
    """Find config file in agent folder."""
    for name in ["config.yaml", "config.yml", "config.json", "config.toml"]:
        path = agent_path / name
        if path.exists():
            return path
    return None


def _load_config_file(path: Path) -> dict[str, Any]:
    """Load config file based on extension."""
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return _load_yaml(path)
    elif suffix == ".json":
        return _load_json(path)
    elif suffix == ".toml":
        return _load_toml(path)
    else:
        raise ValueError(f"Unsupported config format: {suffix}")


def _parse_input_config(data: dict[str, Any] | None) -> InputConfig:
    """Parse input configuration."""
    if data is None:
        return InputConfig()
    reserved = {"type", "module", "class", "prompt"}
    return InputConfig(
        type=data.get("type", "cli"),
        module=data.get("module"),
        class_name=data.get("class"),
        prompt=data.get("prompt", "> "),
        options={k: v for k, v in data.items() if k not in reserved},
    )


def _parse_trigger_config(data: dict[str, Any]) -> TriggerConfig:
    """Parse trigger configuration."""
    reserved = {"type", "module", "class", "prompt"}
    return TriggerConfig(
        type=data.get("type", ""),
        module=data.get("module"),
        class_name=data.get("class"),
        prompt=data.get("prompt"),
        options={k: v for k, v in data.items() if k not in reserved},
    )


def _parse_tool_config(data: dict[str, Any]) -> ToolConfigItem:
    """Parse tool configuration."""
    reserved = {"name", "type", "module", "class", "doc"}
    return ToolConfigItem(
        name=data.get("name", ""),
        type=data.get("type", "builtin"),
        module=data.get("module"),
        class_name=data.get("class"),
        doc=data.get("doc"),
        options={k: v for k, v in data.items() if k not in reserved},
    )


def _parse_output_config(data: dict[str, Any] | None) -> OutputConfig:
    """Parse output configuration."""
    if data is None:
        return OutputConfig()
    reserved = {"type", "module", "class", "controller_direct"}
    return OutputConfig(
        type=data.get("type", "stdout"),
        module=data.get("module"),
        class_name=data.get("class"),
        controller_direct=data.get("controller_direct", True),
        options={k: v for k, v in data.items() if k not in reserved},
    )


def _parse_subagent_config(data: dict[str, Any]) -> SubAgentConfigItem:
    """Parse sub-agent configuration."""
    # Fields that are handled explicitly
    reserved = {
        "name",
        "type",
        "module",
        "config",
        "description",
        "tools",
        "can_modify",
        "interactive",
    }
    # All other fields (prompt_file, output_to, context_mode, max_turns, etc.)
    # go into options for inline custom sub-agent configs
    return SubAgentConfigItem(
        name=data.get("name", ""),
        type=data.get("type", "builtin"),
        module=data.get("module"),
        config_name=data.get("config"),
        description=data.get("description"),
        tools=data.get("tools", []),
        can_modify=data.get("can_modify", False),
        interactive=data.get("interactive", False),
        options={k: v for k, v in data.items() if k not in reserved},
    )


def load_agent_config(agent_path: str | Path) -> AgentConfig:
    """
    Load agent configuration from folder.

    Args:
        agent_path: Path to agent folder containing config.yaml

    Returns:
        Loaded AgentConfig

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If config is invalid
    """
    agent_path = Path(agent_path)

    if not agent_path.exists():
        raise FileNotFoundError(f"Agent folder not found: {agent_path}")

    # Find and load config file
    config_file = _find_config_file(agent_path)
    if config_file is None:
        raise FileNotFoundError(f"No config file found in: {agent_path}")

    logger.debug("Loading config", path=str(config_file))
    raw_config = _load_config_file(config_file)

    # Interpolate environment variables
    config_data = _interpolate_env_vars(raw_config)

    # Extract controller section if present
    controller_data = config_data.get("controller", {})

    # Build AgentConfig
    config = AgentConfig(
        name=config_data.get("name", agent_path.name),
        version=config_data.get("version", "1.0"),
        model=controller_data.get(
            "model", config_data.get("model", "openai/gpt-4o-mini")
        ),
        api_key_env=controller_data.get(
            "api_key_env", config_data.get("api_key_env", "OPENROUTER_API_KEY")
        ),
        base_url=controller_data.get(
            "base_url", config_data.get("base_url", "https://openrouter.ai/api/v1")
        ),
        temperature=controller_data.get(
            "temperature", config_data.get("temperature", 0.7)
        ),
        max_tokens=controller_data.get(
            "max_tokens", config_data.get("max_tokens", 4096)
        ),
        system_prompt=config_data.get("system_prompt", "You are a helpful assistant."),
        system_prompt_file=config_data.get("system_prompt_file"),
        prompt_context_files=config_data.get("prompt_context_files", {}),
        skill_mode=controller_data.get(
            "skill_mode", config_data.get("skill_mode", "dynamic")
        ),
        max_messages=controller_data.get("max_messages", 50),
        max_context_chars=controller_data.get("max_context_chars", 100000),
        input=_parse_input_config(config_data.get("input")),
        triggers=[_parse_trigger_config(t) for t in config_data.get("triggers", [])],
        tools=[_parse_tool_config(t) for t in config_data.get("tools", [])],
        subagents=[_parse_subagent_config(s) for s in config_data.get("subagents", [])],
        output=_parse_output_config(config_data.get("output")),
        startup_trigger=config_data.get("startup_trigger"),
        agent_path=agent_path,
    )

    # Load system prompt from file if specified
    if config.system_prompt_file and config.agent_path:
        prompt_path = config.agent_path / config.system_prompt_file
        if prompt_path.exists():
            with open(prompt_path, encoding="utf-8") as f:
                config.system_prompt = f.read()
            logger.debug("Loaded system prompt", path=str(prompt_path))

    # Load prompt context files and render into system prompt
    if config.prompt_context_files and config.agent_path:
        context_vars: dict[str, str] = {}
        for var_name, file_path in config.prompt_context_files.items():
            full_path = config.agent_path / file_path
            if full_path.exists():
                with open(full_path, encoding="utf-8") as f:
                    context_vars[var_name] = f.read()
                logger.debug(
                    "Loaded prompt context file",
                    variable=var_name,
                    path=str(full_path),
                )
            else:
                logger.warning(
                    "Prompt context file not found",
                    variable=var_name,
                    path=str(full_path),
                )

        # Render template with context variables
        if context_vars:
            from kohakuterrarium.prompt.template import render_template_safe

            config.system_prompt = render_template_safe(
                config.system_prompt, **context_vars
            )
            logger.debug(
                "Rendered system prompt with context",
                variables=list(context_vars.keys()),
            )

    logger.info("Agent config loaded", agent_name=config.name, model=config.model)
    return config

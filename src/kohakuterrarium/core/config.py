"""
Configuration loading and validation for KohakuTerrarium agents.

Supports YAML, JSON, and TOML formats with environment variable interpolation.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from kohakuterrarium.packages import resolve_package_path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from kohakuterrarium.prompt.template import render_template_safe
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
class OutputConfigItem:
    """Configuration for a single output module."""

    type: str = "stdout"  # builtin type or "custom"/"package"
    module: str | None = None  # For custom: "./custom/output.py"
    class_name: str | None = None  # Class name to instantiate
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutputConfig:
    """Configuration for output modules."""

    # Default output (for model "thinking" / stdout)
    type: str = "stdout"  # builtin type or "custom"/"package"
    module: str | None = None  # For custom: "./custom/output.py"
    class_name: str | None = None  # Class name to instantiate
    controller_direct: bool = True
    options: dict[str, Any] = field(default_factory=dict)

    # Named outputs for explicit [/output_<name>] blocks
    # Maps name -> OutputConfigItem (e.g., {"discord": OutputConfigItem(...)})
    named_outputs: dict[str, OutputConfigItem] = field(default_factory=dict)


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

    # Inheritance: path to base creature/agent config directory
    base_config: str | None = None

    # LLM settings
    model: str = "openai/gpt-4o-mini"
    auth_mode: str = "api-key"  # "api-key" (default) or "codex-oauth"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.7
    max_tokens: int | None = None  # None = let the API decide
    reasoning_effort: str = "medium"  # none/minimal/low/medium/high/xhigh
    service_tier: str | None = None  # None/priority/flex
    extra_body: dict[str, Any] = field(
        default_factory=dict
    )  # extra fields merged into API request body

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

    # Prompt aggregation controls
    # Set to False if you handle tool/output instructions in your own prompt/context
    include_tools_in_prompt: bool = True  # Add tool list to system prompt
    include_hints_in_prompt: bool = (
        True  # Add framework hints (output format, function calling)
    )

    # Context management - limits LLM conversation history
    max_messages: int = 0  # Max messages to keep (0 = unlimited)
    max_context_chars: int = 0  # Max chars (0 = unlimited)
    ephemeral: bool = (
        False  # Clear conversation after each interaction (for group chat)
    )

    # Module configs
    input: InputConfig = field(default_factory=InputConfig)
    triggers: list[TriggerConfig] = field(default_factory=list)
    tools: list[ToolConfigItem] = field(default_factory=list)
    subagents: list[SubAgentConfigItem] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)

    # Auto-compact config (dict with max_tokens, threshold, target, keep_recent_turns)
    compact: dict[str, Any] | None = None

    # Startup trigger (fires once when agent starts)
    startup_trigger: dict[str, Any] | None = None

    # Termination conditions
    termination: dict[str, Any] | None = None  # Raw termination config dict

    # Sub-agent depth limit (0 = unlimited)
    max_subagent_depth: int = 3

    # Tool call format: "bracket", "xml", "native", or custom dict
    tool_format: str | dict = "bracket"

    # Path to agent folder
    agent_path: Path | None = None

    # Session key for shared state isolation (None = use agent name)
    session_key: str | None = None

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
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_toml(path: Path) -> dict[str, Any]:
    """Load TOML file."""
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


def _resolve_base_config_path(base_config: str, child_dir: Path) -> Path | None:
    """
    Resolve base_config path to an actual directory.

    Resolution order:
    1. If starts with '@', resolve as package reference (@package/path)
    2. If starts with 'creatures/', resolve relative to project root
       (walk up from child_dir until we find a directory containing 'creatures/')
    3. Otherwise resolve relative to child config's parent directory
    """
    # Package reference: @package-name/creatures/swe
    # Strip quotes first (YAML may quote the @ as "@...")
    clean = base_config.strip('"').strip("'")
    if clean.startswith("@"):
        try:
            return resolve_package_path(clean)
        except (FileNotFoundError, ValueError) as e:
            logger.warning(
                "Package reference failed", base_config=base_config, error=str(e)
            )
            return None

    if base_config.startswith("creatures/"):
        # Walk up from child_dir to find project root (containing creatures/)
        search = child_dir
        for _ in range(10):  # safety limit
            candidate = search / base_config
            if candidate.is_dir():
                return candidate
            parent = search.parent
            if parent == search:
                break
            search = parent
        logger.warning(
            "Could not resolve creatures/ path from project root",
            base_config=base_config,
            child_dir=str(child_dir),
        )
        return None

    # Relative to child config's parent directory
    resolved = (child_dir / base_config).resolve()
    if resolved.is_dir():
        return resolved
    logger.warning(
        "Base config directory not found",
        base_config=base_config,
        resolved=str(resolved),
    )
    return None


def _merge_configs(base_data: dict[str, Any], child_data: dict[str, Any]) -> dict:
    """
    Merge child config over base config following creature hierarchy rules.

    - tools, subagents: child entries EXTEND base list (deduplicated by name)
    - Dicts (controller, input, output): shallow-merged (child keys override)
    - Scalars: child overrides base
    - system_prompt_file: tracked separately for append behavior
    """
    # Keys whose lists should be extended, not replaced
    _EXTEND_KEYS = {"tools", "subagents"}

    result = dict(base_data)
    for key, value in child_data.items():
        if key == "base_config":
            continue  # Don't propagate base_config into merged result
        if value is None:
            continue  # Only override if child explicitly sets a value
        if (
            key in _EXTEND_KEYS
            and isinstance(value, list)
            and key in result
            and isinstance(result[key], list)
        ):
            # Extend: base list + child entries (deduplicate by name)
            existing_names = {
                item.get("name") for item in result[key] if isinstance(item, dict)
            }
            merged_list = list(result[key])
            for item in value:
                item_name = item.get("name") if isinstance(item, dict) else None
                if item_name and item_name not in existing_names:
                    merged_list.append(item)
                    existing_names.add(item_name)
            result[key] = merged_list
        elif (
            isinstance(value, dict) and key in result and isinstance(result[key], dict)
        ):
            # Shallow merge for dicts (controller, input, output)
            merged = dict(result[key])
            merged.update(value)
            result[key] = merged
        else:
            # Scalars and other lists: child replaces base
            result[key] = value
    return result


def _load_base_config_data(base_path: Path) -> dict[str, Any] | None:
    """Load raw config data from a base config directory."""
    config_file = _find_config_file(base_path)
    if config_file is None:
        logger.warning("No config file in base directory", path=str(base_path))
        return None

    raw = _load_config_file(config_file)
    data = _interpolate_env_vars(raw)

    # Recursively resolve base_config if the base also has one
    if "base_config" in data and data["base_config"]:
        grandparent_path = _resolve_base_config_path(data["base_config"], base_path)
        if grandparent_path:
            grandparent_data = _load_base_config_data(grandparent_path)
            if grandparent_data:
                data = _merge_configs(grandparent_data, data)

    # Track prompt files with their resolved paths for append chain
    prompt_file = data.get("system_prompt_file")
    if prompt_file:
        prompt_path = base_path / prompt_file
        if prompt_path.exists():
            existing_chain = data.get("_prompt_chain", [])
            data["_prompt_chain"] = existing_chain + [str(prompt_path)]

    return data


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


def _parse_output_config_item(data: dict[str, Any]) -> OutputConfigItem:
    """Parse a single output configuration item."""
    reserved = {"type", "module", "class"}
    return OutputConfigItem(
        type=data.get("type", "stdout"),
        module=data.get("module"),
        class_name=data.get("class"),
        options={k: v for k, v in data.items() if k not in reserved},
    )


def _parse_output_config(data: dict[str, Any] | None) -> OutputConfig:
    """Parse output configuration."""
    if data is None:
        return OutputConfig()

    # Parse named outputs if present
    named_outputs: dict[str, OutputConfigItem] = {}
    if "named_outputs" in data:
        for name, item_data in data["named_outputs"].items():
            named_outputs[name] = _parse_output_config_item(item_data)

    reserved = {"type", "module", "class", "controller_direct", "named_outputs"}
    return OutputConfig(
        type=data.get("type", "stdout"),
        module=data.get("module"),
        class_name=data.get("class"),
        controller_direct=data.get("controller_direct", True),
        options={k: v for k, v in data.items() if k not in reserved},
        named_outputs=named_outputs,
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

    return build_agent_config(config_data, agent_path)


def _resolve_inheritance(
    config_data: dict[str, Any], agent_path: Path
) -> dict[str, Any]:
    """Resolve base_config inheritance and merge parent config data.

    If config_data has a base_config reference, loads the base config
    recursively and merges it with the child config.

    Returns:
        Merged config_data (with _base_path set if inheritance was resolved).
    """
    base_config_ref = config_data.get("base_config")
    if not base_config_ref:
        return config_data

    base_path = _resolve_base_config_path(base_config_ref, agent_path)
    if not base_path:
        logger.warning(
            "Base config not found, continuing with child-only config",
            base_config=base_config_ref,
        )
        return config_data

    base_data = _load_base_config_data(base_path)
    if not base_data:
        return config_data

    logger.debug(
        "Merging base config",
        base=str(base_path),
        child=str(agent_path),
    )
    merged = _merge_configs(base_data, config_data)
    merged["_base_path"] = base_path
    return merged


def _construct_agent_config(
    config_data: dict[str, Any], agent_path: Path
) -> AgentConfig:
    """Build the AgentConfig dataclass from a (possibly merged) config dict."""
    controller_data = config_data.get("controller", {})

    return AgentConfig(
        name=config_data.get("name", agent_path.name),
        version=config_data.get("version", "1.0"),
        model=controller_data.get(
            "model", config_data.get("model", "openai/gpt-4o-mini")
        ),
        auth_mode=controller_data.get(
            "auth_mode", config_data.get("auth_mode", "api-key")
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
            "max_tokens", config_data.get("max_tokens", None)
        ),
        reasoning_effort=controller_data.get(
            "reasoning_effort", config_data.get("reasoning_effort", "medium")
        ),
        service_tier=controller_data.get(
            "service_tier", config_data.get("service_tier", None)
        ),
        extra_body=controller_data.get("extra_body", config_data.get("extra_body", {})),
        system_prompt=config_data.get("system_prompt", "You are a helpful assistant."),
        system_prompt_file=config_data.get("system_prompt_file"),
        prompt_context_files=config_data.get("prompt_context_files", {}),
        skill_mode=controller_data.get(
            "skill_mode", config_data.get("skill_mode", "dynamic")
        ),
        include_tools_in_prompt=controller_data.get(
            "include_tools_in_prompt", config_data.get("include_tools_in_prompt", True)
        ),
        include_hints_in_prompt=controller_data.get(
            "include_hints_in_prompt", config_data.get("include_hints_in_prompt", True)
        ),
        max_messages=controller_data.get("max_messages", 0),
        max_context_chars=controller_data.get("max_context_chars", 0),
        ephemeral=controller_data.get("ephemeral", False),
        tool_format=controller_data.get("tool_format", "bracket"),
        input=_parse_input_config(config_data.get("input")),
        triggers=[_parse_trigger_config(t) for t in config_data.get("triggers", [])],
        tools=[_parse_tool_config(t) for t in config_data.get("tools", [])],
        subagents=[_parse_subagent_config(s) for s in config_data.get("subagents", [])],
        output=_parse_output_config(config_data.get("output")),
        compact=config_data.get("compact"),
        startup_trigger=config_data.get("startup_trigger"),
        termination=config_data.get("termination"),
        max_subagent_depth=config_data.get("max_subagent_depth", 3),
        agent_path=agent_path,
        session_key=config_data.get("session_key"),
    )


def _load_prompt_chain(config: AgentConfig, config_data: dict[str, Any]) -> None:
    """Load system prompt from the file chain (base prompts + child prompt).

    Mutates config.system_prompt in place if prompt files are found.
    """
    base_path = config_data.get("_base_path")
    prompt_chain: list[str] = config_data.get("_prompt_chain", [])
    prompt_parts: list[str] = []

    # Load all base prompt files from the inheritance chain
    for chain_path in prompt_chain:
        chain_file = Path(chain_path)
        if chain_file.exists():
            with open(chain_file, encoding="utf-8") as f:
                prompt_parts.append(f.read())
            logger.debug("Loaded chain prompt", path=str(chain_file))

    # Load child's own system prompt (from agent_path or base_path fallback)
    if config.system_prompt_file and config.agent_path:
        prompt_path = config.agent_path / config.system_prompt_file
        if not prompt_path.exists() and base_path:
            prompt_path = base_path / config.system_prompt_file
        if prompt_path.exists():
            # Only add if not already in chain (avoid duplicates)
            resolved = str(prompt_path.resolve())
            chain_resolved = [str(Path(p).resolve()) for p in prompt_chain]
            if resolved not in chain_resolved:
                with open(prompt_path, encoding="utf-8") as f:
                    prompt_parts.append(f.read())
                logger.debug("Loaded child prompt", path=str(prompt_path))

    if prompt_parts:
        config.system_prompt = "\n\n".join(prompt_parts)
        logger.debug(
            "Assembled system prompt from chain",
            parts=len(prompt_parts),
        )


def _render_prompt_context(config: AgentConfig) -> None:
    """Load prompt context files and render Jinja template variables.

    Mutates config.system_prompt in place if context files are found.
    """
    if not config.prompt_context_files or not config.agent_path:
        return

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

    if context_vars:
        config.system_prompt = render_template_safe(
            config.system_prompt, **context_vars
        )
        logger.debug(
            "Rendered system prompt with context",
            variables=list(context_vars.keys()),
        )


def build_agent_config(
    config_data: dict[str, Any],
    agent_path: Path,
) -> AgentConfig:
    """
    Build AgentConfig from a raw config dict.

    Handles base_config inheritance, system prompt loading, and
    template rendering. Used by load_agent_config (from file) and
    by terrarium runtime (inline root agent config from dict).

    Args:
        config_data: Raw config dict (env vars interpolated automatically)
        agent_path: Path context for resolving relative paths

    Returns:
        Loaded AgentConfig
    """
    config_data = _interpolate_env_vars(config_data)
    config_data = _resolve_inheritance(config_data, agent_path)
    config = _construct_agent_config(config_data, agent_path)
    _load_prompt_chain(config, config_data)
    _render_prompt_context(config)

    logger.info("Agent config loaded", agent_name=config.name, model=config.model)
    return config

"""
Builtin sub-agent configurations.

Provides ready-to-use sub-agent configurations for common tasks:
- explore: Search and explore codebase (read-only)
- plan: Create implementation plans (read-only)
- summarize: Condense long content into concise summaries (read-only)
- worker: General-purpose implementation worker (read-write)
- research: Deep research with web access (read-only)
- coordinator: Coordinate multiple agents via channels (read-only)
- critic: Review and critique code, plans, or outputs (read-only)
- memory_read: Retrieve from memory (read-only)
- memory_write: Store to memory (read-write)
- response: Generate user responses (output sub-agent)

Usage:
    from kohakuterrarium.builtins.subagents import get_builtin_subagent_config, BUILTIN_SUBAGENTS

    config = get_builtin_subagent_config("explore")
    manager.register(config)

    # Or register all builtins
    for name in BUILTIN_SUBAGENTS:
        config = get_builtin_subagent_config(name)
        manager.register(config)
"""

from kohakuterrarium.builtins.subagents.coordinator import COORDINATOR_CONFIG
from kohakuterrarium.builtins.subagents.critic import CRITIC_CONFIG
from kohakuterrarium.builtins.subagents.explore import EXPLORE_CONFIG
from kohakuterrarium.builtins.subagents.memory_read import MEMORY_READ_CONFIG
from kohakuterrarium.builtins.subagents.memory_write import MEMORY_WRITE_CONFIG
from kohakuterrarium.builtins.subagents.plan import PLAN_CONFIG
from kohakuterrarium.builtins.subagents.research import RESEARCH_CONFIG
from kohakuterrarium.builtins.subagents.response import RESPONSE_CONFIG
from kohakuterrarium.builtins.subagents.summarize import SUMMARIZE_CONFIG
from kohakuterrarium.builtins.subagents.worker import WORKER_CONFIG
from kohakuterrarium.modules.subagent.config import SubAgentConfig

# All builtin sub-agent configurations
_BUILTIN_CONFIGS: dict[str, SubAgentConfig] = {
    "coordinator": COORDINATOR_CONFIG,
    "critic": CRITIC_CONFIG,
    "explore": EXPLORE_CONFIG,
    "plan": PLAN_CONFIG,
    "research": RESEARCH_CONFIG,
    "memory_read": MEMORY_READ_CONFIG,
    "memory_write": MEMORY_WRITE_CONFIG,
    "response": RESPONSE_CONFIG,
    "summarize": SUMMARIZE_CONFIG,
    "worker": WORKER_CONFIG,
}

# List of available builtin sub-agents
BUILTIN_SUBAGENTS = list(_BUILTIN_CONFIGS.keys())


def get_builtin_subagent_config(name: str) -> SubAgentConfig | None:
    """
    Get a builtin sub-agent configuration by name.

    Args:
        name: Sub-agent name

    Returns:
        SubAgentConfig or None if not found
    """
    return _BUILTIN_CONFIGS.get(name)


def list_builtin_subagents() -> list[str]:
    """List all available builtin sub-agent names."""
    return BUILTIN_SUBAGENTS.copy()


__all__ = [
    "BUILTIN_SUBAGENTS",
    "COORDINATOR_CONFIG",
    "CRITIC_CONFIG",
    "EXPLORE_CONFIG",
    "MEMORY_READ_CONFIG",
    "MEMORY_WRITE_CONFIG",
    "PLAN_CONFIG",
    "RESEARCH_CONFIG",
    "RESPONSE_CONFIG",
    "SUMMARIZE_CONFIG",
    "WORKER_CONFIG",
    "get_builtin_subagent_config",
    "list_builtin_subagents",
]

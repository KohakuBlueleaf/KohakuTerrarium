"""
Builtin sub-agent configurations (convenience re-exports).

All real logic lives in ``builtins.subagent_catalog``. This module
re-exports for backward compatibility and convenience.
"""

from kohakuterrarium.builtins.subagent_catalog import (
    BUILTIN_SUBAGENTS,
    get_builtin_subagent_config,
    list_builtin_subagents,
)
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

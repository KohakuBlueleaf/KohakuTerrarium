"""
Core module - fundamental abstractions and runtime components.

Exports:
- Agent: Main agent orchestrator
- AgentConfig: Agent configuration
- ModuleLoader: Load custom modules from agent folders
- TriggerEvent: Universal event type for all components
- EventType: Common event type constants
- Conversation: Message history management
- Controller: Main LLM orchestration loop
- Executor: Background tool execution
- JobStatus, JobResult: Job tracking
- Registry: Module registration
"""

from kohakuterrarium.core.config import (
    AgentConfig,
    InputConfig,
    OutputConfig,
    ToolConfigItem,
    TriggerConfig,
    load_agent_config,
)
from kohakuterrarium.core.conversation import Conversation, ConversationConfig
from kohakuterrarium.core.controller import (
    Controller,
    ControllerConfig,
    ControllerContext,
)
from kohakuterrarium.core.environment import Environment
from kohakuterrarium.core.events import (
    EventType,
    TriggerEvent,
    create_error_event,
    create_tool_complete_event,
    create_user_input_event,
)
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.job import (
    JobResult,
    JobState,
    JobStatus,
    JobStore,
    JobType,
    generate_job_id,
)
from kohakuterrarium.core.loader import (
    ModuleLoader,
    ModuleLoadError,
    load_custom_module,
)
from kohakuterrarium.core.registry import Registry, get_registry, register_tool

__all__ = [
    # Agent
    "Agent",
    "run_agent",
    # Environment
    "Environment",
    # Config
    "AgentConfig",
    "InputConfig",
    "OutputConfig",
    "ToolConfigItem",
    "TriggerConfig",
    "load_agent_config",
    # Events
    "TriggerEvent",
    "EventType",
    "create_user_input_event",
    "create_tool_complete_event",
    "create_error_event",
    # Conversation
    "Conversation",
    "ConversationConfig",
    # Controller
    "Controller",
    "ControllerConfig",
    "ControllerContext",
    # Executor
    "Executor",
    # Jobs
    "JobStatus",
    "JobResult",
    "JobState",
    "JobType",
    "JobStore",
    "generate_job_id",
    # Registry
    "Registry",
    "get_registry",
    "register_tool",
    # Loader
    "ModuleLoader",
    "ModuleLoadError",
    "load_custom_module",
]


def __getattr__(name: str):
    """Lazy imports for modules that would cause circular import chains."""
    if name in ("Agent", "run_agent"):
        from kohakuterrarium.core.agent import Agent, run_agent

        globals()["Agent"] = Agent
        globals()["run_agent"] = run_agent
        return Agent if name == "Agent" else run_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

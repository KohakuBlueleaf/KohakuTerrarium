"""
Core module - fundamental abstractions and runtime components.

Exports:
- TriggerEvent: Universal event type for all components
- EventType: Common event type constants
- Conversation: Message history management
- Controller: Main LLM orchestration loop
- Executor: Background tool execution
- JobStatus, JobResult: Job tracking
- Registry: Module registration
"""

from kohakuterrarium.core.conversation import Conversation, ConversationConfig
from kohakuterrarium.core.controller import (
    Controller,
    ControllerConfig,
    ControllerContext,
)
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
from kohakuterrarium.core.registry import Registry, get_registry, register_tool

__all__ = [
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
]

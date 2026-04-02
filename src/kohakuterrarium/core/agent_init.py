"""
Agent component initialization.

Contains mixin methods for initializing all agent subsystems
(LLM, registry, executor, input, output, triggers, sub-agents).
Separated from the main Agent class to keep file sizes manageable.

Heavy initialization logic is delegated to bootstrap.* factory modules
to reduce import fan-out.
"""

from kohakuterrarium.bootstrap.io import create_input, create_output
from kohakuterrarium.bootstrap.llm import create_llm_provider
from kohakuterrarium.bootstrap.subagents import init_subagents
from kohakuterrarium.bootstrap.tools import init_tools
from kohakuterrarium.bootstrap.triggers import init_triggers
from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.core.controller import Controller, ControllerConfig
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.loader import ModuleLoader
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.core.session import get_session
from kohakuterrarium.modules.input.base import InputModule
from kohakuterrarium.modules.output.base import OutputModule
from kohakuterrarium.modules.output.router import OutputRouter
from kohakuterrarium.modules.subagent import SubAgentManager
from kohakuterrarium.parsing.format import (
    BRACKET_FORMAT,
    XML_FORMAT,
    ToolCallFormat,
)
from kohakuterrarium.prompt.aggregator import aggregate_system_prompt
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class AgentInitMixin:
    """
    Mixin providing component initialization for the Agent class.

    All _init_* and _create_* methods live here to keep the main Agent
    class focused on its public API and runtime loop.
    """

    config: AgentConfig
    _loader: ModuleLoader

    def _init_llm(self) -> None:
        """Initialize LLM provider based on auth_mode."""
        self.llm = create_llm_provider(self.config)

    def _init_registry(self) -> None:
        """Initialize module registry and register tools."""
        self.registry = Registry()
        init_tools(self.config, self.registry, self._loader)

    def _init_executor(self) -> None:
        """Initialize background executor."""
        self.executor = Executor()

        # Register tools from registry
        for tool_name in self.registry.list_tools():
            tool = self.registry.get_tool(tool_name)
            if tool:
                self.executor.register_tool(tool)

        # Wire session for ToolContext building
        # Use explicit session if provided, else create from session_key
        explicit = getattr(self, "_explicit_session", None)
        if explicit is not None:
            self.session = explicit
        else:
            session_key = self.config.session_key or self.config.name
            self.session = get_session(session_key)

        # Backward-compatible accessors
        self.channel_registry = self.session.channels
        self.scratchpad = self.session.scratchpad

        # Set executor context
        self.executor._agent = self
        self.executor._agent_name = self.config.name
        self.executor._session = self.session
        self.executor._environment = getattr(self, "environment", None)
        self.executor._tool_format = (
            self.config.tool_format
            if isinstance(self.config.tool_format, str)
            else "bracket"
        )
        if self.config.agent_path:
            self.executor._working_dir = self.config.agent_path
        if hasattr(self.config, "agent_path") and self.config.agent_path:
            memory_config = getattr(self.config, "memory", None)
            if isinstance(memory_config, dict) and memory_config.get("path"):
                self.executor._memory_path = (
                    self.config.agent_path / memory_config["path"]
                )

    def _init_subagents(self) -> None:
        """Initialize sub-agent manager and register sub-agents."""
        # Pass parent's tool_format so sub-agents inherit it
        parent_tool_format = (
            self.config.tool_format
            if isinstance(self.config.tool_format, str)
            else "bracket"
        )

        self.subagent_manager = SubAgentManager(
            parent_registry=self.registry,
            llm=self.llm,
            agent_path=self.config.agent_path,
            job_store=self.executor.job_store,  # Share job store so wait command works
            max_depth=self.config.max_subagent_depth,
            tool_format=parent_tool_format,
        )

        init_subagents(
            self.config, self.subagent_manager, self.registry, self._loader
        )

    def _resolve_tool_format(self) -> ToolCallFormat | None:
        """
        Resolve tool_format config to a ToolCallFormat instance.

        Returns:
            ToolCallFormat for bracket/xml/custom, or None for native mode
            (native mode bypasses the stream parser entirely).
        """
        fmt = self.config.tool_format
        if isinstance(fmt, str):
            match fmt:
                case "bracket":
                    return BRACKET_FORMAT
                case "xml":
                    return XML_FORMAT
                case "native":
                    return None  # Native mode bypasses parser
                case _:
                    logger.warning(
                        "Unknown tool_format, using bracket", tool_format=fmt
                    )
                    return BRACKET_FORMAT
        elif isinstance(fmt, dict):
            return ToolCallFormat(**fmt)
        return BRACKET_FORMAT

    def _init_controller(self) -> None:
        """Initialize controller."""
        # Build system prompt
        # Aggregator auto-adds: tool list (name + description), framework hints
        # system.md should only contain agent personality/guidelines
        base_prompt = self.config.system_prompt

        # Add sub-agents section if any registered (respects include_tools_in_prompt)
        if self.config.include_tools_in_prompt:
            subagents_prompt = self.subagent_manager.get_subagents_prompt()
            if subagents_prompt:
                base_prompt = base_prompt + "\n\n" + subagents_prompt

        known_outputs = getattr(self, "_known_outputs", set())

        # Resolve tool format from config
        self._tool_format = self._resolve_tool_format()
        tool_format_name = (
            self.config.tool_format
            if isinstance(self.config.tool_format, str)
            else "custom"
        )

        logger.debug(
            "Building system prompt",
            known_outputs=known_outputs,
            tool_format=tool_format_name,
        )
        system_prompt = aggregate_system_prompt(
            base_prompt,
            self.registry,
            include_tools=self.config.include_tools_in_prompt,
            include_hints=self.config.include_hints_in_prompt,
            tool_format=tool_format_name,
            known_outputs=known_outputs,
        )

        # Store controller config for creating controllers on-demand (parallel mode)
        self._controller_config = ControllerConfig(
            system_prompt=system_prompt,
            include_job_status=True,
            include_tools_list=False,  # Already in aggregated prompt
            max_messages=self.config.max_messages,
            max_context_chars=self.config.max_context_chars,
            ephemeral=self.config.ephemeral,
            known_outputs=getattr(self, "_known_outputs", set()),
            tool_format=tool_format_name,
        )

        # Primary controller (always exists)
        # Note: Controller handles framework commands (read, info, jobs, wait)
        # via its own _commands dict and ControllerContext
        self.controller = self._create_controller()

    def _create_controller(self) -> Controller:
        """Create a new controller instance (for parallel processing)."""
        return Controller(
            self.llm,
            self._controller_config,
            executor=self.executor,
            registry=self.registry,
        )

    def _init_input(self, custom_input: InputModule | None) -> None:
        """Initialize input module."""
        self.input = create_input(self.config, custom_input, self._loader)

    def _init_output(self, custom_output: OutputModule | None) -> None:
        """Initialize output modules (default and named)."""
        default_output, named_outputs = create_output(
            self.config, custom_output, self._loader
        )

        # Store known outputs for parser config
        self._known_outputs = set(named_outputs.keys())
        logger.info("Named outputs registered", named_outputs=list(self._known_outputs))

        self.output_router = OutputRouter(default_output, named_outputs=named_outputs)

    def _init_triggers(self) -> None:
        """Initialize trigger modules from config into trigger_manager."""
        session = getattr(self, "session", None)
        init_triggers(
            self.config, self.trigger_manager, session, self._loader
        )

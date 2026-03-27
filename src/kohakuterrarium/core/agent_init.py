"""
Agent component initialization.

Contains mixin methods for initializing all agent subsystems
(LLM, registry, executor, input, output, triggers, sub-agents).
Separated from the main Agent class to keep file sizes manageable.
"""

from typing import Any

from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.core.controller import Controller, ControllerConfig
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.loader import ModuleLoadError, ModuleLoader
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.openai import OpenAIProvider
from kohakuterrarium.builtins.inputs import (
    CLIInput,
    create_builtin_input,
    is_builtin_input,
)
from kohakuterrarium.builtins.outputs import (
    StdoutOutput,
    create_builtin_output,
    is_builtin_output,
)
from kohakuterrarium.builtins.tools import get_builtin_tool
from kohakuterrarium.modules.input.base import InputModule
from kohakuterrarium.modules.output.base import OutputModule
from kohakuterrarium.modules.output.router import OutputRouter
from kohakuterrarium.modules.trigger import BaseTrigger
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
        """Initialize LLM provider."""
        api_key = self.config.get_api_key()
        if not api_key:
            raise ValueError(
                f"API key not found. Set {self.config.api_key_env} environment variable."
            )

        self.llm = OpenAIProvider(
            api_key=api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    def _init_registry(self) -> None:
        """Initialize module registry and register tools."""
        self.registry = Registry()

        # Register tools based on config
        for tool_config in self.config.tools:
            tool = self._create_tool(tool_config)
            if tool:
                self.registry.register_tool(tool)

    def _create_tool(self, tool_config: Any) -> Any:
        """Create a tool from config (builtin, custom, or package)."""
        match tool_config.type:
            case "builtin":
                tool = get_builtin_tool(tool_config.name)
                if tool is None:
                    logger.warning("Unknown built-in tool", tool_name=tool_config.name)
                return tool

            case "custom" | "package":
                if not tool_config.module or not tool_config.class_name:
                    logger.warning(
                        "Custom tool missing module or class",
                        tool_name=tool_config.name,
                    )
                    return None
                try:
                    return self._loader.load_instance(
                        module_path=tool_config.module,
                        class_name=tool_config.class_name,
                        module_type=tool_config.type,
                        options=tool_config.options,
                    )
                except ModuleLoadError as e:
                    logger.error("Failed to load custom tool", error=str(e))
                    return None

            case _:
                logger.warning("Unknown tool type", tool_type=tool_config.type)
                return None

    def _init_executor(self) -> None:
        """Initialize background executor."""
        self.executor = Executor()

        # Register tools from registry
        for tool_name in self.registry.list_tools():
            tool = self.registry.get_tool(tool_name)
            if tool:
                self.executor.register_tool(tool)

    def _init_subagents(self) -> None:
        """Initialize sub-agent manager and register sub-agents."""
        # Import here to avoid circular imports (subagent -> core/conversation -> core/__init__ -> agent)
        from kohakuterrarium.builtins.subagents import get_builtin_subagent_config
        from kohakuterrarium.modules.subagent import SubAgentManager

        self.subagent_manager = SubAgentManager(
            parent_registry=self.registry,
            llm=self.llm,
            agent_path=self.config.agent_path,
            job_store=self.executor.job_store,  # Share job store so wait command works
        )

        # Register sub-agents from config
        for subagent_item in self.config.subagents:
            config = self._create_subagent_config(
                subagent_item, get_builtin_subagent_config
            )
            if config:
                self.subagent_manager.register(config)
                # Also register with registry so parser knows about it
                self.registry.register_subagent(config.name, config)

        if self.subagent_manager.list_subagents():
            logger.info(
                "Sub-agents registered",
                subagents=self.subagent_manager.list_subagents(),
            )

    def _create_subagent_config(self, item: Any, get_builtin: Any) -> Any:
        """Create a SubAgentConfig from config item."""
        from kohakuterrarium.modules.subagent.config import SubAgentConfig

        match item.type:
            case "builtin":
                config = get_builtin(item.name)
                if config is None:
                    logger.warning("Unknown builtin sub-agent", subagent_name=item.name)
                return config

            case "custom" | "package":
                # If module and config_name provided, load from module
                if item.module and item.config_name:
                    try:
                        return self._loader.load_config_object(
                            module_path=item.module,
                            object_name=item.config_name,
                            module_type=item.type,
                        )
                    except ModuleLoadError as e:
                        logger.error("Failed to load custom sub-agent", error=str(e))
                        return None

                # Otherwise, create inline config from options
                config_dict = {
                    "name": item.name,
                    "description": item.description or f"{item.name} sub-agent",
                    "tools": item.tools,
                    "can_modify": item.can_modify,
                    "interactive": item.interactive,
                    **item.options,
                }
                return SubAgentConfig.from_dict(config_dict)

            case _:
                logger.warning("Unknown sub-agent type", subagent_type=item.type)
                return None

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
        logger.debug("Building system prompt", known_outputs=known_outputs)
        system_prompt = aggregate_system_prompt(
            base_prompt,
            self.registry,
            include_tools=self.config.include_tools_in_prompt,
            include_hints=self.config.include_hints_in_prompt,
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
        if custom_input:
            self.input = custom_input
        else:
            input_type = self.config.input.type
            options = {
                "prompt": self.config.input.prompt,
                **self.config.input.options,
            }

            # Check if it's a builtin input type
            if is_builtin_input(input_type):
                try:
                    self.input = create_builtin_input(input_type, options)
                except Exception as e:
                    logger.error(
                        "Failed to create builtin input",
                        input_type=input_type,
                        error=str(e),
                    )
                    self.input = CLIInput(prompt=self.config.input.prompt)
            elif input_type in ("custom", "package"):
                # Load custom/package input
                if not self.config.input.module or not self.config.input.class_name:
                    logger.warning("Custom input missing module or class, using CLI")
                    self.input = CLIInput(prompt=self.config.input.prompt)
                else:
                    try:
                        self.input = self._loader.load_instance(
                            module_path=self.config.input.module,
                            class_name=self.config.input.class_name,
                            module_type=input_type,
                            options=self.config.input.options,
                        )
                    except ModuleLoadError as e:
                        logger.error("Failed to load custom input", error=str(e))
                        self.input = CLIInput(prompt=self.config.input.prompt)
            else:
                # Unknown type, default to CLI
                logger.warning("Unknown input type, using CLI", input_type=input_type)
                self.input = CLIInput(prompt=self.config.input.prompt)

    def _init_output(self, custom_output: OutputModule | None) -> None:
        """Initialize output modules (default and named)."""
        # Create default output module
        if custom_output:
            default_output = custom_output
        else:
            default_output = self._create_output_module(
                output_type=self.config.output.type,
                module_path=self.config.output.module,
                class_name=self.config.output.class_name,
                options=self.config.output.options.copy(),
            )

        # Create named output modules
        named_outputs: dict[str, OutputModule] = {}
        for name, output_config in self.config.output.named_outputs.items():
            output_module = self._create_output_module(
                output_type=output_config.type,
                module_path=output_config.module,
                class_name=output_config.class_name,
                options=output_config.options.copy(),
            )
            named_outputs[name] = output_module
            logger.debug("Named output registered", output_name=name)

        # Store known outputs for parser config
        self._known_outputs = set(named_outputs.keys())
        logger.info("Named outputs registered", named_outputs=list(self._known_outputs))

        self.output_router = OutputRouter(default_output, named_outputs=named_outputs)

    def _create_output_module(
        self,
        output_type: str,
        module_path: str | None,
        class_name: str | None,
        options: dict,
    ) -> OutputModule:
        """Create a single output module from config."""
        if is_builtin_output(output_type):
            try:
                return create_builtin_output(output_type, options)
            except Exception as e:
                logger.error(
                    "Failed to create builtin output",
                    output_type=output_type,
                    error=str(e),
                )
                return StdoutOutput()

        if output_type in ("custom", "package"):
            if not module_path or not class_name:
                logger.warning("Custom output missing module or class, using stdout")
                return StdoutOutput()
            try:
                return self._loader.load_instance(
                    module_path=module_path,
                    class_name=class_name,
                    module_type=output_type,
                    options=options,
                )
            except ModuleLoadError as e:
                logger.error("Failed to load custom output", error=str(e))
                return StdoutOutput()

        # Unknown type
        logger.warning("Unknown output type, using stdout", output_type=output_type)
        return StdoutOutput()

    def _init_triggers(self) -> None:
        """Initialize trigger modules from config."""
        self._triggers: list[BaseTrigger] = []
        self._trigger_tasks: list = []

        for trigger_config in self.config.triggers:
            trigger = self._create_trigger(trigger_config)
            if trigger:
                self._triggers.append(trigger)
                logger.debug(
                    "Registered trigger",
                    trigger_type=trigger_config.type,
                    trigger_class=trigger_config.class_name,
                )

        if self._triggers:
            logger.info("Triggers registered", count=len(self._triggers))

    def _create_trigger(self, trigger_config: Any) -> BaseTrigger | None:
        """Create a trigger from config."""
        if trigger_config.type in ("custom", "package"):
            if not trigger_config.module or not trigger_config.class_name:
                logger.warning("Custom trigger missing module or class")
                return None

            try:
                trigger = self._loader.load_instance(
                    module_path=trigger_config.module,
                    class_name=trigger_config.class_name,
                    module_type=trigger_config.type,
                    options={
                        "prompt": trigger_config.prompt,
                        **trigger_config.options,
                    },
                )
                return trigger
            except ModuleLoadError as e:
                logger.error("Failed to load custom trigger", error=str(e))
                return None
        else:
            # TODO: Add builtin triggers (timer, idle, etc.)
            logger.warning("Unknown trigger type", trigger_type=trigger_config.type)
            return None

"""
Agent - Main orchestrator that wires all components together.

The Agent class is the top-level entry point for running an agent.
It manages the lifecycle of all modules and the main event loop.
"""

import asyncio
from typing import Any

from kohakuterrarium.core.config import AgentConfig, load_agent_config
from kohakuterrarium.core.controller import Controller, ControllerConfig
from kohakuterrarium.core.events import (
    EventType,
    TriggerEvent,
    create_tool_complete_event,
)
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.loader import ModuleLoader, ModuleLoadError
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
from kohakuterrarium.commands.read import InfoCommand, ReadCommand
from kohakuterrarium.parsing import (
    CommandEvent,
    ParseEvent,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
)
from kohakuterrarium.prompt.aggregator import aggregate_system_prompt
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class _CommandContext:
    """Context object passed to framework commands."""

    def __init__(
        self,
        executor: "Executor",
        registry: "Registry",
        agent_path: Any = None,
    ):
        self._executor = executor
        self._registry = registry
        self.agent_path = agent_path

    def get_job_result(self, job_id: str) -> Any:
        """Get job result by ID."""
        return self._executor.get_result(job_id)

    def get_job_status(self, job_id: str) -> Any:
        """Get job status by ID."""
        return self._executor.get_status(job_id)

    def get_tool_info(self, tool_name: str) -> Any:
        """Get tool info by name."""
        return self._registry.get_tool_info(tool_name)

    def get_tool(self, tool_name: str) -> Any:
        """Get tool instance by name."""
        return self._registry.get_tool(tool_name)


class Agent:
    """
    Main agent orchestrator.

    Wires together:
    - LLM provider
    - Controller (conversation loop)
    - Executor (tool execution)
    - Input module
    - Output router

    Usage:
        # From config path (recommended)
        agent = Agent.from_path("agents/my_agent")
        await agent.run()

        # Programmatic usage
        agent = Agent.from_path("agents/my_agent")
        await agent.start()

        # Inject events programmatically
        await agent.inject_input("Hello!")

        # Set custom output handler
        agent.set_output_handler(lambda text: print(f"AI: {text}"))

        # Monitor state
        print(f"Running: {agent.is_running}")
        print(f"Tools: {agent.tools}")

        await agent.stop()
    """

    @classmethod
    def from_path(
        cls,
        config_path: str,
        *,
        input_module: InputModule | None = None,
        output_module: OutputModule | None = None,
    ) -> "Agent":
        """
        Create agent from config directory path.

        Args:
            config_path: Path to agent config folder (e.g., "agents/my_agent")
            input_module: Custom input module (overrides config)
            output_module: Custom output module (overrides config)

        Returns:
            Configured Agent instance
        """
        config = load_agent_config(config_path)
        return cls(config, input_module=input_module, output_module=output_module)

    def __init__(
        self,
        config: AgentConfig,
        *,
        input_module: InputModule | None = None,
        output_module: OutputModule | None = None,
    ):
        """
        Initialize agent from config.

        Args:
            config: Agent configuration
            input_module: Custom input module (uses config if None)
            output_module: Custom output module (uses config if None)
        """
        self.config = config
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Module loader for custom components
        self._loader = ModuleLoader(agent_path=config.agent_path)

        # Initialize components
        self._init_llm()
        self._init_registry()
        self._init_executor()
        self._init_subagents()
        self._init_controller()
        self._init_commands()
        self._init_input(input_module)
        self._init_output(output_module)
        self._init_triggers()

        logger.info(
            "Agent initialized",
            agent_name=config.name,
            model=config.model,
            tools=len(self.registry.list_tools()),
            triggers=len(self._triggers),
        )

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

        # Add sub-agents section if any registered
        subagents_prompt = self.subagent_manager.get_subagents_prompt()
        if subagents_prompt:
            base_prompt = base_prompt + "\n\n" + subagents_prompt

        system_prompt = aggregate_system_prompt(
            base_prompt,
            self.registry,
            include_tools=True,
            include_hints=True,
        )

        controller_config = ControllerConfig(
            system_prompt=system_prompt,
            include_job_status=True,
            include_tools_list=False,  # Already in aggregated prompt
            max_messages=self.config.max_messages,
            max_context_chars=self.config.max_context_chars,
        )

        self.controller = Controller(
            self.llm,
            controller_config,
            executor=self.executor,
            registry=self.registry,
        )

    def _init_commands(self) -> None:
        """Initialize framework commands."""
        self._commands: dict[str, Any] = {
            "read": ReadCommand(),
            "info": InfoCommand(),
        }

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
        """Initialize output module."""
        if custom_output:
            output_module = custom_output
        else:
            output_type = self.config.output.type
            options = self.config.output.options.copy()

            # Check if it's a builtin output type
            if is_builtin_output(output_type):
                try:
                    output_module = create_builtin_output(output_type, options)
                except Exception as e:
                    logger.error(
                        "Failed to create builtin output",
                        output_type=output_type,
                        error=str(e),
                    )
                    output_module = StdoutOutput()
            elif output_type in ("custom", "package"):
                # Load custom/package output
                if not self.config.output.module or not self.config.output.class_name:
                    logger.warning(
                        "Custom output missing module or class, using stdout"
                    )
                    output_module = StdoutOutput()
                else:
                    try:
                        output_module = self._loader.load_instance(
                            module_path=self.config.output.module,
                            class_name=self.config.output.class_name,
                            module_type=output_type,
                            options=options,
                        )
                    except ModuleLoadError as e:
                        logger.error("Failed to load custom output", error=str(e))
                        output_module = StdoutOutput()
            else:
                # Unknown type, default to stdout
                logger.warning(
                    "Unknown output type, using stdout", output_type=output_type
                )
                output_module = StdoutOutput()

        self.output_router = OutputRouter(output_module)

    def _init_triggers(self) -> None:
        """Initialize trigger modules from config."""
        self._triggers: list[BaseTrigger] = []
        self._trigger_tasks: list[asyncio.Task] = []

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

    async def _run_trigger(self, trigger: BaseTrigger) -> None:
        """Run a single trigger loop."""
        while self._running:
            try:
                event = await trigger.wait_for_trigger()
                if event:
                    logger.info(
                        "Trigger fired",
                        trigger_type=event.type,
                    )
                    await self._process_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Trigger error", error=str(e))
                await asyncio.sleep(1.0)  # Backoff on error

    async def start(self) -> None:
        """Start all agent modules."""
        logger.info("Starting agent", agent_name=self.config.name)

        await self.input.start()
        await self.output_router.start()

        # Start triggers
        for trigger in self._triggers:
            await trigger.start()
            task = asyncio.create_task(self._run_trigger(trigger))
            self._trigger_tasks.append(task)

        if self._triggers:
            logger.info("Triggers started", count=len(self._triggers))

        self._running = True
        self._shutdown_event.clear()

    async def stop(self) -> None:
        """Stop all agent modules."""
        logger.info("Stopping agent", agent_name=self.config.name)

        self._running = False
        self._shutdown_event.set()

        # Stop triggers
        for task in self._trigger_tasks:
            task.cancel()
        if self._trigger_tasks:
            await asyncio.gather(*self._trigger_tasks, return_exceptions=True)
        for trigger in self._triggers:
            await trigger.stop()

        await self.input.stop()
        await self.output_router.stop()
        await self.llm.close()

    async def run(self) -> None:
        """
        Run the agent main loop.

        Handles:
        - Startup triggers
        - Getting input
        - Running controller
        - Processing tool calls
        - Routing output
        """
        await self.start()

        try:
            # Fire startup trigger if configured
            await self._fire_startup_trigger()

            idle_logged = False
            while self._running:
                # Get input
                if not idle_logged:
                    logger.debug("Agent idle, waiting for input...")
                    idle_logged = True
                event = await self.input.get_input()

                # Check for exit
                if event is None:
                    if (
                        hasattr(self.input, "exit_requested")
                        and self.input.exit_requested
                    ):
                        logger.info("Exit requested")
                        break
                    # Timeout or no input, continue waiting
                    continue

                # Process input through controller
                idle_logged = False  # Reset so we log idle again after processing
                logger.info(
                    "Input received, processing event",
                    event_type=event.type,
                    content_len=len(event.content) if event.content else 0,
                )
                await self._process_event(event)
                logger.debug("Event processing complete, returning to idle")

        except KeyboardInterrupt:
            logger.info("Interrupted")
        except Exception as e:
            logger.error("Agent error", error=str(e))
            raise
        finally:
            await self.stop()

    async def _fire_startup_trigger(self) -> None:
        """Fire startup trigger if configured."""
        startup_trigger = self.config.startup_trigger
        if not startup_trigger:
            return

        logger.info("Firing startup trigger")

        # Create startup event with configured prompt
        event = TriggerEvent(
            type=EventType.STARTUP,
            content=startup_trigger.get("prompt", "Agent starting up."),
            context={"trigger": "startup"},
            prompt_override=startup_trigger.get("prompt"),
            stackable=False,
        )

        await self._process_event(event)

    async def _process_event(self, event: TriggerEvent) -> None:
        """
        Process a single event through the controller.

        Loops until controller generates no new jobs.
        - Direct tools: wait for completion, feed results back
        - Background tools/sub-agents: report status, keep tracking until cleaned up

        A job is "cleaned up" when its result/status has been sent back to the model.
        """
        # Notify triggers of context update (for idle timer reset, etc.)
        for trigger in self._triggers:
            try:
                trigger._on_context_update(event.context)
            except Exception:
                pass  # Don't let trigger errors break event processing

        await self.controller.push_event(event)

        # Track non-direct jobs that haven't been cleaned up yet
        # These persist across loop iterations until their results are acknowledged
        pending_background_ids: list[str] = []
        pending_subagent_ids: list[str] = []

        while True:
            # Reset output for this turn
            self.output_router.reset()
            if hasattr(self.output_router.default_output, "reset"):
                self.output_router.default_output.reset()

            # Track ALL jobs started during THIS generation
            direct_tasks: dict[str, asyncio.Task] = {}
            direct_job_ids: list[str] = []
            new_background_ids: list[str] = []
            new_subagent_ids: list[str] = []

            # Run controller and process output
            async for parse_event in self.controller.run_once():
                if isinstance(parse_event, ToolCallEvent):
                    job_id, task, is_direct = await self._start_tool_async(parse_event)
                    if is_direct:
                        direct_tasks[job_id] = task
                        direct_job_ids.append(job_id)
                    else:
                        new_background_ids.append(job_id)
                    logger.debug(
                        "Tool started",
                        tool_name=parse_event.name,
                        job_id=job_id,
                        direct=is_direct,
                    )
                elif isinstance(parse_event, SubAgentCallEvent):
                    job_id = await self._start_subagent_async(parse_event)
                    new_subagent_ids.append(job_id)
                else:
                    await self.output_router.route(parse_event)

            # Flush output
            await self.output_router.flush()

            # Handle pending commands
            commands = self.output_router.pending_commands
            for cmd in commands:
                await self._handle_command(cmd)

            # Check if ANY jobs were started this round
            jobs_started_this_round = bool(
                direct_tasks or new_background_ids or new_subagent_ids
            )

            # Add new non-direct jobs to pending lists
            pending_background_ids.extend(new_background_ids)
            pending_subagent_ids.extend(new_subagent_ids)

            # If no jobs started AND no pending non-direct jobs, we're done
            if (
                not jobs_started_this_round
                and not pending_background_ids
                and not pending_subagent_ids
            ):
                logger.debug(
                    "No jobs pending, exiting process loop",
                    jobs_this_round=jobs_started_this_round,
                    pending_bg=len(pending_background_ids),
                    pending_sa=len(pending_subagent_ids),
                )
                break

            # Build feedback for controller
            feedback_parts: list[str] = []

            # Wait for direct tools and collect results
            if direct_tasks:
                logger.info("Waiting for %d direct tool(s)", len(direct_tasks))
                results = await self._collect_tool_results(direct_job_ids, direct_tasks)
                if results:
                    feedback_parts.append(results)

            # Get status of pending background jobs (and clean up completed ones)
            if pending_background_ids or pending_subagent_ids:
                bg_status, pending_background_ids, pending_subagent_ids = (
                    self._get_and_cleanup_background_status(
                        pending_background_ids, pending_subagent_ids
                    )
                )
                if bg_status:
                    feedback_parts.append(bg_status)

            # Feed results back to controller for next iteration
            if feedback_parts:
                combined = "\n\n".join(feedback_parts)
                feedback_event = create_tool_complete_event(
                    job_id="batch",
                    content=combined,
                    exit_code=0,
                    error=None,
                )
                logger.debug(
                    "Pushing feedback to controller, continuing loop",
                    pending_bg=len(pending_background_ids),
                    pending_sa=len(pending_subagent_ids),
                )
                await self.controller.push_event(feedback_event)
            else:
                # No feedback to send but we have pending jobs - just continue
                # This shouldn't normally happen
                logger.warning(
                    "No feedback but had pending jobs, unexpected break",
                    pending_bg=len(pending_background_ids),
                    pending_sa=len(pending_subagent_ids),
                )
                break

    async def _start_tool_async(
        self, tool_call: ToolCallEvent
    ) -> tuple[str, asyncio.Task, bool]:
        """
        Start a tool execution immediately as an async task.

        Does NOT wait for completion - returns task handle.

        Args:
            tool_call: Tool call event from parser

        Returns:
            (job_id, task, is_direct) tuple - is_direct indicates if we should wait
        """
        logger.info("Running tool: %s", tool_call.name)

        # Check if tool is direct (blocking) or background
        tool = self.executor.get_tool(tool_call.name)
        is_direct = True  # Default to direct
        if tool and hasattr(tool, "execution_mode"):
            from kohakuterrarium.modules.tool.base import ExecutionMode

            is_direct = tool.execution_mode == ExecutionMode.DIRECT

        # Submit to executor - this creates the task internally
        job_id = await self.executor.submit_from_event(tool_call)

        # Get the task handle from executor
        task = self.executor._tasks.get(job_id)
        if task is None:
            # Fallback: create a dummy completed task if already done
            async def _get_result():
                return self.executor.get_result(job_id)

            task = asyncio.create_task(_get_result())

        return job_id, task, is_direct

    async def _collect_tool_results(
        self,
        job_ids: list[str],
        tasks: dict[str, asyncio.Task],
    ) -> str:
        """
        Wait for all tools to complete and return formatted results.

        Args:
            job_ids: List of job IDs in order
            tasks: Dict of job_id -> asyncio.Task

        Returns:
            Formatted results string
        """
        if not tasks:
            return ""

        # Wait for all tasks in parallel
        results_list = await asyncio.gather(
            *[tasks[jid] for jid in job_ids],
            return_exceptions=True,
        )

        # Format results
        result_strs: list[str] = []
        for job_id, result in zip(job_ids, results_list):
            if isinstance(result, Exception):
                result_strs.append(f"## {job_id} - FAILED\n{str(result)}")
                logger.info("Tool %s: failed", job_id.split("_")[0])
            elif result is not None:
                output = result.output[:2000] if result.output else ""
                if result.error:
                    result_strs.append(f"## {job_id} - ERROR\n{result.error}\n{output}")
                    logger.info("Tool %s: error", job_id.split("_")[0])
                else:
                    status = (
                        "OK" if result.exit_code == 0 else f"exit={result.exit_code}"
                    )
                    result_strs.append(f"## {job_id} - {status}\n{output}")
                    logger.info("Tool %s: done", job_id.split("_")[0])

        return "\n\n".join(result_strs) if result_strs else ""

    def _get_and_cleanup_background_status(
        self,
        background_job_ids: list[str],
        subagent_job_ids: list[str],
    ) -> tuple[str, list[str], list[str]]:
        """
        Get status of background jobs and sub-agents, cleaning up completed ones.

        Completed jobs are removed from the pending lists after their status
        is included in the output (so the model sees the result once).

        Returns:
            (status_string, remaining_background_ids, remaining_subagent_ids)
        """
        if not background_job_ids and not subagent_job_ids:
            return "", [], []

        status_lines: list[str] = []
        remaining_bg: list[str] = []
        remaining_sa: list[str] = []

        # Check background tools
        for job_id in background_job_ids:
            status = self.executor.get_status(job_id)
            if status:
                if status.is_complete:
                    # Completed - include result and DON'T add to remaining
                    result = self.executor.get_result(job_id)
                    if result and result.error:
                        status_lines.append(f"- `{job_id}`: ERROR - {result.error}")
                    else:
                        output = result.output[:500] if result and result.output else ""
                        status_lines.append(f"- `{job_id}`: DONE\n{output}")
                else:
                    # Still running - keep tracking
                    status_lines.append(f"- `{job_id}`: {status.state.value}")
                    remaining_bg.append(job_id)

        # Check sub-agents
        for job_id in subagent_job_ids:
            if job_id.startswith("error_"):
                # Error during spawn - don't keep tracking
                status_lines.append(f"- `{job_id}`: ERROR - Sub-agent not registered")
                continue

            result = self.subagent_manager.get_result(job_id)
            if result:
                # Completed - include result and DON'T add to remaining
                if result.success:
                    output = result.truncated(max_chars=500)
                    status_lines.append(
                        f"- `{job_id}`: DONE (turns={result.turns})\n{output}"
                    )
                else:
                    status_lines.append(f"- `{job_id}`: ERROR - {result.error}")
            else:
                # Still running - keep tracking
                status_lines.append(f"- `{job_id}`: RUNNING")
                remaining_sa.append(job_id)

        if not status_lines:
            return "", remaining_bg, remaining_sa

        return (
            "## Background Jobs\n\n" + "\n".join(status_lines),
            remaining_bg,
            remaining_sa,
        )

    async def _start_subagent_async(self, event: SubAgentCallEvent) -> str:
        """
        Start a sub-agent execution.

        Args:
            event: Sub-agent call event from parser

        Returns:
            Job ID
        """
        logger.info(
            "Starting sub-agent",
            subagent_type=event.name,
            task=event.args.get("task", "")[:50],
        )
        try:
            job_id = await self.subagent_manager.spawn_from_event(event)
            return job_id
        except ValueError as e:
            logger.error(
                "Sub-agent not registered", subagent_name=event.name, error=str(e)
            )
            return f"error_{event.name}"

    async def _handle_command(self, cmd: CommandEvent) -> None:
        """Execute a framework command and feed result back to controller."""
        logger.debug("Executing command", command=cmd.command)

        command_handler = self._commands.get(cmd.command)
        if command_handler is None:
            logger.warning("Unknown command", command=cmd.command)
            return

        try:
            # Create command context with access to job store, registry, and agent path
            context = _CommandContext(
                executor=self.executor,
                registry=self.registry,
                agent_path=self.config.agent_path,
            )

            # Execute command
            result = await command_handler.execute(cmd.args, context)

            if result.content:
                # Inject command result as system message
                completion = TriggerEvent(
                    type="command_result",
                    content=result.content,
                    context={"command": cmd.command},
                )
                await self._process_event(completion)
            elif result.error:
                logger.warning(
                    "Command error",
                    command=cmd.command,
                    error=result.error,
                )

        except Exception as e:
            logger.error("Command execution failed", command=cmd.command, error=str(e))

    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running

    # =========================================================================
    # Programmatic API
    # =========================================================================

    @property
    def tools(self) -> list[str]:
        """Get list of registered tool names."""
        return self.registry.list_tools()

    @property
    def subagents(self) -> list[str]:
        """Get list of registered sub-agent names."""
        return self.subagent_manager.list_subagents()

    @property
    def conversation_history(self) -> list[dict]:
        """Get conversation history as list of message dicts."""
        return self.controller.conversation.to_messages()

    async def inject_input(self, text: str, source: str = "programmatic") -> None:
        """
        Inject user input programmatically.

        Use this to send input without going through the input module.

        Args:
            text: Input text to inject
            source: Source identifier for context
        """
        from kohakuterrarium.core.events import create_user_input_event

        event = create_user_input_event(text, source=source)
        await self._process_event(event)

    async def inject_event(self, event: TriggerEvent) -> None:
        """
        Inject a custom event programmatically.

        Args:
            event: TriggerEvent to inject
        """
        await self._process_event(event)

    def set_output_handler(self, handler: Any, replace_default: bool = False) -> None:
        """
        Set a custom output handler callback.

        The handler receives text chunks as they're generated.

        Args:
            handler: Callable that receives (text: str) for each chunk
            replace_default: If True, replace default output; if False, add as secondary

        Example:
            agent.set_output_handler(lambda text: print(f"AI: {text}"))
        """
        # Create a simple callback output module
        from kohakuterrarium.modules.output.base import OutputModule

        class CallbackOutput(OutputModule):
            def __init__(self, callback: Any):
                self._callback = callback

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

            async def write(self, text: str) -> None:
                self._callback(text)

            async def write_line(self, text: str) -> None:
                self._callback(text + "\n")

        callback_output = CallbackOutput(handler)

        if replace_default:
            self.output_router.default_output = callback_output
        else:
            self.output_router.add_secondary(callback_output)

    def get_state(self) -> dict[str, Any]:
        """
        Get agent state for monitoring.

        Returns:
            Dict with agent state information
        """
        return {
            "name": self.config.name,
            "running": self._running,
            "tools": self.tools,
            "subagents": self.subagents,
            "message_count": len(self.conversation_history),
            "pending_jobs": len(self.executor._tasks) if self.executor else 0,
        }


async def run_agent(config_path: str) -> None:
    """
    Convenience function to run an agent from config path.

    Args:
        config_path: Path to agent config folder
    """
    config = load_agent_config(config_path)
    agent = Agent(config)
    await agent.run()

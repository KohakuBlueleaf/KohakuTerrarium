"""
Agent - Main orchestrator that wires all components together.

The Agent class is the top-level entry point for running an agent.
It manages the lifecycle of all modules and the main event loop.
"""

import asyncio
from typing import Any

from kohakuterrarium.core.config import AgentConfig, load_agent_config
from kohakuterrarium.core.controller import Controller, ControllerConfig
from kohakuterrarium.core.events import TriggerEvent, create_tool_complete_event
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.openai import OPENROUTER_BASE_URL, OpenAIProvider
from kohakuterrarium.modules.input.base import InputModule
from kohakuterrarium.modules.input.cli import CLIInput
from kohakuterrarium.modules.output.base import OutputModule
from kohakuterrarium.modules.output.router import OutputRouter
from kohakuterrarium.modules.output.stdout import StdoutOutput
from kohakuterrarium.modules.tool import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    PythonTool,
    ReadTool,
    WriteTool,
)
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
        config = load_agent_config("agents/my_agent")
        agent = Agent(config)
        await agent.run()
    """

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

        # Initialize components
        self._init_llm()
        self._init_registry()
        self._init_executor()
        self._init_controller()
        self._init_commands()
        self._init_input(input_module)
        self._init_output(output_module)

        logger.info(
            "Agent initialized",
            agent_name=config.name,
            model=config.model,
            tools=len(self.registry.list_tools()),
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

        # Register built-in tools based on config
        for tool_config in self.config.tools:
            if tool_config.type == "builtin":
                tool = self._create_builtin_tool(tool_config.name, tool_config.options)
                if tool:
                    self.registry.register_tool(tool)

    def _create_builtin_tool(self, name: str, options: dict[str, Any]) -> Any:
        """Create a built-in tool by name."""
        match name:
            case "bash":
                return BashTool()
            case "python":
                return PythonTool()
            case "read":
                return ReadTool()
            case "write":
                return WriteTool()
            case "edit":
                return EditTool()
            case "glob":
                return GlobTool()
            case "grep":
                return GrepTool()
            case _:
                logger.warning("Unknown built-in tool", tool_name=name)
                return None

    def _init_executor(self) -> None:
        """Initialize background executor."""
        self.executor = Executor()

        # Register tools from registry
        for tool_name in self.registry.list_tools():
            tool = self.registry.get_tool(tool_name)
            if tool:
                self.executor.register_tool(tool)

    def _init_controller(self) -> None:
        """Initialize controller."""
        # Build system prompt
        # Aggregator auto-adds: tool list (name + description), framework hints
        # system.md should only contain agent personality/guidelines
        system_prompt = aggregate_system_prompt(
            self.config.system_prompt,
            self.registry,
            include_tools=True,
            include_hints=True,
        )

        controller_config = ControllerConfig(
            system_prompt=system_prompt,
            include_job_status=True,
            include_tools_list=False,  # Already in aggregated prompt
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
            # Create from config
            match self.config.input.type:
                case "cli":
                    self.input = CLIInput(
                        prompt=self.config.input.prompt,
                        **self.config.input.options,
                    )
                case _:
                    # Default to CLI
                    self.input = CLIInput(prompt=self.config.input.prompt)

    def _init_output(self, custom_output: OutputModule | None) -> None:
        """Initialize output module."""
        if custom_output:
            output_module = custom_output
        else:
            # Create from config
            match self.config.output.type:
                case "stdout":
                    output_module = StdoutOutput(
                        prefix="",
                        suffix="\n",
                        **self.config.output.options,
                    )
                case _:
                    output_module = StdoutOutput()

        self.output_router = OutputRouter(output_module)

    async def start(self) -> None:
        """Start all agent modules."""
        logger.info("Starting agent", agent_name=self.config.name)

        await self.input.start()
        await self.output_router.start()

        self._running = True
        self._shutdown_event.clear()

    async def stop(self) -> None:
        """Stop all agent modules."""
        logger.info("Stopping agent", agent_name=self.config.name)

        self._running = False
        self._shutdown_event.set()

        await self.input.stop()
        await self.output_router.stop()
        await self.llm.close()

    async def run(self) -> None:
        """
        Run the agent main loop.

        Handles:
        - Getting input
        - Running controller
        - Processing tool calls
        - Routing output
        """
        await self.start()

        try:
            while self._running:
                # Get input
                event = await self.input.get_input()

                # Check for exit
                if event is None:
                    if (
                        hasattr(self.input, "exit_requested")
                        and self.input.exit_requested
                    ):
                        logger.info("Exit requested")
                        break
                    continue

                # Process input through controller
                await self._process_event(event)

        except KeyboardInterrupt:
            logger.info("Interrupted")
        except Exception as e:
            logger.error("Agent error", error=str(e))
            raise
        finally:
            await self.stop()

    async def _process_event(self, event: TriggerEvent) -> None:
        """Process a single event through the controller."""
        await self.controller.push_event(event)

        # Reset output for new turn
        self.output_router.reset()
        if hasattr(self.output_router.default_output, "reset"):
            self.output_router.default_output.reset()

        # Track running tool tasks (started during streaming)
        running_tasks: dict[str, asyncio.Task] = {}
        tool_job_ids: list[str] = []

        # Run controller and process output
        async for parse_event in self.controller.run_once():
            # Handle tool calls immediately - start async task right away
            if isinstance(parse_event, ToolCallEvent):
                job_id, task = await self._start_tool_async(parse_event)
                running_tasks[job_id] = task
                tool_job_ids.append(job_id)
                logger.debug(
                    "Tool started async", tool_name=parse_event.name, job_id=job_id
                )
            else:
                # Route other events (text, blocks, etc.)
                await self.output_router.route(parse_event)

        # Flush output
        await self.output_router.flush()

        # Wait for all direct tools to complete (parallel)
        if running_tasks:
            await self._wait_and_collect_results(tool_job_ids, running_tasks)

        # Handle pending commands
        commands = self.output_router.pending_commands
        for cmd in commands:
            await self._handle_command(cmd)

    async def _start_tool_async(
        self, tool_call: ToolCallEvent
    ) -> tuple[str, asyncio.Task]:
        """
        Start a tool execution immediately as an async task.

        Does NOT wait for completion - returns task handle.

        Args:
            tool_call: Tool call event from parser

        Returns:
            (job_id, task) tuple
        """
        logger.info("Starting tool", tool_name=tool_call.name)

        # Submit to executor - this creates the task internally
        job_id = await self.executor.submit_from_event(tool_call)

        # Get the task handle from executor
        task = self.executor._tasks.get(job_id)
        if task is None:
            # Fallback: create a dummy completed task if already done
            async def _get_result():
                return self.executor.get_result(job_id)

            task = asyncio.create_task(_get_result())

        return job_id, task

    async def _wait_and_collect_results(
        self,
        job_ids: list[str],
        tasks: dict[str, asyncio.Task],
    ) -> None:
        """
        Wait for all tools to complete in parallel and send results to controller.

        Args:
            job_ids: List of job IDs in order
            tasks: Dict of job_id -> asyncio.Task
        """
        if not tasks:
            return

        logger.info("Waiting for tools", count=len(tasks))

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
            elif result is not None:
                output = result.output[:2000] if result.output else ""
                if result.error:
                    result_strs.append(f"## {job_id} - ERROR\n{result.error}\n{output}")
                else:
                    status = (
                        "OK" if result.exit_code == 0 else f"exit={result.exit_code}"
                    )
                    result_strs.append(f"## {job_id} - {status}\n{output}")

        # Send combined results back to controller
        if result_strs:
            combined_content = "\n\n".join(result_strs)
            completion = create_tool_complete_event(
                job_id="batch",
                content=combined_content,
                exit_code=0,
                error=None,
            )
            await self._process_event(completion)

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


async def run_agent(config_path: str) -> None:
    """
    Convenience function to run an agent from config path.

    Args:
        config_path: Path to agent config folder
    """
    config = load_agent_config(config_path)
    agent = Agent(config)
    await agent.run()

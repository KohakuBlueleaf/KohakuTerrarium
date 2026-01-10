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
from kohakuterrarium.modules.tool import BashTool, PythonTool
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

        # Run controller and process output
        async for parse_event in self.controller.run_once():
            await self.output_router.route(parse_event)

        # Flush output
        await self.output_router.flush()

        # Handle pending tool calls
        tool_calls = self.output_router.pending_tool_calls
        if tool_calls:
            await self._handle_tool_calls(tool_calls)

        # Handle pending commands
        commands = self.output_router.pending_commands
        for cmd in commands:
            logger.debug("Command processed", command=cmd.command)

    async def _handle_tool_calls(self, tool_calls: list[ToolCallEvent]) -> None:
        """Execute tool calls and feed results back to controller."""
        for tool_call in tool_calls:
            logger.info("Executing tool", tool_name=tool_call.name)

            try:
                # Submit to executor
                job_id = await self.executor.submit_from_event(tool_call)

                # Wait for result
                result = await self.executor.wait_for(job_id, timeout=60.0)

                if result:
                    # Create completion event
                    completion = create_tool_complete_event(
                        job_id=job_id,
                        output=result.output[:2000] if result.output else "",
                        success=result.success,
                    )

                    # Process the result through controller
                    await self._process_event(completion)

            except Exception as e:
                logger.error(
                    "Tool execution failed", tool_name=tool_call.name, error=str(e)
                )

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

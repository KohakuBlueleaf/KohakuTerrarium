"""
Agent - Main orchestrator that wires all components together.

The Agent class is the top-level entry point for running an agent.
It manages the lifecycle of all modules and the main event loop.

Component initialization is in agent_init.py (AgentInitMixin).
Event handling and tool execution is in agent_handlers.py (AgentHandlersMixin).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from kohakuterrarium.core.agent_handlers import AgentHandlersMixin
from kohakuterrarium.core.agent_init import AgentInitMixin
from kohakuterrarium.core.config import AgentConfig, load_agent_config
from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.core.loader import ModuleLoader
from kohakuterrarium.core.session import Session
from kohakuterrarium.core.termination import TerminationChecker, TerminationConfig
from kohakuterrarium.modules.input.base import InputModule
from kohakuterrarium.modules.output.base import OutputModule
from kohakuterrarium.modules.trigger.base import BaseTrigger
from kohakuterrarium.utils.logging import get_logger

if TYPE_CHECKING:
    from kohakuterrarium.core.environment import Environment

logger = get_logger(__name__)


class Agent(AgentInitMixin, AgentHandlersMixin):
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
        session: Session | None = None,
        environment: Environment | None = None,
    ) -> Agent:
        """
        Create agent from config directory path.

        Args:
            config_path: Path to agent config folder (e.g., "agents/my_agent")
            input_module: Custom input module (overrides config)
            output_module: Custom output module (overrides config)
            session: Explicit session (creature-private state)
            environment: Shared environment (inter-creature state)

        Returns:
            Configured Agent instance
        """
        config = load_agent_config(config_path)
        return cls(
            config,
            input_module=input_module,
            output_module=output_module,
            session=session,
            environment=environment,
        )

    def __init__(
        self,
        config: AgentConfig,
        *,
        input_module: InputModule | None = None,
        output_module: OutputModule | None = None,
        session: Session | None = None,
        environment: Environment | None = None,
    ):
        """
        Initialize agent from config.

        Args:
            config: Agent configuration
            input_module: Custom input module (uses config if None)
            output_module: Custom output module (uses config if None)
            session: Explicit session (creature-private state). Created from
                     session_key if not provided.
            environment: Shared environment (inter-creature state). None for
                         standalone agents.
        """
        self.config = config
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._processing_lock = asyncio.Lock()

        # Environment and session (explicit or auto-created in _init_executor)
        self.environment: Environment | None = environment
        self._explicit_session: Session | None = session

        # Module loader for custom components
        self._loader = ModuleLoader(agent_path=config.agent_path)

        # Initialize termination checker
        self._termination_checker = self._init_termination()

        # Initialize components (methods from AgentInitMixin)
        # Order matters: output before controller (need known_outputs for parser)
        self._init_llm()
        self._init_registry()
        self._init_executor()
        self._init_subagents()
        self._init_output(output_module)  # Before controller - sets _known_outputs
        self._init_controller()
        self._init_input(input_module)
        self._init_triggers()

        logger.info(
            "Agent initialized",
            agent_name=config.name,
            model=config.model,
            tools=len(self.registry.list_tools()),
            triggers=len(self._triggers),
            ephemeral=config.ephemeral,
        )

    def _init_termination(self) -> TerminationChecker | None:
        """Initialize termination checker from config."""
        if not self.config.termination:
            return None

        tc = TerminationConfig(
            max_turns=self.config.termination.get("max_turns", 0),
            max_tokens=self.config.termination.get("max_tokens", 0),
            max_duration=self.config.termination.get("max_duration", 0),
            idle_timeout=self.config.termination.get("idle_timeout", 0),
            keywords=self.config.termination.get("keywords", []),
        )
        checker = TerminationChecker(tc)
        if checker.is_active:
            logger.info("Termination conditions configured", config=str(tc))
        return checker

    # =========================================================================
    # Lifecycle
    # =========================================================================

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

        if self._termination_checker:
            self._termination_checker.start()

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

                # Wait for EITHER user input OR background job completion
                if not idle_logged:
                    logger.debug(
                        "Agent idle, waiting for input or background results..."
                    )
                    idle_logged = True

                event = await self._wait_for_next_event()

                # Check for exit
                if event is None:
                    if (
                        hasattr(self.input, "exit_requested")
                        and self.input.exit_requested
                    ):
                        logger.info("Exit requested")
                        break
                    continue

                idle_logged = False
                # Log content length (handle multimodal)
                if event.is_multimodal():
                    content_len = len(event.get_text_content())
                    content_info = f"{content_len} chars + {len(event.content)} parts"
                else:
                    content_len = len(event.content) if event.content else 0
                    content_info = f"{content_len} chars"
                logger.info(
                    "Input received, processing event",
                    event_type=event.type,
                    content=content_info,
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

    async def _wait_for_next_event(self) -> TriggerEvent | None:
        """Wait for the next event from any source.

        Races user input against background job completions.
        Returns whichever arrives first. This allows the agent to
        be idle while background tools (like terrarium_observe) run,
        and wake up when either the user types or a background job
        delivers results.
        """
        input_task = asyncio.create_task(self.input.get_input())
        bg_task = asyncio.create_task(self.executor.get_next_event(timeout=None))

        done, pending = await asyncio.wait(
            {input_task, bg_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel the loser
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # Return the winner's result
        for task in done:
            try:
                return task.result()
            except Exception:
                return None

        return None

    # =========================================================================
    # Programmatic API
    # =========================================================================

    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running

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

            async def write_stream(self, chunk: str) -> None:
                self._callback(chunk)

            async def flush(self) -> None:
                pass

            async def on_processing_start(self) -> None:
                pass

            async def on_processing_end(self) -> None:
                pass

            def on_activity(self, activity_type: str, detail: str) -> None:
                pass

        callback_output = CallbackOutput(handler)

        if replace_default:
            self.output_router.default_output = callback_output
        else:
            self.output_router.add_secondary(callback_output)

    # =========================================================================
    # Hot-plug API
    # =========================================================================

    async def add_trigger(self, trigger: BaseTrigger) -> None:
        """Add and start a trigger on a running agent.

        Can be called while the agent is running. The trigger will
        immediately begin listening and firing events.
        """
        await trigger.start()
        self._triggers.append(trigger)
        task = asyncio.create_task(self._run_trigger(trigger))
        self._trigger_tasks.append(task)
        logger.info("Trigger added at runtime", trigger=type(trigger).__name__)

    async def remove_trigger(self, trigger: BaseTrigger) -> None:
        """Stop and remove a trigger from a running agent."""
        idx = None
        for i, t in enumerate(self._triggers):
            if t is trigger:
                idx = i
                break
        if idx is None:
            return

        # Cancel the corresponding task
        if idx < len(self._trigger_tasks):
            self._trigger_tasks[idx].cancel()
            try:
                await self._trigger_tasks[idx]
            except asyncio.CancelledError:
                pass
            self._trigger_tasks.pop(idx)

        # Stop and remove the trigger
        await trigger.stop()
        self._triggers.pop(idx)
        logger.info("Trigger removed at runtime", trigger=type(trigger).__name__)

    def update_system_prompt(self, content: str, replace: bool = False) -> None:
        """Update the system prompt of a running agent.

        Args:
            content: New content to append (or full replacement if replace=True)
            replace: If True, replace entire system prompt. If False, append.
        """
        sys_msg = self.controller.conversation.get_system_message()
        if sys_msg is None:
            return

        if replace:
            sys_msg.content = content
        else:
            if isinstance(sys_msg.content, str):
                sys_msg.content = sys_msg.content + "\n\n" + content

        logger.info("System prompt updated", replace=replace, added_length=len(content))

    def get_system_prompt(self) -> str:
        """Get the current system prompt text."""
        sys_msg = self.controller.conversation.get_system_message()
        if sys_msg and isinstance(sys_msg.content, str):
            return sys_msg.content
        return ""

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
            "pending_jobs": self.executor.get_pending_count() if self.executor else 0,
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

"""
Agent event handling and tool execution.

Contains mixin methods for processing events, executing tools,
collecting results, and managing background jobs. Separated from
the main Agent class to keep file sizes manageable.
"""

import asyncio
from dataclasses import dataclass, field

from kohakuterrarium.core.controller import Controller
from kohakuterrarium.core.events import (
    EventType,
    TriggerEvent,
    create_tool_complete_event,
)
from kohakuterrarium.core.job import JobResult
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode
from kohakuterrarium.parsing import (
    CommandResultEvent,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def _make_job_label(job_id: str) -> tuple[str, str]:
    """Extract (tool_name, label) from a job_id.

    Label format: ``name[short_id]`` for display purposes.
    """
    tool_name = job_id.rsplit("_", 1)[0] if "_" in job_id else job_id
    short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
    label = f"{tool_name}[{short_id}]" if short_id else tool_name
    return tool_name, label


class AgentHandlersMixin:
    """Mixin providing event handling and tool execution for the Agent class.

    Contains the core event processing loop, tool startup, result collection,
    and background job status management.
    """

    async def _fire_startup_trigger(self) -> None:
        """Fire startup trigger if configured."""
        startup_trigger = self.config.startup_trigger
        if not startup_trigger:
            return

        logger.info("Firing startup trigger")
        event = TriggerEvent(
            type=EventType.STARTUP,
            content=startup_trigger.get("prompt", "Agent starting up."),
            context={"trigger": "startup"},
            prompt_override=startup_trigger.get("prompt"),
            stackable=False,
        )
        await self._process_event(event)

    async def _process_event(self, event: TriggerEvent) -> None:
        """Process event using the primary controller.

        Uses a lock to prevent concurrent processing. When multiple
        triggers fire simultaneously, events are serialized so only
        one LLM call runs at a time.
        """
        # Record user input to session store
        if (
            hasattr(self, "session_store")
            and self.session_store
            and event.type == "user_input"
        ):
            content = (
                event.get_text_content()
                if hasattr(event, "is_multimodal") and event.is_multimodal()
                else (event.content or "")
            )
            self.session_store.append_event(
                self.config.name, "user_input", {"content": content}
            )

        # Notify output of user input (for inline panel rendering)
        if event.type == "user_input" and hasattr(self, "output_router"):
            content = (
                event.get_text_content()
                if hasattr(event, "is_multimodal") and event.is_multimodal()
                else (event.content or "")
            )
            await self.output_router.on_user_input(content)

        async with self._processing_lock:
            if not self._running:
                logger.debug("Dropping event, agent stopped", event_type=event.type)
                return
            await self._process_event_with_controller(event, self.controller)

    # ------------------------------------------------------------------
    # Main processing loop (split into phases)
    # ------------------------------------------------------------------

    async def _process_event_with_controller(
        self, event: TriggerEvent, controller: Controller
    ) -> None:
        """Process a single event through the specified controller.

        Orchestrates the full cycle: push event, run LLM turns in a loop,
        dispatch tools/sub-agents, collect results, push feedback, and
        finalize output. See ``_run_controller_loop`` for the inner loop.
        """
        self._prepare_processing_cycle(event, controller)
        await controller.push_event(event)
        await self.output_router.on_processing_start()

        all_round_text: list[str] = []
        await self._run_controller_loop(controller, all_round_text)
        await self._finalize_processing(event, controller, all_round_text)

    def _prepare_processing_cycle(
        self, event: TriggerEvent, controller: Controller
    ) -> None:
        """Reset state at the start of a new processing cycle."""
        self._interrupt_requested = False
        controller._interrupted = False
        self.trigger_manager.set_context_all(event.context)
        if self._termination_checker:
            self._termination_checker.record_activity()

    async def _run_controller_loop(
        self, controller: Controller, all_round_text: list[str]
    ) -> None:
        """Inner loop: run LLM, dispatch tools, collect feedback, repeat.

        Exits when there is no more feedback to push (no direct tool
        results and no output confirmations).
        """
        while True:
            if self._interrupt_requested:
                self._interrupt_requested = False
                controller._interrupted = False
                self.output_router.notify_activity(
                    "interrupt", "[system] Processing interrupted"
                )
                break

            self._reset_output_state()

            round_result = await self._run_single_turn(controller)
            all_round_text.extend(round_result.text_output)

            # Termination check
            if self._check_termination(round_result.text_output):
                break

            # Flush before collecting results (TUI renders text first)
            await self._flush_output()

            # Collect feedback and decide whether to continue
            should_continue = await self._collect_and_push_feedback(
                controller,
                round_result.direct_tasks,
                round_result.direct_job_ids,
                round_result.native_tool_call_ids,
                round_result.native_mode,
            )
            if not should_continue:
                break

    async def _run_single_turn(self, controller: Controller) -> "_TurnResult":
        """Run one LLM turn, dispatching tools and sub-agents as they appear.

        Returns a ``_TurnResult`` with collected job info and text output.
        """
        direct_tasks: dict[str, asyncio.Task] = {}
        direct_job_ids: list[str] = []
        round_text: list[str] = []
        native_mode = getattr(controller.config, "tool_format", None) == "native"
        native_tool_call_ids: dict[str, str] = {}

        async for parse_event in controller.run_once():
            if self._interrupt_requested:
                break

            if isinstance(parse_event, ToolCallEvent):
                await self._dispatch_tool_event(
                    parse_event,
                    controller,
                    direct_tasks,
                    direct_job_ids,
                    native_tool_call_ids,
                    native_mode,
                )
            elif isinstance(parse_event, SubAgentCallEvent):
                await self._dispatch_subagent_event(parse_event, controller)
            elif isinstance(parse_event, CommandResultEvent):
                self._notify_command_result(parse_event)
            else:
                if isinstance(parse_event, TextEvent):
                    round_text.append(parse_event.text)
                await self.output_router.route(parse_event)

        return _TurnResult(
            direct_tasks=direct_tasks,
            direct_job_ids=direct_job_ids,
            text_output=round_text,
            native_mode=native_mode,
            native_tool_call_ids=native_tool_call_ids,
        )

    async def _dispatch_tool_event(
        self,
        parse_event: ToolCallEvent,
        controller: Controller,
        direct_tasks: dict[str, asyncio.Task],
        direct_job_ids: list[str],
        native_tool_call_ids: dict[str, str],
        native_mode: bool,
    ) -> None:
        """Handle a ToolCallEvent: start the tool and track it."""
        tool_call_id = parse_event.args.pop("_tool_call_id", None)
        run_bg = parse_event.args.pop("run_in_background", False)

        job_id, task, is_direct = await self._start_tool_async(parse_event)

        # Three-level decision for execution mode
        if not is_direct:
            pass  # Tool declared BACKGROUND, respect it
        elif run_bg:
            is_direct = False

        if tool_call_id:
            native_tool_call_ids[job_id] = tool_call_id

        if is_direct:
            direct_tasks[job_id] = task
            direct_job_ids.append(job_id)
        elif tool_call_id:
            # Background: add placeholder for native mode conversation
            controller.conversation.append(
                "tool",
                "Running in background. Result will be delivered when ready.",
                tool_call_id=tool_call_id,
                name=parse_event.name,
            )

        logger.debug(
            "Tool started",
            tool_name=parse_event.name,
            job_id=job_id,
            direct=is_direct,
        )

        await self._flush_output()
        self._notify_tool_start(parse_event, job_id, is_direct)

    async def _dispatch_subagent_event(
        self, parse_event: SubAgentCallEvent, controller: Controller
    ) -> None:
        """Handle a SubAgentCallEvent: start the sub-agent."""
        sa_tool_call_id = parse_event.args.pop("_tool_call_id", None)
        job_id = await self._start_subagent_async(parse_event)

        if sa_tool_call_id:
            controller.conversation.append(
                "tool",
                f"Sub-agent '{parse_event.name}' running. "
                "Result will be delivered when ready.",
                tool_call_id=sa_tool_call_id,
                name=parse_event.name,
            )

        await self._flush_output()
        _, label = _make_job_label(job_id)
        full_task = parse_event.args.get("task", "")
        self.output_router.notify_activity(
            "subagent_start",
            f"[{label}] {full_task[:60]}",
            metadata={"job_id": job_id, "task": full_task},
        )

    def _notify_command_result(self, parse_event: CommandResultEvent) -> None:
        """Route command results to activity log (not user-facing output)."""
        if parse_event.error:
            self.output_router.notify_activity(
                "command_error",
                f"[{parse_event.command}] {parse_event.error}",
            )
        else:
            self.output_router.notify_activity(
                "command_done",
                f"[{parse_event.command}] OK",
            )

    def _notify_tool_start(
        self, parse_event: ToolCallEvent, job_id: str, is_direct: bool
    ) -> None:
        """Notify output of a tool start with a human-readable preview."""
        _, label = _make_job_label(job_id)

        full_args: dict = {}
        arg_preview = ""
        if parse_event.args:
            arg_parts = []
            for k, v in parse_event.args.items():
                if k.startswith("_"):
                    continue
                full_args[k] = v
                arg_parts.append(f"{k}={str(v)[:40]}")
            arg_preview = " ".join(arg_parts)[:80]

        bg_tag = " (bg)" if not is_direct else ""
        self.output_router.notify_activity(
            "tool_start",
            f"[{label}]{bg_tag} {arg_preview}",
            metadata={"job_id": job_id, "args": full_args},
        )

    def _check_termination(self, round_text: list[str]) -> bool:
        """Check if termination conditions are met. Returns True to stop."""
        if not self._termination_checker:
            return False
        self._termination_checker.record_turn()
        last_output = "".join(round_text)
        if self._termination_checker.should_terminate(last_output=last_output):
            logger.info(
                "Agent terminated",
                reason=self._termination_checker.reason,
                turns=self._termination_checker.turn_count,
            )
            self._running = False
            return True
        return False

    async def _collect_and_push_feedback(
        self,
        controller: Controller,
        direct_tasks: dict[str, asyncio.Task],
        direct_job_ids: list[str],
        native_tool_call_ids: dict[str, str],
        native_mode: bool,
    ) -> bool:
        """Collect tool results and output feedback, push to controller.

        Returns True if the loop should continue (feedback was pushed),
        False if there is nothing more to process.
        """
        feedback_parts: list[str] = []

        # Output feedback (tells model what was sent to named outputs)
        output_feedback = self.output_router.get_output_feedback()
        if output_feedback:
            feedback_parts.append(output_feedback)

        # Direct tool results
        native_results_added = False
        if direct_tasks:
            logger.info("Waiting for %d direct tool(s)", len(direct_tasks))
            if native_mode and native_tool_call_ids:
                await self._add_native_tool_results(
                    controller, direct_job_ids, direct_tasks, native_tool_call_ids
                )
                native_results_added = True
            else:
                results = await self._collect_tool_results(
                    direct_job_ids, direct_tasks
                )
                if results:
                    feedback_parts.append(results)

        # No feedback means we're done
        if not feedback_parts and not native_results_added:
            logger.debug("No feedback, exiting process loop")
            return False

        # Push feedback to controller for next turn
        if native_results_added and not feedback_parts:
            logger.debug("Native tool results in conversation, continuing")
            await controller.push_event(
                TriggerEvent(type="tool_complete", content="")
            )
        elif feedback_parts:
            combined = "\n\n".join(feedback_parts)
            feedback_event = create_tool_complete_event(
                job_id="batch", content=combined, exit_code=0, error=None,
            )
            logger.debug("Pushing feedback to controller, continuing")
            await controller.push_event(feedback_event)

        return True

    async def _finalize_processing(
        self,
        event: TriggerEvent,
        controller: Controller,
        all_round_text: list[str],
    ) -> None:
        """Finalize: flush output, emit usage, notify processing end."""
        await self._flush_output()

        # Emit token usage
        usage = getattr(controller, "_last_usage", {})
        if usage:
            self.output_router.notify_activity(
                "token_usage",
                f"tokens: {usage.get('prompt_tokens', 0)} in, "
                f"{usage.get('completion_tokens', 0)} out",
                metadata=usage,
            )

        # Channel-triggered event notification
        trigger_channel = event.context.get("channel") if event.context else None
        trigger_sender = event.context.get("sender") if event.context else None
        if trigger_channel and trigger_sender:
            round_output = "".join(all_round_text).strip()
            if round_output:
                self.output_router.notify_activity(
                    "processing_complete",
                    f"Processed message from {trigger_channel}",
                    metadata={
                        "trigger_channel": trigger_channel,
                        "trigger_sender": trigger_sender,
                        "output_preview": round_output[:500],
                    },
                )

        await self.output_router.on_processing_end()
        self.output_router.clear_all()

        if controller.is_ephemeral:
            controller.flush()

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _reset_output_state(self) -> None:
        """Reset output router and default output for a new iteration."""
        self.output_router.reset()
        if hasattr(self.output_router.default_output, "reset"):
            self.output_router.default_output.reset()

    async def _flush_output(self) -> None:
        """Flush buffered output and reset default output."""
        await self.output_router.flush()
        if hasattr(self.output_router.default_output, "reset"):
            self.output_router.default_output.reset()

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _start_tool_async(
        self, tool_call: ToolCallEvent
    ) -> tuple[str, asyncio.Task, bool]:
        """Start a tool execution immediately as an async task.

        Does NOT wait for completion.

        Returns:
            (job_id, task, is_direct): is_direct indicates if we should wait
        """
        try:
            logger.info("Running tool: %s", tool_call.name)
            tool = self.executor.get_tool(tool_call.name)
            is_direct = True
            if tool and isinstance(tool, BaseTool):
                is_direct = tool.execution_mode == ExecutionMode.DIRECT

            job_id = await self.executor.submit_from_event(
                tool_call, is_direct=is_direct
            )
            task = self.executor.get_task(job_id)
            if task is None:
                async def _get_result():
                    return self.executor.get_result(job_id)
                task = asyncio.create_task(_get_result())

            return job_id, task, is_direct
        except Exception as e:
            logger.error("Failed to start tool", tool_name=tool_call.name, error=str(e))
            error_msg = str(e)
            error_job_id = f"error_{tool_call.name}"

            async def _error_result():
                return JobResult(job_id=error_job_id, error=error_msg)

            task = asyncio.create_task(_error_result())
            return error_job_id, task, True

    async def _add_native_tool_results(
        self,
        controller: Controller,
        job_ids: list[str],
        tasks: dict[str, asyncio.Task],
        tool_call_ids: dict[str, str],
    ) -> None:
        """Wait for tools and add results as role='tool' messages.

        For native tool calling mode: appends proper tool messages
        to the conversation so the LLM sees structured results.
        """
        if not tasks:
            return

        results_list = await asyncio.gather(
            *[tasks[jid] for jid in job_ids], return_exceptions=True,
        )

        for job_id, result in zip(job_ids, results_list):
            tool_name, label = _make_job_label(job_id)
            tool_call_id = tool_call_ids.get(job_id, job_id)

            if isinstance(result, Exception):
                content = f"Error: {result}"
                self.output_router.notify_activity(
                    "tool_error", f"[{label}] FAILED: {result}"
                )
            elif result is not None and result.error:
                content = f"Error: {result.error}"
                self.output_router.notify_activity(
                    "tool_error", f"[{label}] ERROR: {result.error}"
                )
            elif result is not None:
                content = result.output if result.output else ""
                status = "OK" if result.exit_code == 0 else f"exit={result.exit_code}"
                self.output_router.notify_activity("tool_done", f"[{label}] {status}")
            else:
                content = ""

            controller.conversation.append(
                "tool", content, tool_call_id=tool_call_id, name=tool_name,
            )

    async def _collect_tool_results(
        self,
        job_ids: list[str],
        tasks: dict[str, asyncio.Task],
    ) -> str:
        """Wait for all tools to complete and return formatted results."""
        if not tasks:
            return ""

        results_list = await asyncio.gather(
            *[tasks[jid] for jid in job_ids], return_exceptions=True,
        )

        result_strs: list[str] = []
        for job_id, result in zip(job_ids, results_list):
            _, label = _make_job_label(job_id)

            if isinstance(result, Exception):
                result_strs.append(f"## {job_id} - FAILED\n{str(result)}")
                logger.info("Tool %s: failed", job_id)
                self.output_router.notify_activity(
                    "tool_error", f"[{label}] FAILED: {result}"
                )
            elif result is not None:
                output = result.output if result.output else ""
                if result.error:
                    result_strs.append(
                        f"## {job_id} - ERROR\n{result.error}\n{output}"
                    )
                    logger.info("Tool %s: error", job_id)
                    self.output_router.notify_activity(
                        "tool_error", f"[{label}] ERROR: {result.error}"
                    )
                else:
                    status = (
                        "OK" if result.exit_code == 0 else f"exit={result.exit_code}"
                    )
                    result_strs.append(f"## {job_id} - {status}\n{output}")
                    logger.info("Tool %s: done", job_id)
                    self.output_router.notify_activity(
                        "tool_done", f"[{label}] {status}"
                    )

        return "\n\n".join(result_strs) if result_strs else ""

    # ------------------------------------------------------------------
    # Sub-agent execution
    # ------------------------------------------------------------------

    async def _start_subagent_async(self, event: SubAgentCallEvent) -> str:
        """Start a sub-agent execution. Returns job ID."""
        logger.info(
            "Starting sub-agent",
            subagent_type=event.name,
            task=event.args.get("task", "")[:50],
        )
        try:
            return await self.subagent_manager.spawn_from_event(event)
        except ValueError as e:
            logger.error(
                "Sub-agent not registered", subagent_name=event.name, error=str(e)
            )
            return f"error_{event.name}"

    # ------------------------------------------------------------------
    # Background job completion callback
    # ------------------------------------------------------------------

    def _on_bg_complete(self, event: TriggerEvent) -> None:
        """Callback fired by executor when a BACKGROUND tool completes.

        Direct tools never fire this. Only background tools and
        sub-agents reach here.
        """
        if not self._running:
            return

        job_id = getattr(event, "job_id", "")
        is_subagent = job_id.startswith("agent_")
        error = event.context.get("error") if event.context else None
        content = (
            event.content if isinstance(event.content, str) else str(event.content)
        )

        if is_subagent:
            parts = job_id.split("_")
            sa_name = parts[1] if len(parts) >= 3 else job_id
            short_id = parts[-1][:6] if len(parts) >= 3 else ""
            label = f"{sa_name}[{short_id}]" if short_id else sa_name
            activity_done = "subagent_done"
            activity_error = "subagent_error"
        else:
            _, label = _make_job_label(job_id)
            activity_done = "tool_done"
            activity_error = "tool_error"

        sa_meta = event.context.get("subagent_metadata", {}) if event.context else {}
        tools_used = sa_meta.get("tools_used", [])

        if error:
            self.output_router.notify_activity(
                activity_error,
                f"[{label}] ERROR: {error}",
                metadata={"job_id": job_id},
            )
        elif is_subagent:
            tools_summary = ", ".join(tools_used[:10]) if tools_used else "none"
            self.output_router.notify_activity(
                activity_done,
                f"[{label}] tools: {tools_summary}",
                metadata={
                    "job_id": job_id,
                    "tools_used": tools_used,
                    "result": content,
                    "turns": sa_meta.get("turns", 0),
                    "duration": sa_meta.get("duration", 0),
                },
            )
        else:
            self.output_router.notify_activity(
                activity_done,
                f"[{label}] DONE",
                metadata={"job_id": job_id},
            )

        logger.info("Background job completed", job_id=job_id)
        asyncio.create_task(self._process_event(event))


@dataclass(slots=True)
class _TurnResult:
    """Results from a single LLM turn, used internally by the controller loop."""

    direct_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    direct_job_ids: list[str] = field(default_factory=list)
    text_output: list[str] = field(default_factory=list)
    native_mode: bool = False
    native_tool_call_ids: dict[str, str] = field(default_factory=dict)

"""
Agent event handling and tool execution.

Contains mixin methods for processing events, executing tools,
collecting results, and managing background jobs. Separated from
the main Agent class to keep file sizes manageable.
"""

import asyncio
from typing import Any

from kohakuterrarium.core.constants import (
    STATUS_PREVIEW_MAX_CHARS,
    TOOL_RESULT_MAX_CHARS,
)
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


class AgentHandlersMixin:
    """
    Mixin providing event handling and tool execution for the Agent class.

    Contains the core event processing loop, tool startup, result collection,
    and background job status management.
    """

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
        """Process event using the primary controller.

        Uses a lock to prevent concurrent processing. When multiple
        triggers fire simultaneously (e.g. broadcast), events are
        serialized so only one LLM call runs at a time.
        """
        async with self._processing_lock:
            if not self._running:
                logger.debug("Dropping event, agent stopped", event_type=event.type)
                return
            await self._process_event_with_controller(event, self.controller)

    async def _process_event_with_controller(
        self, event: TriggerEvent, controller: Controller
    ) -> None:
        """
        Process a single event through the specified controller.

        This is the main agent loop. It continues until:
        1. No new jobs were started this round, AND
        2. No background jobs or sub-agents are still pending, AND
        3. No feedback (tool results, status updates, output confirmations) to report

        Flow per iteration:
        1. Run controller.run_once() to get LLM response
        2. Handle parse events:
           - ToolCallEvent -> start tool immediately (direct or background)
           - SubAgentCallEvent -> start sub-agent (always background)
           - Others -> route to output_router
        3. Wait for direct tools to complete
        4. Collect feedback:
           - Output feedback (what was sent to named outputs)
           - Direct tool results
           - Background job/sub-agent status (RUNNING or completed)
        5. Push feedback as event to controller for next iteration

        Job lifecycle:
        - Jobs are tracked in pending_*_ids lists until their results are reported
        - Once a job completes and its result is included in feedback, it's removed
        - Loop stays alive while any jobs are pending (even if RUNNING)

        Wait command integration:
        - Model can use [/wait]job_id[wait/] to block until a specific job completes
        - Wait command uses shared job_store (same as executor and subagent_manager)
        - Controller handles wait command inline, result is surfaced to model
        """
        # Notify triggers of context update (for idle timer reset, etc.)
        for trigger in self._triggers:
            try:
                trigger.set_context(event.context)
            except Exception as e:
                logger.warning(
                    "Trigger context update failed",
                    trigger=type(trigger).__name__,
                    error=str(e),
                )

        # Record activity for termination checker
        if self._termination_checker:
            self._termination_checker.record_activity()

        await controller.push_event(event)

        # Notify output modules that processing is starting (e.g., typing indicator)
        await self.output_router.on_processing_start()

        # =======================================================================
        # Job Tracking: pending_*_ids lists track jobs across loop iterations.
        # Jobs stay in these lists until their results are reported to model.
        # =======================================================================
        pending_background_ids: list[str] = []
        pending_subagent_ids: list[str] = []

        while True:
            # ===================================================================
            # PHASE 1: Setup for new iteration
            # ===================================================================
            self.output_router.reset()
            # TODO: Improvement needed - OutputModule protocol should include
            # an optional reset() method instead of using hasattr() duck typing.
            # This would require changes to modules/output/base.py (out of scope).
            if hasattr(self.output_router.default_output, "reset"):
                self.output_router.default_output.reset()

            # Track jobs started THIS iteration (direct vs background)
            direct_tasks: dict[str, asyncio.Task] = {}  # Direct: we wait for these
            direct_job_ids: list[str] = []
            new_background_ids: list[str] = []  # Background: tracked until done
            new_subagent_ids: list[str] = []  # Sub-agents: always background
            round_text_output: list[str] = []  # Collect text for termination check

            # ===================================================================
            # PHASE 2: Run LLM and handle parse events
            # Controller yields: TextEvent, ToolCallEvent, SubAgentCallEvent, etc.
            # CommandEvents are handled inline by controller (converted to TextEvent)
            # ===================================================================
            async for parse_event in controller.run_once():
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
                    # Notify output of tool activity with name[id] + arg preview
                    short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
                    label = f"{parse_event.name}[{short_id}]" if short_id else parse_event.name
                    arg_preview = ""
                    if parse_event.args:
                        arg_parts = []
                        for k, v in parse_event.args.items():
                            v_str = str(v)[:40]
                            arg_parts.append(f"{k}={v_str}")
                        arg_preview = " ".join(arg_parts)[:60]
                    self.output_router.default_output.on_activity(
                        "tool_start",
                        f"[{label}] {arg_preview}",
                    )
                elif isinstance(parse_event, SubAgentCallEvent):
                    job_id = await self._start_subagent_async(parse_event)
                    new_subagent_ids.append(job_id)
                    # Notify output of sub-agent activity with name[id]
                    sa_short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
                    sa_label = f"{parse_event.name}[{sa_short_id}]" if sa_short_id else parse_event.name
                    task_preview = parse_event.args.get("task", "")[:60]
                    self.output_router.default_output.on_activity(
                        "subagent_start",
                        f"[{sa_label}] {task_preview}",
                    )
                elif isinstance(parse_event, CommandResultEvent):
                    # Command results are internal feedback for the LLM,
                    # NOT user-facing output. Route to activity/logs only.
                    if parse_event.error:
                        self.output_router.default_output.on_activity(
                            "command_error",
                            f"[{parse_event.command}] {parse_event.error}",
                        )
                    else:
                        self.output_router.default_output.on_activity(
                            "command_done",
                            f"[{parse_event.command}] OK",
                        )
                else:
                    # Capture text output for termination keyword detection
                    if isinstance(parse_event, TextEvent):
                        round_text_output.append(parse_event.text)
                    await self.output_router.route(parse_event)

            # ===================================================================
            # Termination check (between PHASE 2 and PHASE 3)
            # ===================================================================
            if self._termination_checker:
                self._termination_checker.record_turn()
                # Check the actual text the model output this round
                last_output = "".join(round_text_output)
                if self._termination_checker.should_terminate(last_output=last_output):
                    logger.info(
                        "Agent terminated",
                        reason=self._termination_checker.reason,
                        turns=self._termination_checker.turn_count,
                    )
                    # Stop the agent so it won't accept new triggers
                    self._running = False
                    break

            # ===================================================================
            # PHASE 3: Flush output and update job tracking
            # ===================================================================
            await self.output_router.flush()

            # Note: Commands (read, info, jobs, wait) are handled inline by
            # controller during run_once() - they never reach output_router.
            # See controller._handle_command() which uses ControllerContext.

            jobs_started_this_round = bool(
                direct_tasks or new_background_ids or new_subagent_ids
            )

            # Add new background jobs to pending lists for tracking
            pending_background_ids.extend(new_background_ids)
            pending_subagent_ids.extend(new_subagent_ids)

            # ===================================================================
            # PHASE 4: Collect feedback for the model
            # Feedback includes: output confirmations, tool results, job status
            # ===================================================================
            feedback_parts: list[str] = []

            # 4a. Output feedback - tells model what was sent to named outputs
            output_feedback = self.output_router.get_output_feedback()
            if output_feedback:
                feedback_parts.append(output_feedback)

            # 4b. Direct tool results - we waited for these, now report results
            if direct_tasks:
                logger.info("Waiting for %d direct tool(s)", len(direct_tasks))
                results = await self._collect_tool_results(direct_job_ids, direct_tasks)
                if results:
                    feedback_parts.append(results)

            # 4c. Background job status - report RUNNING or completed results
            # Completed jobs are removed from pending lists after reporting
            if pending_background_ids or pending_subagent_ids:
                bg_status, pending_background_ids, pending_subagent_ids = (
                    self._get_and_cleanup_background_status(
                        pending_background_ids, pending_subagent_ids
                    )
                )
                if bg_status:
                    feedback_parts.append(bg_status)

            # ===================================================================
            # PHASE 5: Decide whether to continue the loop
            # Exit only when: no new jobs, no pending jobs, no feedback
            # ===================================================================
            if (
                not jobs_started_this_round
                and not pending_background_ids
                and not pending_subagent_ids
                and not feedback_parts
            ):
                logger.debug(
                    "No jobs pending and no feedback, exiting process loop",
                    jobs_this_round=jobs_started_this_round,
                    pending_bg=len(pending_background_ids),
                    pending_sa=len(pending_subagent_ids),
                )
                break

            # ===================================================================
            # PHASE 6: Push feedback to controller for next LLM turn
            # ===================================================================
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
                await controller.push_event(feedback_event)
            else:
                # No feedback but have pending jobs - push a status message
                # so the model knows jobs are still running and can use wait
                pending_count = len(pending_background_ids) + len(pending_subagent_ids)
                status_msg = (
                    f"{pending_count} background job(s) still running. "
                    "Use [/wait]job_id[wait/] to get results, or continue with other work."
                )
                logger.debug(
                    "No feedback but pending jobs, sending status hint",
                    pending_bg=len(pending_background_ids),
                    pending_sa=len(pending_subagent_ids),
                )
                status_event = create_tool_complete_event(
                    job_id="status",
                    content=status_msg,
                    exit_code=0,
                )
                await controller.push_event(status_event)

        # Notify output modules that processing has ended
        await self.output_router.on_processing_end()

        # Clear any remaining output state at end of turn
        self.output_router.clear_all()

        # In ephemeral mode, flush conversation after each interaction
        if controller.is_ephemeral:
            controller.flush()

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
        try:
            logger.info("Running tool: %s", tool_call.name)

            # Check if tool is direct (blocking) or background
            tool = self.executor.get_tool(tool_call.name)
            is_direct = True  # Default to direct
            if tool and isinstance(tool, BaseTool):
                is_direct = tool.execution_mode == ExecutionMode.DIRECT

            # Submit to executor - this creates the task internally
            job_id = await self.executor.submit_from_event(tool_call)

            # Get the task handle from executor using public API
            task = self.executor.get_task(job_id)
            if task is None:
                # Fallback: create a dummy completed task if already done
                async def _get_result():
                    return self.executor.get_result(job_id)

                task = asyncio.create_task(_get_result())

            return job_id, task, is_direct
        except Exception as e:
            logger.error("Failed to start tool", tool_name=tool_call.name, error=str(e))

            # Create a dummy completed task that returns error
            # Capture error string before exception variable goes out of scope
            error_msg = str(e)
            error_job_id = f"error_{tool_call.name}"

            async def _error_result():
                return JobResult(job_id=error_job_id, error=error_msg)

            task = asyncio.create_task(_error_result())
            return error_job_id, task, True  # Direct so it gets reported

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
            # Extract tool name: everything before the last underscore
            # job_id format is "{tool_name}_{uuid}", tool names may contain underscores
            tool_name = job_id.rsplit("_", 1)[0] if "_" in job_id else job_id

            if isinstance(result, Exception):
                result_strs.append(f"## {job_id} - FAILED\n{str(result)}")
                logger.info("Tool %s: failed", tool_name)
                self.output_router.default_output.on_activity(
                    "tool_error", f"[{tool_name}] FAILED: {result}"
                )
            elif result is not None:
                output = result.output[:TOOL_RESULT_MAX_CHARS] if result.output else ""
                if result.error:
                    result_strs.append(f"## {job_id} - ERROR\n{result.error}\n{output}")
                    logger.info("Tool %s: error", tool_name)
                    self.output_router.default_output.on_activity(
                        "tool_error", f"[{tool_name}] ERROR: {result.error}"
                    )
                else:
                    status = (
                        "OK" if result.exit_code == 0 else f"exit={result.exit_code}"
                    )
                    result_strs.append(f"## {job_id} - {status}\n{output}")
                    logger.info("Tool %s: done", tool_name)
                    self.output_router.default_output.on_activity(
                        "tool_done", f"[{tool_name}] {status}"
                    )

        return "\n\n".join(result_strs) if result_strs else ""

    def _get_and_cleanup_background_status(
        self,
        background_job_ids: list[str],
        subagent_job_ids: list[str],
    ) -> tuple[str, list[str], list[str]]:
        """
        Get status of background jobs and sub-agents, cleaning up completed ones.

        This function serves two purposes:
        1. Report status to the model (so it knows what's happening)
        2. Clean up completed jobs (so they don't get reported again)

        For each job:
        - If COMPLETED: Include result in status, DON'T add to remaining list
        - If RUNNING: Include "RUNNING" status, ADD to remaining list

        The remaining lists are used by the main loop to determine:
        - Whether to continue looping (pending jobs exist)
        - What to check on the next iteration

        IMPORTANT: Always report RUNNING status. This ensures:
        - Model knows jobs are still in progress
        - Loop continues while jobs are running
        - Model can use [/wait] command to block if needed

        Args:
            background_job_ids: IDs of background tool jobs to check
            subagent_job_ids: IDs of sub-agent jobs to check

        Returns:
            Tuple of:
            - status_string: Formatted status for feedback to model
            - remaining_background_ids: Background jobs still running
            - remaining_subagent_ids: Sub-agent jobs still running
        """
        if not background_job_ids and not subagent_job_ids:
            return "", [], []

        status_lines: list[str] = []
        remaining_bg: list[str] = []
        remaining_sa: list[str] = []

        # Check background tools
        for job_id in background_job_ids:
            tool_name = job_id.rsplit("_", 1)[0] if "_" in job_id else job_id
            short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
            label = f"{tool_name}[{short_id}]" if short_id else tool_name

            status = self.executor.get_status(job_id)
            if status:
                if status.is_complete:
                    result = self.executor.get_result(job_id)
                    if result and result.error:
                        status_lines.append(f"- `{job_id}`: ERROR - {result.error}")
                        self.output_router.default_output.on_activity(
                            "tool_error", f"[{label}] ERROR: {result.error}"
                        )
                    else:
                        output = (
                            result.output[:STATUS_PREVIEW_MAX_CHARS]
                            if result and result.output
                            else ""
                        )
                        status_lines.append(f"- `{job_id}`: DONE\n{output}")
                        self.output_router.default_output.on_activity(
                            "tool_done", f"[{label}] DONE"
                        )
                else:
                    status_lines.append(f"- `{job_id}`: {status.state.value}")
                    remaining_bg.append(job_id)

        # Check sub-agents
        for job_id in subagent_job_ids:
            sa_name = job_id.replace("agent_", "", 1).rsplit("_", 1)[0] if "_" in job_id else job_id
            short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
            label = f"{sa_name}[{short_id}]" if short_id else sa_name

            if job_id.startswith("error_"):
                status_lines.append(f"- `{job_id}`: ERROR - Sub-agent not registered")
                self.output_router.default_output.on_activity(
                    "subagent_error", f"[{label}] Not registered"
                )
                continue

            result = self.subagent_manager.get_result(job_id)
            if result:
                if result.success:
                    output = result.truncated(max_chars=STATUS_PREVIEW_MAX_CHARS)
                    status_lines.append(
                        f"- `{job_id}`: DONE (turns={result.turns})\n{output}"
                    )
                    self.output_router.default_output.on_activity(
                        "subagent_done",
                        f"[{label}] DONE (turns={result.turns})",
                    )
                else:
                    status_lines.append(f"- `{job_id}`: ERROR - {result.error}")
                    self.output_router.default_output.on_activity(
                        "subagent_error", f"[{label}] ERROR: {result.error}"
                    )
            else:
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

    async def _run_trigger(self, trigger: Any) -> None:
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

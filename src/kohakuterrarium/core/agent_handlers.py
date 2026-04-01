"""
Agent event handling and tool execution.

Contains mixin methods for processing events, executing tools,
collecting results, and managing background jobs. Separated from
the main Agent class to keep file sizes manageable.
"""

import asyncio
from typing import Any


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
        # Record user input to session store (catches CLI + inject_input + all sources)
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

        This loop handles ONE event and all its direct tool calls.
        It exits as soon as there's no more immediate feedback.

        Flow per iteration:
        1. Run controller.run_once() to get LLM response
        2. Handle parse events:
           - ToolCallEvent -> start tool (direct or background)
           - SubAgentCallEvent -> start sub-agent (background)
           - Others -> route to output_router
        3. Wait for DIRECT tools only, collect results
        4. Push feedback to controller for next iteration
        5. Exit when no feedback remains

        Background tools and sub-agents do NOT block this loop.
        They deliver results via executor._on_complete callback,
        which fires _process_event as a new task (same as triggers).
        """
        # Notify triggers of context update (for idle timer reset, etc.)
        self.trigger_manager.set_context_all(event.context)

        # Record activity for termination checker
        if self._termination_checker:
            self._termination_checker.record_activity()

        await controller.push_event(event)

        # Notify output modules that processing is starting (e.g., typing indicator)
        await self.output_router.on_processing_start()

        # Accumulate all text output across loop iterations (for idle notification)
        all_round_text: list[str] = []

        # =======================================================================
        # Job Tracking: pending_*_ids lists track jobs across loop iterations.
        # Jobs stay in these lists until their results are reported to model.
        # =======================================================================
        # Background jobs are NOT tracked here. They deliver results
        # via executor._on_complete -> _process_event when they complete.

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

            # Track jobs started THIS iteration
            direct_tasks: dict[str, asyncio.Task] = {}  # Direct: we wait for these
            direct_job_ids: list[str] = []
            round_text_output: list[str] = []  # Collect text for termination check

            # ===================================================================
            # PHASE 2: Run LLM and handle parse events
            # Controller yields: TextEvent, ToolCallEvent, SubAgentCallEvent, etc.
            # CommandEvents are handled inline by controller (converted to TextEvent)
            # ===================================================================
            # In native mode, all tools are direct (we wait for results
            # to add them as proper tool messages to conversation)
            native_mode = getattr(controller.config, "tool_format", None) == "native"
            # Track tool_call_ids for native mode tool messages
            native_tool_call_ids: dict[str, str] = {}  # job_id -> tool_call_id

            async for parse_event in controller.run_once():
                if isinstance(parse_event, ToolCallEvent):
                    # Extract tool_call_id if present (native mode)
                    tool_call_id = parse_event.args.pop("_tool_call_id", None)

                    # Check if model explicitly requested background
                    run_bg = parse_event.args.pop("run_in_background", False)

                    job_id, task, is_direct = await self._start_tool_async(parse_event)

                    # Three-level decision:
                    # 1. Tool declares BACKGROUND mode -> always background (forced)
                    # 2. Model passes run_in_background=True -> background (opt-in)
                    # 3. Otherwise -> direct (default)
                    if not is_direct:
                        pass  # Tool itself declared BACKGROUND, respect it
                    elif run_bg:
                        is_direct = False
                    else:
                        is_direct = True

                    if tool_call_id:
                        native_tool_call_ids[job_id] = tool_call_id

                    if is_direct:
                        direct_tasks[job_id] = task
                        direct_job_ids.append(job_id)
                    else:
                        # Background: add placeholder so API sees a response
                        # for every tool call. Actual result comes later via
                        # _on_bg_complete -> _process_event.
                        if tool_call_id:
                            controller.conversation.append(
                                "tool",
                                f"Running in background. "
                                "Result will be delivered when ready.",
                                tool_call_id=tool_call_id,
                                name=parse_event.name,
                            )
                    logger.debug(
                        "Tool started",
                        tool_name=parse_event.name,
                        job_id=job_id,
                        direct=is_direct,
                    )
                    # Flush buffered LLM text so it renders before tool_start
                    await self.output_router.flush()
                    if hasattr(self.output_router.default_output, "reset"):
                        self.output_router.default_output.reset()

                    # Notify output of tool activity with name[id] + arg preview
                    short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
                    label = (
                        f"{parse_event.name}[{short_id}]"
                        if short_id
                        else parse_event.name
                    )
                    # Build truncated preview for human-readable detail
                    full_args = {}
                    arg_preview = ""
                    if parse_event.args:
                        arg_parts = []
                        for k, v in parse_event.args.items():
                            if k.startswith("_"):
                                continue
                            full_args[k] = v
                            v_str = str(v)[:40]
                            arg_parts.append(f"{k}={v_str}")
                        arg_preview = " ".join(arg_parts)[:80]
                    bg_tag = " (bg)" if not is_direct else ""
                    self.output_router.notify_activity(
                        "tool_start",
                        f"[{label}]{bg_tag} {arg_preview}",
                        metadata={"job_id": job_id, "args": full_args},
                    )
                elif isinstance(parse_event, SubAgentCallEvent):
                    # Extract tool_call_id (native mode)
                    sa_tool_call_id = parse_event.args.pop("_tool_call_id", None)

                    job_id = await self._start_subagent_async(parse_event)

                    # Add placeholder to conversation (native mode needs it)
                    if sa_tool_call_id:
                        controller.conversation.append(
                            "tool",
                            f"Sub-agent '{parse_event.name}' running. "
                            "Result will be delivered when ready.",
                            tool_call_id=sa_tool_call_id,
                            name=parse_event.name,
                        )

                    # Flush buffered LLM text before showing activity
                    await self.output_router.flush()
                    if hasattr(self.output_router.default_output, "reset"):
                        self.output_router.default_output.reset()
                    # Notify output of sub-agent activity with name[id]
                    sa_short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
                    sa_label = (
                        f"{parse_event.name}[{sa_short_id}]"
                        if sa_short_id
                        else parse_event.name
                    )
                    full_task = parse_event.args.get("task", "")
                    task_preview = full_task[:60]
                    self.output_router.notify_activity(
                        "subagent_start",
                        f"[{sa_label}] {task_preview}",
                        metadata={"job_id": job_id, "task": full_task},
                    )
                elif isinstance(parse_event, CommandResultEvent):
                    # Command results are internal feedback for the LLM,
                    # NOT user-facing output. Route to activity/logs only.
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
                else:
                    # Capture text output for termination keyword detection
                    if isinstance(parse_event, TextEvent):
                        round_text_output.append(parse_event.text)
                    await self.output_router.route(parse_event)

            # Accumulate text across iterations
            all_round_text.extend(round_text_output)

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
            # PHASE 3: Flush output before collecting results
            # This ensures buffered LLM text renders in TUI BEFORE
            # tool_done/tool_error activity notifications appear.
            # ===================================================================
            await self.output_router.flush()
            if hasattr(self.output_router.default_output, "reset"):
                self.output_router.default_output.reset()

            jobs_started_this_round = bool(direct_tasks)

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
            native_results_added = False
            if direct_tasks:
                logger.info("Waiting for %d direct tool(s)", len(direct_tasks))

                if native_mode and native_tool_call_ids:
                    # Native mode: add results as role="tool" messages
                    # directly to conversation (proper API format)
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

            # ===================================================================
            # PHASE 5: Decide whether to continue the loop
            #
            # Exit when there's no feedback from direct tools or outputs.
            # Background jobs deliver results asynchronously via
            # _on_bg_complete -> _process_event (same path as triggers).
            # ===================================================================
            if not feedback_parts and not native_results_added:
                logger.debug("No feedback, exiting process loop")
                break

            # ===================================================================
            # PHASE 6: Push feedback to controller for next LLM turn
            # ===================================================================
            if native_results_added and not feedback_parts:
                # Native mode: tool results already in conversation as
                # role="tool" messages. Trigger next LLM turn.
                logger.debug("Native tool results in conversation, continuing")
                await controller.push_event(
                    TriggerEvent(type="tool_complete", content="")
                )
            elif feedback_parts:
                combined = "\n\n".join(feedback_parts)
                feedback_event = create_tool_complete_event(
                    job_id="batch",
                    content=combined,
                    exit_code=0,
                    error=None,
                )
                logger.debug("Pushing feedback to controller, continuing")
                await controller.push_event(feedback_event)

        # Flush remaining buffered output
        await self.output_router.flush()
        if hasattr(self.output_router.default_output, "reset"):
            self.output_router.default_output.reset()

        # Emit token usage from this processing cycle
        usage = getattr(controller, "_last_usage", {})
        if usage:
            self.output_router.notify_activity(
                "token_usage",
                f"tokens: {usage.get('prompt_tokens', 0)} in, {usage.get('completion_tokens', 0)} out",
                metadata=usage,
            )

        # Check if this was a channel-triggered event and whether we sent
        # to any channel. If not, notify the output that the creature
        # processed a channel message without sending to any channel.
        trigger_channel = event.context.get("channel") if event.context else None
        trigger_sender = event.context.get("sender") if event.context else None
        if trigger_channel and trigger_sender:
            # Collect text output from this round for the notification
            round_output = "".join(all_round_text).strip()
            if round_output:
                # Truncate for notification
                preview = round_output[:500]
                self.output_router.notify_activity(
                    "processing_complete",
                    f"Processed message from {trigger_channel}",
                    metadata={
                        "trigger_channel": trigger_channel,
                        "trigger_sender": trigger_sender,
                        "output_preview": preview,
                    },
                )

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

            # Submit to executor - pass is_direct so executor skips
            # callback/queue for direct tools
            job_id = await self.executor.submit_from_event(
                tool_call, is_direct=is_direct
            )

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

    async def _add_native_tool_results(
        self,
        controller: Controller,
        job_ids: list[str],
        tasks: dict[str, asyncio.Task],
        tool_call_ids: dict[str, str],
    ) -> None:
        """Wait for tools and add results as role='tool' messages.

        For native tool calling mode. Appends proper tool messages
        to the conversation so the LLM sees structured results.
        """
        if not tasks:
            return

        results_list = await asyncio.gather(
            *[tasks[jid] for jid in job_ids],
            return_exceptions=True,
        )

        for job_id, result in zip(job_ids, results_list):
            tool_name = job_id.rsplit("_", 1)[0] if "_" in job_id else job_id
            short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
            label = f"{tool_name}[{short_id}]" if short_id else tool_name
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

            # Add as proper tool message to conversation
            controller.conversation.append(
                "tool",
                content,
                tool_call_id=tool_call_id,
                name=tool_name,
            )

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
            tool_name = job_id.rsplit("_", 1)[0] if "_" in job_id else job_id
            short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
            label = f"{tool_name}[{short_id}]" if short_id else tool_name

            if isinstance(result, Exception):
                result_strs.append(f"## {job_id} - FAILED\n{str(result)}")
                logger.info("Tool %s: failed", tool_name)
                self.output_router.notify_activity(
                    "tool_error", f"[{label}] FAILED: {result}"
                )
            elif result is not None:
                output = result.output if result.output else ""
                if result.error:
                    result_strs.append(f"## {job_id} - ERROR\n{result.error}\n{output}")
                    logger.info("Tool %s: error", tool_name)
                    self.output_router.notify_activity(
                        "tool_error", f"[{label}] ERROR: {result.error}"
                    )
                else:
                    status = (
                        "OK" if result.exit_code == 0 else f"exit={result.exit_code}"
                    )
                    result_strs.append(f"## {job_id} - {status}\n{output}")
                    logger.info("Tool %s: done", tool_name)
                    self.output_router.notify_activity(
                        "tool_done", f"[{label}] {status}"
                    )

        return "\n\n".join(result_strs) if result_strs else ""

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

    def _on_bg_complete(self, event: TriggerEvent) -> None:
        """Callback fired by executor when a BACKGROUND tool completes.

        Direct tools never fire this - the executor skips the callback
        for them (is_direct=True). Only background tools reach here.
        """
        if not self._running:
            return

        job_id = getattr(event, "job_id", "")
        is_subagent = job_id.startswith("agent_")
        error = event.context.get("error") if event.context else None
        content = (
            event.content if isinstance(event.content, str) else str(event.content)
        )

        # Build label: for sub-agents use the agent name, for tools use tool name
        if is_subagent:
            # job_id format: "agent_<name>_<hex>" e.g. "agent_explore_5c3c56e6"
            parts = job_id.split("_")
            sa_name = parts[1] if len(parts) >= 3 else job_id
            short_id = parts[-1][:6] if len(parts) >= 3 else ""
            label = f"{sa_name}[{short_id}]" if short_id else sa_name
            activity_type_done = "subagent_done"
            activity_type_error = "subagent_error"
        else:
            tool_name = job_id.rsplit("_", 1)[0] if "_" in job_id else job_id
            short_id = job_id.rsplit("_", 1)[-1][:6] if "_" in job_id else ""
            label = f"{tool_name}[{short_id}]" if short_id else tool_name
            activity_type_done = "tool_done"
            activity_type_error = "tool_error"

        # Extract sub-agent metadata if available
        sa_meta = event.context.get("subagent_metadata", {}) if event.context else {}
        tools_used = sa_meta.get("tools_used", [])

        if error:
            self.output_router.notify_activity(
                activity_type_error,
                f"[{label}] ERROR: {error}",
                metadata={"job_id": job_id},
            )
        else:
            if is_subagent:
                tools_summary = ", ".join(tools_used[:10]) if tools_used else "none"
                detail = f"[{label}] tools: {tools_summary}"
                self.output_router.notify_activity(
                    activity_type_done,
                    detail,
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
                    activity_type_done,
                    f"[{label}] DONE",
                    metadata={"job_id": job_id},
                )

        logger.info("Background job completed", job_id=job_id)
        asyncio.create_task(self._process_event(event))

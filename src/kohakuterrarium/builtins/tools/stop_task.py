"""Stop task tool. Cancel a running background tool or sub-agent."""

from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("stop_task")
class StopTaskTool(BaseTool):
    """Cancel a running background tool or sub-agent by job ID."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "stop_task"

    @property
    def description(self) -> str:
        return "Cancel a running background task (tool or sub-agent) by job ID"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    def get_parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID to cancel. Use [/jobs] to list running jobs.",
                },
            },
            "required": ["job_id"],
        }

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        job_id = args.get("job_id", "").strip()
        if not job_id:
            return ToolResult(error="job_id is required", exit_code=1)

        if not context or not context.agent:
            return ToolResult(error="Agent context required", exit_code=1)

        cancelled = await context.agent.executor.cancel(job_id)
        if cancelled:
            logger.info("Task cancelled", job_id=job_id)
            return ToolResult(output=f"Cancelled: {job_id}", exit_code=0)

        # Check if it exists but is already done
        status = context.agent.executor.get_status(job_id)
        if status:
            return ToolResult(
                output=f"Task {job_id} is already {status.state.value}",
                exit_code=0,
            )

        return ToolResult(error=f"Task not found: {job_id}", exit_code=1)

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# stop_task

Cancel a running background tool or sub-agent.

## Arguments

- `job_id` (required): The job ID to cancel. Use the `jobs` command to list running jobs.

## Behavior

- Cancels the asyncio task associated with the job
- The job status changes to CANCELLED
- If the job is already done, reports its current status
- Does not affect direct (blocking) tools, only background tasks

## Use cases

- Cancel a long-running sub-agent (e.g., explore taking too long)
- Cancel a background tool (e.g., terrarium_observe you no longer need)
- Cancel a wait_channel that is no longer relevant
"""

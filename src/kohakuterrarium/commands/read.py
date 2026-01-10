"""
Read command - Read job output.

Usage: ##read job_id [--lines N] [--offset M]##
"""

from typing import TYPE_CHECKING, Any

from kohakuterrarium.commands.base import BaseCommand, CommandResult, parse_command_args

if TYPE_CHECKING:
    from kohakuterrarium.core.controller import ControllerContext


class ReadCommand(BaseCommand):
    """
    Read job output command.

    Retrieves output from a completed or running job.

    Usage:
        ##read job_123##
        ##read job_123 --lines 50##
        ##read job_123 --lines 50 --offset 10##
    """

    @property
    def command_name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "Read output from a job"

    async def _execute(self, args: str, context: Any) -> CommandResult:
        """Read job output."""
        job_id, kwargs = parse_command_args(args)

        if not job_id:
            return CommandResult(error="No job_id provided. Usage: ##read job_id##")

        # Get optional parameters
        lines = int(kwargs.get("lines", 0))
        offset = int(kwargs.get("offset", 0))

        # Get job result from context
        # Context should have get_job_result method
        if not hasattr(context, "get_job_result"):
            return CommandResult(error="Context does not support job result retrieval")

        result = context.get_job_result(job_id)
        if result is None:
            # Check if job exists but not completed
            if hasattr(context, "get_job_status"):
                status = context.get_job_status(job_id)
                if status is not None:
                    if status.is_running:
                        return CommandResult(
                            content=f"[Job {job_id} is still running: {status.to_context_string()}]"
                        )
                    elif not status.is_complete:
                        return CommandResult(content=f"[Job {job_id} is pending]")
            return CommandResult(error=f"Job not found: {job_id}")

        # Get output
        output = result.output or ""

        # Apply slicing if requested
        if lines > 0 or offset > 0:
            output_lines = output.split("\n")
            if offset > 0:
                output_lines = output_lines[offset:]
            if lines > 0:
                output_lines = output_lines[:lines]
            output = "\n".join(output_lines)

        # Format result
        if result.error:
            content = f"## Job {job_id} (error)\n\nError: {result.error}\n\n"
            if output:
                content += f"Output:\n```\n{output}\n```"
        else:
            content = f"## Job {job_id} Output\n\n```\n{output}\n```"

            if result.exit_code is not None:
                content += f"\n\nExit code: {result.exit_code}"

        return CommandResult(content=content)


class InfoCommand(BaseCommand):
    """
    Get documentation for a tool or sub-agent.

    Usage:
        ##info tool_name##
        ##info subagent_name##
    """

    @property
    def command_name(self) -> str:
        return "info"

    @property
    def description(self) -> str:
        return "Get documentation for a tool or sub-agent"

    async def _execute(self, args: str, context: Any) -> CommandResult:
        """Get tool/subagent documentation."""
        target_name, _ = parse_command_args(args)

        if not target_name:
            return CommandResult(error="No name provided. Usage: ##info name##")

        # Try to get tool info
        if hasattr(context, "get_tool_info"):
            tool_info = context.get_tool_info(target_name)
            if tool_info is not None:
                return CommandResult(
                    content=tool_info.documentation
                    or f"# {target_name}\n\n{tool_info.description}"
                )

        # Try to get subagent info
        if hasattr(context, "get_subagent_info"):
            subagent_info = context.get_subagent_info(target_name)
            if subagent_info is not None:
                return CommandResult(content=subagent_info)

        return CommandResult(error=f"Not found: {target_name}")


# Default command instances
read_command = ReadCommand()
info_command = InfoCommand()

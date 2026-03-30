"""Ask user tool - request human input mid-execution."""

import asyncio
import sys
from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode, ToolResult
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("ask_user")
class AskUserTool(BaseTool):
    """Request human input mid-execution (CLI-only)."""

    @property
    def tool_name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return "Ask the user a question and wait for response"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Ask user for input via stdin."""
        question = args.get("question", "") or args.get("body", "")
        if not question:
            return ToolResult(error="Question is required")

        try:
            # Print question to stderr (stdout may be used for agent output)
            sys.stderr.write(f"\n[Agent Question] {question}\n> ")
            sys.stderr.flush()

            # Read from stdin in a thread to not block the event loop
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, sys.stdin.readline)
            response = response.strip()

            if not response:
                return ToolResult(output="(no response)", exit_code=0)

            logger.debug("User responded to question")
            return ToolResult(output=response, exit_code=0)

        except EOFError:
            return ToolResult(error="No input available (stdin closed)")
        except Exception as e:
            return ToolResult(error=f"Failed to get user input: {e}")

    def get_full_documentation(self) -> str:
        return """# ask_user

Ask the user a question and wait for their response. For human-in-the-loop
patterns: approval workflows, clarification, interactive agents.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| question | content | Question to ask the user (required) |

## Examples

```
[/ask_user]
I found 3 potential approaches. Which should I use?
1. Refactor the existing module
2. Create a new module
3. Use a third-party library
[ask_user/]
```

```
[/ask_user]
Should I proceed with deleting the deprecated files? (yes/no)
[ask_user/]
```

## Output

Returns the user's text response.

## Mode

BACKGROUND - blocks until user responds but doesn't block other tools.

## LIMITATIONS

- CLI-only: reads from stdin, writes question to stderr
- Will hang if stdin is not available (non-interactive mode)
"""

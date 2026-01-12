"""
Edit tool - apply unified diff patches to files.

Accepts standard unified diff format for precise file modifications.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # Lines with prefixes: ' ', '-', '+'


class DiffParseError(Exception):
    """Error parsing diff format."""

    pass


def parse_unified_diff(diff_text: str) -> list[DiffHunk]:
    """
    Parse unified diff format into hunks.

    Supports standard unified diff:
    - Lines starting with '-' are removed
    - Lines starting with '+' are added
    - Lines starting with ' ' are context (unchanged)
    - @@ -old_start,old_count +new_start,new_count @@ markers

    Args:
        diff_text: The unified diff content

    Returns:
        List of DiffHunk objects

    Raises:
        DiffParseError: If diff format is invalid
    """
    lines = diff_text.split("\n")
    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    hunk_pattern = re.compile(r"^@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip file headers (--- and +++ lines)
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue

        # Check for hunk header
        match = hunk_pattern.match(line)
        if match:
            # Save previous hunk
            if current_hunk:
                hunks.append(current_hunk)

            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1

            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=[],
            )
            i += 1
            continue

        # If we're in a hunk, collect lines
        if current_hunk is not None:
            if line.startswith(" ") or line.startswith("-") or line.startswith("+"):
                current_hunk.lines.append(line)
            elif line.startswith("\\"):
                # "\ No newline at end of file" - skip
                pass
            elif line == "":
                # Empty line could be context (space was stripped) or end of hunk
                # Treat as context if we haven't reached expected line count
                expected = current_hunk.old_count + current_hunk.new_count
                actual_context = sum(
                    1
                    for l in current_hunk.lines
                    if l.startswith(" ") or l.startswith("-") or l.startswith("+")
                )
                if actual_context < expected:
                    current_hunk.lines.append(" ")  # Treat as context
            i += 1
            continue

        i += 1

    # Save last hunk
    if current_hunk:
        hunks.append(current_hunk)

    if not hunks:
        raise DiffParseError("No valid hunks found in diff")

    return hunks


def apply_hunks(original: str, hunks: list[DiffHunk]) -> str:
    """
    Apply diff hunks to original content.

    Args:
        original: Original file content
        hunks: List of parsed hunks to apply

    Returns:
        Modified content

    Raises:
        DiffParseError: If hunk cannot be applied (context mismatch)
    """
    original_lines = original.split("\n")
    # Track if original ended with newline
    had_trailing_newline = original.endswith("\n")
    if had_trailing_newline and original_lines and original_lines[-1] == "":
        original_lines = original_lines[:-1]

    # Apply hunks in reverse order to preserve line numbers
    sorted_hunks = sorted(hunks, key=lambda h: h.old_start, reverse=True)

    for hunk in sorted_hunks:
        # Extract expected old lines and new lines from hunk
        old_lines = []
        new_lines = []

        for line in hunk.lines:
            if line.startswith(" "):
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line.startswith("-"):
                old_lines.append(line[1:])
            elif line.startswith("+"):
                new_lines.append(line[1:])

        # Find where to apply (0-indexed)
        start_idx = hunk.old_start - 1

        # Verify context matches (if we have old lines to match)
        if old_lines:
            end_idx = start_idx + len(old_lines)
            if end_idx > len(original_lines):
                raise DiffParseError(
                    f"Hunk at line {hunk.old_start} extends beyond file "
                    f"(file has {len(original_lines)} lines, hunk needs {end_idx})"
                )

            actual_lines = original_lines[start_idx:end_idx]

            # Check for context match
            for i, (expected, actual) in enumerate(zip(old_lines, actual_lines)):
                if expected != actual:
                    raise DiffParseError(
                        f"Context mismatch at line {hunk.old_start + i}:\n"
                        f"  Expected: {expected!r}\n"
                        f"  Actual:   {actual!r}"
                    )

            # Apply: remove old, insert new
            original_lines[start_idx:end_idx] = new_lines
        else:
            # Pure insertion (no old lines)
            original_lines[start_idx:start_idx] = new_lines

    result = "\n".join(original_lines)
    if had_trailing_newline:
        result += "\n"

    return result


@register_builtin("edit")
class EditTool(BaseTool):
    """
    Tool for editing files using unified diff format.

    Accepts standard unified diff with:
    - @@ -start,count +start,count @@ hunk headers
    - Lines starting with '-' for deletions
    - Lines starting with '+' for additions
    - Lines starting with ' ' for context
    """

    @property
    def tool_name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return "Edit file using unified diff format"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Apply diff to file."""
        path = args.get("path", "")
        diff = args.get("diff", "")

        if not path:
            return ToolResult(
                error="No path provided. Use @@path= to specify the file:\n\n"
                "[/edit]\n"
                "@@path=path/to/file.py\n"
                "@@ -10,2 +10,3 @@\n"
                " context line\n"
                "+new line\n"
                "[edit/]"
            )
        if not diff:
            return ToolResult(error="No diff provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        try:
            # Read current content
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                original = await f.read()

            # Parse diff
            try:
                hunks = parse_unified_diff(diff)
            except DiffParseError as e:
                return ToolResult(
                    error=f"Invalid diff format: {e}\n\n"
                    "COMPLETE EXAMPLE - copy this format exactly:\n"
                    "[/edit]\n"
                    "@@path=src/file.py\n"
                    "@@ -10,3 +10,4 @@\n"
                    " context line (starts with space)\n"
                    "-line to remove (starts with minus)\n"
                    "+line to add (starts with plus)\n"
                    "+another new line\n"
                    "[edit/]\n\n"
                    "IMPORTANT:\n"
                    "- @@path= is the tool argument (file path)\n"
                    "- @@ -10,3 +10,4 @@ is the diff hunk header (line numbers)\n"
                    "- These are DIFFERENT! Don't confuse them.\n"
                    "- Lines starting with space = context (unchanged)\n"
                    "- Lines starting with - = removed\n"
                    "- Lines starting with + = added"
                )

            # Apply hunks
            try:
                new_content = apply_hunks(original, hunks)
            except DiffParseError as e:
                return ToolResult(
                    error=f"Failed to apply diff: {e}\n\n"
                    'TIP: Use <read path="file"/> first to see exact line '
                    "numbers and content, then match them exactly in your diff."
                )

            # Check if anything changed
            if new_content == original:
                return ToolResult(
                    output="No changes made (diff produced identical content)",
                    exit_code=0,
                )

            # Write back
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(new_content)

            # Calculate stats
            old_lines = original.count("\n")
            new_lines = new_content.count("\n")
            added = sum(1 for h in hunks for l in h.lines if l.startswith("+"))
            removed = sum(1 for h in hunks for l in h.lines if l.startswith("-"))

            logger.debug(
                "File edited",
                file_path=str(file_path),
                hunks=len(hunks),
                added=added,
                removed=removed,
            )

            return ToolResult(
                output=(
                    f"Edited {file_path}\n"
                    f"  {len(hunks)} hunk(s) applied\n"
                    f"  +{added} -{removed} lines"
                ),
                exit_code=0,
            )

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Edit failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# edit

Edit file using unified diff format.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | attribute | Path to file (required) |
| diff | body | Unified diff content |

## Diff Format

```
@@ -start,count +start,count @@
-line to remove
+line to add
 context line (unchanged)
```

- Lines starting with `-` are removed
- Lines starting with `+` are added
- Lines starting with ` ` (space) are context

## Examples

Replace a function:
```xml
<edit path="src/main.py">
@@ -5,3 +5,3 @@
-def hello():
-    print("Hi")
+def hello():
+    print("Hello, World!")
</edit>
```

Add import:
```xml
<edit path="src/utils.py">
@@ -1,1 +1,2 @@
 import os
+import sys
</edit>
```

Delete lines:
```xml
<edit path="src/old.py">
@@ -10,3 +10,1 @@
 # Keep this comment
-# Delete this
-# And this
</edit>
```

## Tips

- Use `<read path="file"/>` first to see line numbers
- Include context lines to anchor changes
- Line numbers in @@ are 1-indexed
- Multiple hunks can be in one diff
"""

"""
File operation tools - Read, Write, Glob, Grep.

Essential tools for SWE agents to interact with the filesystem.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class ReadTool(BaseTool):
    """
    Tool for reading file contents.

    Supports reading entire files or specific line ranges.
    """

    @property
    def tool_name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "Read file contents"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Read file contents."""
        path = args.get("path", "")
        if not path:
            return ToolResult(error="No path provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        # Get optional parameters
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 0))

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Apply offset and limit
            if offset > 0:
                lines = lines[offset:]
            if limit > 0:
                lines = lines[:limit]

            # Format with line numbers
            output_lines = []
            start_line = offset + 1
            for i, line in enumerate(lines):
                line_num = start_line + i
                # Remove trailing newline for cleaner output
                line_content = line.rstrip("\n\r")
                output_lines.append(f"{line_num:6}→{line_content}")

            output = "\n".join(output_lines)

            # Add truncation notice if applicable
            if limit > 0 and offset + limit < total_lines:
                output += f"\n\n... (showing lines {offset + 1}-{offset + len(lines)} of {total_lines})"

            logger.debug(
                "File read",
                file_path=str(file_path),
                lines_read=len(lines),
            )

            return ToolResult(output=output, exit_code=0)

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Read failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# read

Read file contents with optional line range.

## Arguments

- path (required): Path to the file to read
- offset (optional): Line number to start from (0-based, default: 0)
- limit (optional): Maximum number of lines to read (default: all)

## Examples

Read entire file:
```
##tool##
name: read
args:
  path: src/main.py
##tool##
```

Read lines 10-30:
```
##tool##
name: read
args:
  path: src/main.py
  offset: 10
  limit: 20
##tool##
```

## Output

Returns file contents with line numbers in format:
```
     1→first line
     2→second line
```
"""


class WriteTool(BaseTool):
    """
    Tool for writing/creating files.

    Creates parent directories if needed.
    """

    @property
    def tool_name(self) -> str:
        return "write"

    @property
    def description(self) -> str:
        return "Write content to a file"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Write content to file."""
        path = args.get("path", "")
        content = args.get("content", "")

        if not path:
            return ToolResult(error="No path provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists for logging
            exists = file_path.exists()

            # Write content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            action = "Updated" if exists else "Created"
            lines = content.count("\n") + 1 if content else 0

            logger.debug(
                "File written",
                file_path=str(file_path),
                action=action.lower(),
                lines=lines,
            )

            return ToolResult(
                output=f"{action} {file_path} ({lines} lines, {len(content)} bytes)",
                exit_code=0,
            )

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Write failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# write

Write content to a file. Creates the file if it doesn't exist.
Creates parent directories automatically.

## Arguments

- path (required): Path to the file to write
- content (required): Content to write to the file

## Examples

Create a new file:
```
##tool##
name: write
args:
  path: src/hello.py
  content: |
    def hello():
        print("Hello, World!")

    if __name__ == "__main__":
        hello()
##tool##
```

## Notes

- Overwrites existing files
- Creates parent directories if they don't exist
- Content should use proper indentation in YAML
"""


class EditTool(BaseTool):
    """
    Tool for editing files via string replacement.

    Finds old_string and replaces with new_string.
    Requires unique match in file.
    """

    @property
    def tool_name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return "Edit file by replacing text"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Edit file by string replacement."""
        path = args.get("path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")

        if not path:
            return ToolResult(error="No path provided")
        if not old_string:
            return ToolResult(error="No old_string provided")
        if old_string == new_string:
            return ToolResult(error="old_string and new_string are identical")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        try:
            # Read current content
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Check for match
            count = content.count(old_string)

            if count == 0:
                # Try to find similar matches for better error message
                lines_with_partial = []
                for i, line in enumerate(content.split("\n"), 1):
                    # Check first 20 chars of old_string
                    if old_string[:20] in line:
                        lines_with_partial.append(f"  Line {i}: {line[:80]}...")

                hint = ""
                if lines_with_partial:
                    hint = "\n\nPartial matches found:\n" + "\n".join(
                        lines_with_partial[:3]
                    )

                return ToolResult(
                    error=f"old_string not found in file.{hint}\n\n"
                    "Tip: Use 'read' tool first to see exact content."
                )

            if count > 1:
                return ToolResult(
                    error=f"old_string found {count} times. Must be unique.\n"
                    "Add more context (surrounding lines) to make it unique."
                )

            # Perform replacement
            new_content = content.replace(old_string, new_string, 1)

            # Write back
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Calculate diff stats
            old_lines = old_string.count("\n") + 1
            new_lines = new_string.count("\n") + 1
            diff = new_lines - old_lines

            diff_str = ""
            if diff > 0:
                diff_str = f" (+{diff} lines)"
            elif diff < 0:
                diff_str = f" ({diff} lines)"

            logger.debug(
                "File edited",
                file_path=str(file_path),
                old_lines=old_lines,
                new_lines=new_lines,
            )

            return ToolResult(
                output=f"Edited {file_path}: replaced {old_lines} lines with {new_lines} lines{diff_str}",
                exit_code=0,
            )

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Edit failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# edit

Edit file by replacing text. Finds old_string and replaces with new_string.

## Arguments

- path (required): Path to the file to edit
- old_string (required): Exact text to find and replace
- new_string (required): Text to replace with

## Examples

Replace a function:
```
##tool##
name: edit
args:
  path: src/main.py
  old_string: |
    def hello():
        print("Hi")
  new_string: |
    def hello():
        print("Hello, World!")
##tool##
```

Add import at top:
```
##tool##
name: edit
args:
  path: src/utils.py
  old_string: |
    import os
  new_string: |
    import os
    import sys
##tool##
```

## Requirements

- old_string must exist exactly once in file
- If multiple matches, add more context to make unique
- Use 'read' tool first to see exact content

## Notes

- Preserves file encoding (UTF-8)
- Whitespace and indentation must match exactly
- Use YAML multiline syntax (|) for multi-line content
"""


class GlobTool(BaseTool):
    """
    Tool for finding files by pattern.

    Supports glob patterns like **/*.py
    """

    @property
    def tool_name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "Find files matching a pattern"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Find files matching pattern."""
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(error="No pattern provided")

        # Get base path
        base_path = args.get("path", ".")
        base = Path(base_path).expanduser().resolve()

        if not base.exists():
            return ToolResult(error=f"Path not found: {base_path}")

        # Get limit
        limit = int(args.get("limit", 100))

        try:
            # Use glob to find files
            if "**" in pattern:
                matches = list(base.glob(pattern))
            else:
                matches = list(base.glob(pattern))

            # Sort by modification time (newest first)
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Apply limit
            total = len(matches)
            if limit > 0 and len(matches) > limit:
                matches = matches[:limit]

            # Format output
            output_lines = []
            for match in matches:
                try:
                    rel_path = match.relative_to(base)
                except ValueError:
                    rel_path = match
                output_lines.append(str(rel_path))

            output = "\n".join(output_lines)

            if total > len(matches):
                output += f"\n\n... ({total} total, showing {len(matches)})"

            logger.debug(
                "Glob search",
                pattern=pattern,
                matches=len(matches),
            )

            return ToolResult(output=output or "(no matches)", exit_code=0)

        except Exception as e:
            logger.error("Glob failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# glob

Find files matching a glob pattern.

## Arguments

- pattern (required): Glob pattern (e.g., "**/*.py", "src/*.js")
- path (optional): Base directory to search in (default: current directory)
- limit (optional): Maximum number of results (default: 100)

## Examples

Find all Python files:
```
##tool##
name: glob
args:
  pattern: "**/*.py"
##tool##
```

Find files in specific directory:
```
##tool##
name: glob
args:
  pattern: "*.ts"
  path: src/components
##tool##
```

## Patterns

- `*` - matches any characters except /
- `**` - matches any characters including /
- `?` - matches single character
- `[abc]` - matches a, b, or c

## Output

Returns list of matching file paths, sorted by modification time (newest first).
"""


class GrepTool(BaseTool):
    """
    Tool for searching file contents.

    Supports regex patterns and file type filtering.
    """

    @property
    def tool_name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search file contents for a pattern"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Search files for pattern."""
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(error="No pattern provided")

        # Get base path
        base_path = args.get("path", ".")
        base = Path(base_path).expanduser().resolve()

        if not base.exists():
            return ToolResult(error=f"Path not found: {base_path}")

        # Get options
        file_pattern = args.get("glob", "**/*")
        limit = int(args.get("limit", 50))
        case_insensitive = args.get("ignore_case", False)

        # Compile regex
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(error=f"Invalid regex: {e}")

        try:
            matches = []
            files_searched = 0

            # Find files to search
            if base.is_file():
                files = [base]
            else:
                files = list(base.glob(file_pattern))

            for file_path in files:
                if not file_path.is_file():
                    continue

                # Skip binary files
                try:
                    with open(file_path, "rb") as f:
                        chunk = f.read(1024)
                        if b"\x00" in chunk:
                            continue
                except Exception:
                    continue

                files_searched += 1

                try:
                    with open(file_path, encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                try:
                                    rel_path = file_path.relative_to(base)
                                except ValueError:
                                    rel_path = file_path

                                matches.append(
                                    {
                                        "file": str(rel_path),
                                        "line": line_num,
                                        "content": line.rstrip(),
                                    }
                                )

                                if len(matches) >= limit:
                                    break
                except Exception:
                    continue

                if len(matches) >= limit:
                    break

            # Format output
            output_lines = []
            for match in matches:
                output_lines.append(
                    f"{match['file']}:{match['line']}: {match['content']}"
                )

            output = "\n".join(output_lines)

            if len(matches) >= limit:
                output += (
                    f"\n\n... (limit {limit} reached, {files_searched} files searched)"
                )
            else:
                output += f"\n\n({len(matches)} matches in {files_searched} files)"

            logger.debug(
                "Grep search",
                pattern=pattern,
                matches=len(matches),
                files=files_searched,
            )

            return ToolResult(output=output or "(no matches)", exit_code=0)

        except Exception as e:
            logger.error("Grep failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# grep

Search file contents for a pattern (regex supported).

## Arguments

- pattern (required): Search pattern (regex)
- path (optional): Directory or file to search (default: current directory)
- glob (optional): File pattern to search in (default: "**/*")
- limit (optional): Maximum number of matches (default: 50)
- ignore_case (optional): Case-insensitive search (default: false)

## Examples

Search for function definitions:
```
##tool##
name: grep
args:
  pattern: "def \\w+\\("
  glob: "**/*.py"
##tool##
```

Case-insensitive search:
```
##tool##
name: grep
args:
  pattern: "todo|fixme"
  ignore_case: true
##tool##
```

Search in specific file:
```
##tool##
name: grep
args:
  pattern: "import"
  path: src/main.py
##tool##
```

## Output

Returns matches in format:
```
file.py:10: matching line content
file.py:25: another match
```
"""

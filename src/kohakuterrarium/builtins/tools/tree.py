"""
Tree tool - list files with frontmatter summaries.

Shows directory structure and extracts summary from YAML frontmatter.
"""

import re
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

# Regex to extract YAML frontmatter
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(content: str) -> dict[str, Any]:
    """
    Parse YAML frontmatter from markdown content.

    Simple parser that handles common cases without full YAML dependency.
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}

    frontmatter = {}
    yaml_content = match.group(1)

    for line in yaml_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Simple key: value parsing
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Handle quoted strings
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            # Handle arrays [item1, item2]
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                value = [item.strip().strip("\"'") for item in items if item.strip()]

            # Handle booleans
            if value in ("true", "True", "yes", "Yes"):
                value = True
            elif value in ("false", "False", "no", "No"):
                value = False

            frontmatter[key] = value

    return frontmatter


async def build_tree(
    path: Path,
    prefix: str = "",
    max_depth: int = 3,
    current_depth: int = 0,
    show_hidden: bool = False,
) -> list[str]:
    """
    Build tree output with frontmatter summaries.

    Returns list of formatted lines.
    """
    if current_depth >= max_depth:
        return []

    lines = []

    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return [f"{prefix}(permission denied)"]

    # Filter hidden files
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith(".")]

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            # Recurse into directory
            child_lines = await build_tree(
                entry,
                child_prefix,
                max_depth,
                current_depth + 1,
                show_hidden,
            )
            lines.extend(child_lines)
        else:
            # For markdown files, try to get frontmatter summary
            summary = ""
            if entry.suffix in (".md", ".markdown"):
                try:
                    async with aiofiles.open(
                        entry, encoding="utf-8", errors="ignore"
                    ) as f:
                        content = await f.read()
                    fm = parse_frontmatter(content)
                    if fm.get("summary"):
                        summary = f" - {fm['summary']}"
                    elif fm.get("title"):
                        summary = f" - {fm['title']}"
                    elif fm.get("description"):
                        summary = f" - {fm['description']}"

                    # Show protected status
                    if fm.get("protected"):
                        summary = f" [protected]{summary}"
                except Exception:
                    pass

            lines.append(f"{prefix}{connector}{entry.name}{summary}")

    return lines


@register_builtin("tree")
class TreeTool(BaseTool):
    """
    Tool for listing directory structure with frontmatter summaries.

    Useful for discovering memory structure and understanding file contents.
    """

    @property
    def tool_name(self) -> str:
        return "tree"

    @property
    def description(self) -> str:
        return "List files in tree format with summaries from frontmatter"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """List directory tree with frontmatter summaries."""
        # Get path (body content or path attribute)
        path_str = args.get("path") or args.get("_body", ".").strip() or "."
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            return ToolResult(error=f"Path not found: {path_str}")

        if not path.is_dir():
            return ToolResult(error=f"Not a directory: {path_str}")

        # Options
        max_depth = int(args.get("depth", 3))
        show_hidden = args.get("hidden", "false").lower() in ("true", "yes", "1")

        try:
            lines = [f"{path.name}/"]
            tree_lines = await build_tree(path, "", max_depth, 0, show_hidden)
            lines.extend(tree_lines)

            output = "\n".join(lines)

            logger.debug(
                "Tree listing",
                path=str(path),
                depth=max_depth,
                lines=len(lines),
            )

            return ToolResult(output=output, exit_code=0)

        except Exception as e:
            logger.error("Tree failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# tree

List directory structure with frontmatter summaries.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | body or attribute | Directory to list (default: cwd) |
| depth | attribute | Max recursion depth (default: 3) |
| hidden | attribute | Show hidden files (default: false) |

## Examples

List current directory:
```xml
<tree/>
```

List specific directory:
```xml
<tree>memory</tree>
```

With options:
```xml
<tree path="memory" depth="5"/>
```

## Frontmatter

For markdown files, extracts and displays:
- `summary`: Brief description
- `title`: File title (fallback)
- `description`: Description (fallback)
- `protected`: Shows [protected] marker

## Output Format

```
memory/
├── character.md - Cat girl persona definition
├── rules.md [protected] - Core agent rules
├── context.md - Current session context
└── facts/
    ├── user.md - Known user information
    └── project.md - Project details
```
"""

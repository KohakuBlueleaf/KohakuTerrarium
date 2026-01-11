"""
System prompt plugins - modular components for prompt aggregation.

Each plugin contributes a section to the final system prompt.
Plugins are sorted by priority (lower = earlier in prompt).
"""

import os
import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from kohakuterrarium.utils.logging import get_logger

if TYPE_CHECKING:
    from kohakuterrarium.core.registry import Registry

logger = get_logger(__name__)


@dataclass
class PluginContext:
    """Context passed to plugins during aggregation."""

    registry: "Registry | None" = None
    working_dir: Path = field(default_factory=Path.cwd)
    agent_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PromptPlugin(Protocol):
    """Protocol for system prompt plugins."""

    @property
    def name(self) -> str:
        """Unique plugin name."""
        ...

    @property
    def priority(self) -> int:
        """Sort priority (lower = earlier in prompt)."""
        ...

    def get_content(self, context: PluginContext) -> str | None:
        """
        Generate content to add to system prompt.

        Args:
            context: Plugin context with registry, paths, etc.

        Returns:
            Content string or None to skip.
        """
        ...


class BasePlugin(ABC):
    """Base class for prompt plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name."""
        ...

    @property
    def priority(self) -> int:
        """Sort priority (lower = earlier). Default: 50."""
        return 50

    @abstractmethod
    def get_content(self, context: PluginContext) -> str | None:
        """Generate content for system prompt."""
        ...


class ToolListPlugin(BasePlugin):
    """
    Generates tool list section.

    Outputs: tool name + one-line description for each tool.
    """

    @property
    def name(self) -> str:
        return "tool_list"

    @property
    def priority(self) -> int:
        return 50

    def get_content(self, context: PluginContext) -> str | None:
        if not context.registry:
            return None

        tool_names = context.registry.list_tools()
        if not tool_names:
            return None

        lines = ["## Available Tools", ""]
        for name in sorted(tool_names):
            info = context.registry.get_tool_info(name)
            description = info.description if info else "No description"
            lines.append(f"- `{name}`: {description}")

        lines.append("")
        lines.append("Use `[/info]tool_name[info/]` for full documentation.")

        return "\n".join(lines)


class FrameworkHintsPlugin(BasePlugin):
    """
    Adds framework hints (tool call syntax, commands).

    This is the core syntax that all agents need.
    """

    @property
    def name(self) -> str:
        return "framework_hints"

    @property
    def priority(self) -> int:
        return 60

    def get_content(self, context: PluginContext) -> str | None:
        return """## Tool Call Syntax

Use this format to call tools:

```
[/tool_name]
@@arg=value
content here
[tool_name/]
```

### Examples:

```
[/bash]ls -la[bash/]
```

```
[/read]@@path=src/main.py[read/]
```

```
[/write]
@@path=new_file.py
file content here
[write/]
```

```
[/grep]
@@pattern=TODO
@@path=src/
[grep/]
```

## Framework Commands

- `[/info]tool_name[info/]` - Get full documentation for a tool
- `[/read_job]job_id[read_job/]` - Read output from a background job"""


class EnvInfoPlugin(BasePlugin):
    """
    Injects environment information.

    Includes: working directory, git status, platform, date.
    Useful for SWE agents that need context awareness.
    """

    @property
    def name(self) -> str:
        return "env_info"

    @property
    def priority(self) -> int:
        return 10  # Early in prompt

    def get_content(self, context: PluginContext) -> str | None:
        cwd = context.working_dir
        is_git = (cwd / ".git").exists()
        plat = platform.system()
        date = datetime.now().strftime("%Y-%m-%d")

        return f"""<env>
Working directory: {cwd}
Is git repo: {"Yes" if is_git else "No"}
Platform: {plat}
Date: {date}
</env>"""


class ProjectInstructionsPlugin(BasePlugin):
    """
    Loads project-specific instructions from files.

    Searches for: AGENTS.md, .kohaku.md, CLAUDE.md
    in working directory and parent directories up to repo root.

    Deeper files override higher-level files (appended later).
    """

    INSTRUCTION_FILES = ["AGENTS.md", ".kohaku.md", "CLAUDE.md"]

    @property
    def name(self) -> str:
        return "project_instructions"

    @property
    def priority(self) -> int:
        return 20  # After env info, before tools

    def get_content(self, context: PluginContext) -> str | None:
        cwd = context.working_dir
        instructions = []

        # Walk up to find repo root or filesystem root
        current = cwd
        paths_to_check = []

        while current != current.parent:
            paths_to_check.append(current)
            # Stop at git root
            if (current / ".git").exists():
                break
            current = current.parent

        # Check from root down (so deeper files come later and override)
        for path in reversed(paths_to_check):
            for filename in self.INSTRUCTION_FILES:
                filepath = path / filename
                if filepath.exists():
                    try:
                        content = filepath.read_text(encoding="utf-8")
                        rel_path = (
                            filepath.relative_to(cwd)
                            if filepath.is_relative_to(cwd)
                            else filepath
                        )
                        instructions.append(f"# From: {rel_path}\n{content}")
                        logger.debug(
                            "Loaded project instructions", filepath=str(filepath)
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to load instructions",
                            filepath=str(filepath),
                            error=str(e),
                        )

        if not instructions:
            return None

        return "## Project Instructions\n\n" + "\n\n".join(instructions)


# Registry of built-in plugins
BUILTIN_PLUGINS: dict[str, type[BasePlugin]] = {
    "tool_list": ToolListPlugin,
    "framework_hints": FrameworkHintsPlugin,
    "env_info": EnvInfoPlugin,
    "project_instructions": ProjectInstructionsPlugin,
}


def create_plugin(name: str) -> BasePlugin | None:
    """Create a plugin by name."""
    plugin_cls = BUILTIN_PLUGINS.get(name)
    if plugin_cls:
        return plugin_cls()
    return None


def get_default_plugins() -> list[BasePlugin]:
    """Get default plugins for basic agent."""
    return [
        ToolListPlugin(),
        FrameworkHintsPlugin(),
    ]


def get_swe_plugins() -> list[BasePlugin]:
    """Get plugins for SWE-style agents."""
    return [
        EnvInfoPlugin(),
        ProjectInstructionsPlugin(),
        ToolListPlugin(),
        FrameworkHintsPlugin(),
    ]

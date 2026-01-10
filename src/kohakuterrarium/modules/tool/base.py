"""
Tool protocol and base classes.

Tools are executable functions that can be called by the controller.
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class ExecutionMode(Enum):
    """Tool execution mode."""

    DIRECT = "direct"  # Complete all jobs, return results immediately
    BACKGROUND = "background"  # Periodic status updates, context refresh
    STATEFUL = "stateful"  # Multi-turn interaction (like generators)


@dataclass
class ToolConfig:
    """
    Configuration for a tool.

    Attributes:
        timeout: Maximum execution time in seconds (0 = no timeout)
        max_output: Maximum output size in bytes (0 = no limit)
        working_dir: Working directory for execution
        env: Additional environment variables
        extra: Tool-specific configuration
    """

    timeout: float = 60.0
    max_output: int = 0
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """
    Result from tool execution.

    Attributes:
        output: Output content
        exit_code: Exit code (None if not applicable)
        error: Error message if failed
        metadata: Additional result metadata
    """

    output: str = ""
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.error is None and (self.exit_code is None or self.exit_code == 0)


@runtime_checkable
class Tool(Protocol):
    """
    Protocol for tools.

    Tools must implement:
    - name: Tool identifier
    - description: One-line description for system prompt
    - execution_mode: How the tool should be executed
    - execute: Async method to run the tool
    """

    @property
    def tool_name(self) -> str:
        """Tool identifier used in tool calls."""
        ...

    @property
    def description(self) -> str:
        """One-line description for system prompt aggregation."""
        ...

    @property
    def execution_mode(self) -> ExecutionMode:
        """How this tool should be executed."""
        ...

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """
        Execute the tool with given arguments.

        Args:
            args: Arguments parsed from tool call

        Returns:
            ToolResult with output and status
        """
        ...


class BaseTool:
    """
    Base class for tools with common functionality.

    Subclasses should implement:
    - tool_name property
    - description property
    - _execute method
    """

    def __init__(self, config: ToolConfig | None = None):
        self.config = config or ToolConfig()

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Tool identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description."""
        raise NotImplementedError

    @property
    def execution_mode(self) -> ExecutionMode:
        """Default to background execution."""
        return ExecutionMode.BACKGROUND

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute with error handling."""
        try:
            return await self._execute(args)
        except Exception as e:
            return ToolResult(error=str(e))

    @abstractmethod
    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """
        Internal execution method.

        Subclasses implement this without worrying about error handling.
        """
        raise NotImplementedError

    def get_full_documentation(self) -> str:
        """
        Get full documentation for ##info## command.

        Override to provide detailed docs.
        """
        return f"""# {self.tool_name}

{self.description}

## Execution Mode
{self.execution_mode.value}

## Arguments
(No specific arguments documented)

## Output
Tool output as text.
"""


@dataclass
class ToolInfo:
    """
    Tool information for registration and system prompt.

    Attributes:
        tool_name: Tool identifier
        description: One-line description
        execution_mode: Execution mode
        documentation: Full documentation (for ##info##)
    """

    tool_name: str
    description: str
    execution_mode: ExecutionMode = ExecutionMode.BACKGROUND
    documentation: str = ""

    @classmethod
    def from_tool(cls, tool: Tool) -> "ToolInfo":
        """Create ToolInfo from a Tool instance."""
        doc = ""
        if hasattr(tool, "get_full_documentation"):
            doc = tool.get_full_documentation()  # type: ignore
        return cls(
            tool_name=tool.tool_name,
            description=tool.description,
            execution_mode=tool.execution_mode,
            documentation=doc,
        )

    def to_prompt_line(self) -> str:
        """Format for system prompt tool list."""
        return f"- {self.tool_name}: {self.description}"

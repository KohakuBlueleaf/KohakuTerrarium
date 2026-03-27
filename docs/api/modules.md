# Modules API Reference

API reference for the plugin modules in `kohakuterrarium.modules`.

## Input Module (`modules/input/`)

### InputModule Protocol

```python
@runtime_checkable
class InputModule(Protocol):
    """Protocol for input modules."""

    async def start(self) -> None:
        """Start the input module."""

    async def stop(self) -> None:
        """Stop the input module."""

    async def get_input(self) -> TriggerEvent | None:
        """
        Wait for and return the next input event.

        Returns:
            TriggerEvent with type="user_input", or None if no input
        """
```

### BaseInputModule

```python
class BaseInputModule(ABC):
    """Base class for input modules."""

    @property
    def is_running(self) -> bool:
        """Check if module is running."""

    async def start(self) -> None:
        """Start the input module."""

    async def stop(self) -> None:
        """Stop the input module."""

    async def _on_start(self) -> None:
        """Called when module starts. Override in subclass."""

    async def _on_stop(self) -> None:
        """Called when module stops. Override in subclass."""

    @abstractmethod
    async def get_input(self) -> TriggerEvent | None:
        """Get next input event. Must implement."""
```

### Creating Custom Input

```python
from kohakuterrarium.modules.input.base import BaseInputModule
from kohakuterrarium.core.events import TriggerEvent, EventType

class MyInput(BaseInputModule):
    def __init__(self, **config):
        super().__init__()
        self.config = config

    async def _on_start(self) -> None:
        # Initialize your input source
        pass

    async def get_input(self) -> TriggerEvent | None:
        # Get input from your source
        text = await self._get_from_source()

        if not text:
            return None

        return TriggerEvent(
            type=EventType.USER_INPUT,
            content=text,
            context={"source": "my_input"},
        )
```

---

## Output Module (`modules/output/`)

### OutputModule Protocol

```python
@runtime_checkable
class OutputModule(Protocol):
    """Protocol for output modules."""

    async def start(self) -> None:
        """Start the output module."""

    async def stop(self) -> None:
        """Stop the output module."""

    async def write(self, content: str) -> None:
        """Write complete content."""

    async def write_stream(self, chunk: str) -> None:
        """Write a streaming chunk."""

    async def flush(self) -> None:
        """Flush any buffered content."""

    async def on_processing_start(self) -> None:
        """Called when agent starts processing."""
```

### BaseOutputModule

```python
class BaseOutputModule(ABC):
    """Base class for output modules."""

    @property
    def is_running(self) -> bool:
        """Check if module is running."""

    async def start(self) -> None:
        """Start the output module."""

    async def stop(self) -> None:
        """Stop the output module (flushes first)."""

    @abstractmethod
    async def write(self, content: str) -> None:
        """Write complete content. Must implement."""

    async def write_stream(self, chunk: str) -> None:
        """Write streaming chunk. Default calls write()."""

    async def flush(self) -> None:
        """Flush buffered content. Default no-op."""

    async def on_processing_start(self) -> None:
        """Called when processing starts. Default no-op."""

    async def on_processing_end(self) -> None:
        """Called when processing ends. Default no-op."""
```

### Creating Custom Output

```python
from kohakuterrarium.modules.output.base import BaseOutputModule

class MyOutput(BaseOutputModule):
    def __init__(self, **config):
        super().__init__()
        self.buffer = []

    async def write(self, content: str) -> None:
        # Send to your destination
        await self._send(content)

    async def write_stream(self, chunk: str) -> None:
        # Buffer streaming chunks
        self.buffer.append(chunk)

    async def flush(self) -> None:
        # Send buffered content
        if self.buffer:
            content = "".join(self.buffer)
            await self._send(content)
            self.buffer.clear()

    async def on_processing_start(self) -> None:
        # Show typing indicator
        await self._show_typing()
```

### OutputRouter

Routes parse events to appropriate outputs.

```python
class OutputRouter:
    """Routes parse events to output modules."""

    def __init__(
        self,
        default_output: OutputModule,
        named_outputs: dict[str, OutputModule] | None = None,
        suppress_tool_blocks: bool = True,
        suppress_subagent_blocks: bool = True,
    ):
        """Initialize router."""

    async def start(self) -> None:
        """Start router and all output modules."""

    async def stop(self) -> None:
        """Stop router and all output modules."""

    async def route(self, event: ParseEvent) -> None:
        """Route a parse event to appropriate handler."""

    async def flush(self) -> None:
        """Flush all output modules."""

    def get_output_feedback(self) -> str | None:
        """Get feedback string for completed outputs."""

    def get_output_targets(self) -> list[str]:
        """Get list of named output target names."""

    def reset(self) -> None:
        """Reset router state for new round."""

    def clear_all(self) -> None:
        """Clear all state including completed outputs."""
```

---

## Tool Module (`modules/tool/`)

### Tool Protocol

```python
@runtime_checkable
class Tool(Protocol):
    """Protocol for tools."""

    @property
    def tool_name(self) -> str:
        """Tool identifier used in tool calls."""

    @property
    def description(self) -> str:
        """One-line description for system prompt."""

    @property
    def execution_mode(self) -> ExecutionMode:
        """How this tool should be executed."""

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments."""
```

### ExecutionMode Enum

```python
class ExecutionMode(Enum):
    DIRECT = "direct"          # Complete before returning
    BACKGROUND = "background"  # Run in background, report status
    STATEFUL = "stateful"      # Multi-turn interaction
```

### ToolResult

```python
@dataclass
class ToolResult:
    """Result from tool execution."""
    output: str | list[ContentPart] = ""  # Supports multimodal
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""

    def get_text_output(self) -> str:
        """Extract text from multimodal output."""

    def has_images(self) -> bool:
        """Check if result contains images."""

    def is_multimodal(self) -> bool:
        """Check if result uses multimodal format."""
```

### BaseTool

```python
class BaseTool:
    """Base class for tools."""

    def __init__(self, config: ToolConfig | None = None):
        self.config = config or ToolConfig()

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Tool identifier. Must implement."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description. Must implement."""

    @property
    def execution_mode(self) -> ExecutionMode:
        """Default to BACKGROUND."""
        return ExecutionMode.BACKGROUND

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute with error handling."""

    @abstractmethod
    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Internal execution. Must implement."""

    def get_full_documentation(self) -> str:
        """Full docs for [/info] command. Override for detailed docs."""
```

### ToolConfig

```python
@dataclass
class ToolConfig:
    timeout: float = 60.0         # Max execution time
    max_output: int = 0           # Max output bytes (0 = unlimited)
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
```

### Creating Custom Tools

```python
from kohakuterrarium.modules.tool.base import BaseTool, ToolResult, ExecutionMode

class MyTool(BaseTool):
    @property
    def tool_name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something useful"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.BACKGROUND

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        content = args.get("content", "")

        try:
            result = await self._process(content)
            return ToolResult(output=result)
        except Exception as e:
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# my_tool

Does something useful.

## Arguments
| Arg | Type | Description |
|-----|------|-------------|
| content | body | Content to process |

## Example
```
[/my_tool]some content[my_tool/]
```
"""
```

---

## Trigger Module (`modules/trigger/`)

### TriggerModule Protocol

```python
@runtime_checkable
class TriggerModule(Protocol):
    """Protocol for trigger modules."""

    async def start(self) -> None:
        """Start the trigger."""

    async def stop(self) -> None:
        """Stop the trigger."""

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """
        Wait for and return the next trigger event.

        Returns:
            TriggerEvent when trigger fires, or None if stopped
        """

    def set_context(self, context: dict[str, Any]) -> None:
        """Update trigger context."""
```

### BaseTrigger

```python
class BaseTrigger(ABC):
    """Base class for trigger modules."""

    def __init__(
        self,
        prompt: str | None = None,
        **options,
    ):
        """
        Initialize trigger.

        Args:
            prompt: Default prompt for trigger events
            **options: Additional trigger options
        """

    @property
    def is_running(self) -> bool:
        """Check if trigger is running."""

    async def start(self) -> None:
        """Start the trigger."""

    async def stop(self) -> None:
        """Stop the trigger."""

    def set_context(self, context: dict[str, Any]) -> None:
        """Update trigger context."""

    def _on_context_update(self, context: dict[str, Any]) -> None:
        """Called on context update. Override in subclass."""

    @abstractmethod
    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Wait for trigger event. Must implement."""

    def _create_event(
        self,
        event_type: str,
        content: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        """Create a trigger event with default values."""
```

### Creating Custom Triggers

```python
import asyncio
from kohakuterrarium.modules.trigger.base import BaseTrigger
from kohakuterrarium.core.events import TriggerEvent

class IdleTrigger(BaseTrigger):
    def __init__(
        self,
        min_idle_seconds: int = 300,
        prompt: str | None = None,
        **options,
    ):
        super().__init__(prompt=prompt, **options)
        self.min_idle = min_idle_seconds
        self._last_activity = None

    def _on_context_update(self, context: dict) -> None:
        # Track activity
        if context.get("has_activity"):
            self._last_activity = asyncio.get_event_loop().time()

    async def wait_for_trigger(self) -> TriggerEvent | None:
        while self.is_running:
            await asyncio.sleep(10)

            if self._last_activity:
                idle_time = asyncio.get_event_loop().time() - self._last_activity
                if idle_time >= self.min_idle:
                    return self._create_event(
                        "idle",
                        f"Idle for {idle_time:.0f} seconds",
                    )

        return None
```

---

## Sub-Agent Module (`modules/subagent/`)

### SubAgentConfig

```python
@dataclass
class SubAgentConfig:
    """Sub-agent configuration."""
    name: str
    description: str = ""
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    prompt_file: str | None = None
    can_modify: bool = False
    stateless: bool = True
    interactive: bool = False
    context_mode: ContextUpdateMode = ContextUpdateMode.INTERRUPT_RESTART
    output_to: OutputTarget = OutputTarget.CONTROLLER
    output_module: str | None = None
    return_as_context: bool = False
    max_turns: int = 10
    timeout: float = 300.0
    model: str | None = None
    temperature: float | None = None
    memory_path: str | None = None

    def load_prompt(self, agent_path: Path | None = None) -> str:
        """Load system prompt from file or inline."""

    @classmethod
    def from_dict(cls, data: dict) -> "SubAgentConfig":
        """Create from dictionary."""
```

### OutputTarget Enum

```python
class OutputTarget(Enum):
    CONTROLLER = "controller"  # Return to parent controller
    EXTERNAL = "external"      # Stream to user/output
```

### ContextUpdateMode Enum

```python
class ContextUpdateMode(Enum):
    INTERRUPT_RESTART = "interrupt_restart"  # Stop, start new
    QUEUE_APPEND = "queue_append"            # Queue, process after
    FLUSH_REPLACE = "flush_replace"          # Flush, replace immediately
```

### SubAgentResult

```python
@dataclass
class SubAgentResult:
    """Result from sub-agent execution."""
    output: str = ""
    success: bool = True
    error: str | None = None
    turns: int = 0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def truncated(self, max_chars: int = 2000) -> str:
        """Get truncated output."""
```

### SubAgentManager

```python
class SubAgentManager:
    """Manages sub-agent lifecycle."""

    def __init__(
        self,
        parent_registry: Registry,
        llm: LLMProvider,
        job_store: JobStore | None = None,
        agent_path: Path | None = None,
    ):
        """Initialize manager."""

    def register(self, config: SubAgentConfig) -> None:
        """Register a sub-agent configuration."""

    def get_config(self, name: str) -> SubAgentConfig | None:
        """Get sub-agent config by name."""

    def list_subagents(self) -> list[str]:
        """List registered sub-agent names."""

    async def spawn(
        self,
        name: str,
        task: str,
        job_id: str | None = None,
    ) -> str:
        """Spawn sub-agent (returns job_id)."""

    async def wait_for(
        self,
        job_id: str,
        timeout: float | None = None,
    ) -> SubAgentResult | None:
        """Wait for sub-agent to complete."""

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running sub-agent."""

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get sub-agent job status."""

    def get_result(self, job_id: str) -> SubAgentResult | None:
        """Get sub-agent result."""
```

---

## Parsing Module (`parsing/`)

### ParseEvent Types

```python
@dataclass
class TextEvent:
    """Regular text content."""
    text: str

@dataclass
class ToolCallEvent:
    """Tool call detected."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

@dataclass
class SubAgentCallEvent:
    """Sub-agent call detected."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

@dataclass
class CommandEvent:
    """Framework command detected."""
    command: str
    args: str = ""
    raw: str = ""

@dataclass
class OutputEvent:
    """Explicit output block."""
    target: str
    content: str = ""
    raw: str = ""

@dataclass
class BlockStartEvent:
    """Block start marker."""
    block_type: str
    name: str | None = None

@dataclass
class BlockEndEvent:
    """Block end marker."""
    block_type: str
    success: bool = True
    error: str | None = None

# Union type
ParseEvent = (
    TextEvent | ToolCallEvent | SubAgentCallEvent |
    CommandEvent | OutputEvent | BlockStartEvent | BlockEndEvent
)
```

### StreamParser

```python
class StreamParser:
    """Streaming parser for LLM output."""

    def __init__(self, config: ParserConfig | None = None):
        """Initialize parser."""

    def feed(self, chunk: str) -> list[ParseEvent]:
        """Feed a chunk of text, return detected events."""

    def flush(self) -> list[ParseEvent]:
        """Flush remaining buffered content."""
```

### ParserConfig

```python
@dataclass
class ParserConfig:
    emit_block_events: bool = False
    buffer_text: bool = True
    text_buffer_size: int = 1
    known_tools: set[str] = field(default_factory=set)
    known_subagents: set[str] = field(default_factory=set)
    known_commands: set[str] = field(default_factory=set)
    known_outputs: set[str] = field(default_factory=set)
    content_arg_map: dict[str, str] = field(default_factory=dict)
```

### Usage

```python
from kohakuterrarium.parsing import StreamParser, ParserConfig

config = ParserConfig(
    known_tools={"bash", "read", "write"},
    known_outputs={"discord"},
)

parser = StreamParser(config)

# Process streaming chunks
for chunk in llm_stream:
    events = parser.feed(chunk)
    for event in events:
        if isinstance(event, ToolCallEvent):
            # Start tool execution
            pass
        elif isinstance(event, TextEvent):
            # Output text
            pass

# Don't forget to flush
final_events = parser.flush()
```

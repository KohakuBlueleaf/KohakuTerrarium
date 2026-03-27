# Core Module API Reference

API reference for the core modules in `kohakuterrarium.core`.

## Agent (`core/agent.py`)

The top-level orchestrator that wires all components together.

### Agent Class

```python
class Agent:
    """Main agent class that orchestrates all components."""

    @classmethod
    def from_path(cls, config_path: str | Path) -> "Agent":
        """Load agent from configuration folder."""

    async def start(self) -> None:
        """Start all modules (input, output, triggers, etc.)."""

    async def stop(self) -> None:
        """Stop all modules and cleanup."""

    async def run(self) -> None:
        """Main event loop - process inputs and triggers."""

    async def inject_input(self, content: str) -> None:
        """Inject a user input event."""

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""

    @property
    def tools(self) -> list[str]:
        """List of registered tool names."""

    @property
    def subagents(self) -> list[str]:
        """List of registered sub-agent names."""
```

### Usage

```python
from kohakuterrarium.core.agent import Agent

# Load from config folder
agent = Agent.from_path("agents/my_agent")

# Run main loop
await agent.run()

# Or use programmatically
await agent.start()
await agent.inject_input("Hello!")
await agent.stop()
```

---

## Controller (`core/controller.py`)

The LLM conversation loop with event queue management.

### Controller Class

```python
class Controller:
    """LLM conversation controller."""

    def __init__(
        self,
        llm: LLMProvider,
        conversation: Conversation,
        parser: StreamParser,
        config: ControllerConfig | None = None,
    ):
        """Initialize controller."""

    async def push_event(self, event: TriggerEvent) -> None:
        """Push event to the controller's queue."""

    async def run_once(self) -> AsyncIterator[ParseEvent]:
        """
        Run one conversation turn.

        Yields ParseEvents as they are detected in the stream.
        """

    def get_job_result(self, job_id: str) -> JobResult | None:
        """Get result for a completed job."""

    def get_job_status(self, job_id: str) -> JobStatus | None:
        """Get status of a job."""
```

### ControllerConfig

```python
@dataclass
class ControllerConfig:
    """Controller configuration."""
    max_messages: int = 0              # Max messages (0 = unlimited)
    max_context_chars: int = 0         # Max context chars (0 = unlimited)
    ephemeral: bool = False            # Clear after each turn
    include_tools: bool = True         # Include tool list in prompt
    include_hints: bool = True         # Include framework hints
    skill_mode: str = "dynamic"        # "dynamic" or "static"
    known_outputs: set[str] | None = None  # Named output targets
```

### ControllerContext

Context object passed to command handlers:

```python
@dataclass
class ControllerContext:
    """Context for command execution."""
    job_store: JobStore                # Shared job store
    agent_path: Path | None = None     # Agent folder path
    # ... tool/subagent info methods
```

---

## Executor (`core/executor.py`)

Manages async tool execution in the background.

### Executor Class

```python
class Executor:
    """Background tool executor."""

    def __init__(self, job_store: JobStore | None = None):
        """Initialize executor with optional shared job store."""

    def register_tool(self, tool: Tool) -> None:
        """Register a tool for execution."""

    async def start_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        job_id: str | None = None,
    ) -> str:
        """
        Start tool execution (non-blocking).

        Returns job_id immediately.
        """

    async def wait_for_direct_tools(
        self,
        job_ids: list[str],
        timeout: float | None = None,
    ) -> dict[str, JobResult]:
        """Wait for specific tools to complete."""

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get job status."""

    def get_result(self, job_id: str) -> JobResult | None:
        """Get job result (if completed)."""

    def get_running_jobs(self) -> list[JobStatus]:
        """Get all running jobs."""
```

---

## Job System (`core/job.py`)

Job status tracking and result storage.

### JobState Enum

```python
class JobState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"
```

### JobType Enum

```python
class JobType(Enum):
    TOOL = "tool"
    SUBAGENT = "subagent"
    BASH = "bash"
```

### JobStatus

```python
@dataclass
class JobStatus:
    """Status of a running or completed job."""
    job_id: str
    job_type: JobType
    type_name: str              # Tool/subagent name
    state: JobState
    start_time: datetime
    duration: float | None = None
    output_lines: int = 0
    output_bytes: int = 0
    preview: str = ""           # First 200 chars
    error: str | None = None

    @property
    def is_running(self) -> bool:
        """Check if job is still running."""

    @property
    def is_complete(self) -> bool:
        """Check if job is complete (done or error)."""

    def to_context_string(self) -> str:
        """Format for inclusion in controller context."""
```

### JobResult

```python
@dataclass
class JobResult:
    """Complete result of a finished job."""
    job_id: str
    output: str
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if job succeeded."""

    def truncated(self, max_chars: int = 2000) -> str:
        """Get truncated output with note."""

    def get_lines(self, start: int = 0, count: int = 50) -> str:
        """Get specific lines from output."""
```

### JobStore

```python
class JobStore:
    """In-memory storage for job status and results."""

    def register(self, status: JobStatus) -> None:
        """Register a new job."""

    def update_status(
        self,
        job_id: str,
        state: JobState | None = None,
        **kwargs,
    ) -> None:
        """Update job status fields."""

    def store_result(self, result: JobResult) -> None:
        """Store job result."""

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get job status."""

    def get_result(self, job_id: str) -> JobResult | None:
        """Get job result."""

    def get_running_jobs(self) -> list[JobStatus]:
        """Get all running jobs."""

    def cleanup_old(self, max_age_seconds: float = 3600) -> int:
        """Remove old completed jobs."""
```

---

## Events (`core/events.py`)

Unified event model for the entire system.

### TriggerEvent

```python
@dataclass
class TriggerEvent:
    """Universal event type."""
    type: str                              # Event type identifier
    content: str | list[ContentPart] = ""  # Main message (multimodal)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    job_id: str | None = None              # For completions
    prompt_override: str | None = None     # Optional prompt injection
    stackable: bool = True                 # Can batch with others

    def get_text_content(self) -> str:
        """Extract text from content."""

    def is_multimodal(self) -> bool:
        """Check if content is multimodal."""

    def with_context(self, **kwargs) -> "TriggerEvent":
        """Create new event with additional context."""
```

### EventType Constants

```python
class EventType:
    USER_INPUT = "user_input"
    IDLE = "idle"
    TIMER = "timer"
    CONTEXT_UPDATE = "context_update"
    TOOL_COMPLETE = "tool_complete"
    SUBAGENT_OUTPUT = "subagent_output"
    MONITOR = "monitor"
    ERROR = "error"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
```

### Factory Functions

```python
def create_user_input_event(
    content: str,
    source: str = "cli",
    **extra_context,
) -> TriggerEvent:
    """Create a user input event."""

def create_tool_complete_event(
    job_id: str,
    content: str,
    exit_code: int | None = None,
    error: str | None = None,
    **extra_context,
) -> TriggerEvent:
    """Create a tool completion event."""

def create_error_event(
    error_type: str,
    message: str,
    job_id: str | None = None,
    **extra_context,
) -> TriggerEvent:
    """Create an error event."""
```

---

## Conversation (`core/conversation.py`)

Message history management.

### Conversation Class

```python
class Conversation:
    """Manages conversation history."""

    def __init__(self, config: ConversationConfig | None = None):
        """Initialize conversation."""

    def append(
        self,
        role: str,  # "system", "user", "assistant", "tool"
        content: str | list[ContentPart],
        **kwargs,
    ) -> Message:
        """Append a message."""

    def to_messages(self) -> list[dict[str, Any]]:
        """Convert to OpenAI API format."""

    def get_messages(self) -> list[Message]:
        """Get raw Message objects."""

    def get_context_length(self) -> int:
        """Get current context length in chars."""

    def get_image_count(self) -> int:
        """Get total images in conversation."""

    def get_last_message(self) -> Message | None:
        """Get last message."""

    def clear(self, keep_system: bool = True) -> None:
        """Clear conversation history."""

    def to_json(self) -> str:
        """Serialize to JSON."""

    @classmethod
    def from_json(cls, json_str: str) -> "Conversation":
        """Deserialize from JSON."""
```

### ConversationConfig

```python
@dataclass
class ConversationConfig:
    max_messages: int = 0          # 0 = unlimited
    max_context_chars: int = 0     # 0 = unlimited
    keep_system: bool = True       # Keep system messages on truncate
```

---

## Registry (`core/registry.py`)

Module registration system.

### Registry Class

```python
class Registry:
    """Central registry for modules."""

    def register_tool(self, tool: Tool) -> None:
        """Register a tool instance."""

    def get_tool(self, name: str) -> Tool | None:
        """Get tool by name."""

    def get_tool_info(self, name: str) -> ToolInfo | None:
        """Get tool info by name."""

    def list_tools(self) -> list[str]:
        """List all tool names."""

    def register_subagent(self, name: str, config: Any) -> None:
        """Register a sub-agent."""

    def get_subagent(self, name: str) -> Any | None:
        """Get sub-agent by name."""

    def list_subagents(self) -> list[str]:
        """List all sub-agent names."""

    def register_command(self, name: str, handler: Callable) -> None:
        """Register a command handler."""

    def get_command(self, name: str) -> Callable | None:
        """Get command handler."""

    def clear(self) -> None:
        """Clear all registrations."""
```

### Global Registry Functions

```python
def get_registry() -> Registry:
    """Get the global registry instance."""

def register_tool(tool: Tool) -> None:
    """Register to global registry."""

# Decorators
@tool("my_tool")
class MyTool(BaseTool):
    ...

@command("my_command")
async def handle_my_command(...):
    ...
```

---

## Configuration (`core/config.py`)

Configuration loading and parsing.

### AgentConfig

```python
@dataclass
class AgentConfig:
    """Complete agent configuration."""
    name: str
    version: str = "1.0"
    controller: ControllerConfig
    system_prompt_file: str | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    subagents: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[dict[str, Any]] = field(default_factory=list)
    memory: dict[str, Any] | None = None
    startup_trigger: dict[str, Any] | None = None

    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        """Load from YAML/JSON/TOML file."""
```

---

## LLM Provider (`llm/`)

### LLMProvider Protocol

```python
class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = True,
        **kwargs,
    ) -> AsyncIterator[str] | ChatResponse:
        """Send chat completion request."""
```

### OpenAIProvider

```python
class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = OPENAI_BASE_URL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize provider."""

    async def close(self) -> None:
        """Close HTTP client."""
```

### Usage

```python
from kohakuterrarium.llm.openai import OpenAIProvider

provider = OpenAIProvider(
    api_key="sk-...",
    model="gpt-4o-mini",
)

# Streaming
async for chunk in provider.chat(messages, stream=True):
    print(chunk, end="")

# Non-streaming
response = await provider.chat(messages, stream=False)
print(response.content)

await provider.close()
```

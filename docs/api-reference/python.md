# Python API Reference

Comprehensive reference for all public Python APIs. For architectural context, see [Architecture](../architecture/README.md).

## Core: Agent (`core/agent.py`)

```python
class Agent:
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
    def is_running(self) -> bool
    @property
    def tools(self) -> list[str]
    @property
    def subagents(self) -> list[str]
```

**Hot-plug methods:**

```python
    async def add_trigger(self, trigger: TriggerModule) -> None:
        """Add and start a trigger on a running agent."""

    async def remove_trigger(self, trigger: TriggerModule) -> None:
        """Stop and remove a trigger from a running agent."""

    def update_system_prompt(self, content: str, replace: bool = False) -> None:
        """Append to (or replace) the system prompt. Takes effect on next LLM call."""

    def get_system_prompt(self) -> str:
        """Read the current system prompt text."""
```

---

## Core: Controller (`core/controller.py`)

```python
class Controller:
    def __init__(
        self,
        llm: LLMProvider,
        conversation: Conversation,
        parser: StreamParser,
        config: ControllerConfig | None = None,
    ): ...

    async def push_event(self, event: TriggerEvent) -> None:
        """Push event to the controller's queue."""

    async def run_once(self) -> AsyncIterator[ParseEvent]:
        """Run one conversation turn. Yields ParseEvents."""

    def get_job_result(self, job_id: str) -> JobResult | None
    def get_job_status(self, job_id: str) -> JobStatus | None
```

### ControllerConfig

```python
@dataclass
class ControllerConfig:
    max_messages: int = 0              # 0 = unlimited
    max_context_chars: int = 0         # 0 = unlimited
    ephemeral: bool = False            # Clear after each turn
    include_tools: bool = True
    include_hints: bool = True
    skill_mode: str = "dynamic"        # "dynamic" or "static"
    known_outputs: set[str] | None = None
```

---

## Core: Executor (`core/executor.py`)

```python
class Executor:
    def __init__(self, job_store: JobStore | None = None): ...

    def register_tool(self, tool: Tool) -> None
    async def start_tool(self, tool_name: str, args: dict, job_id: str | None = None) -> str:
        """Start tool execution (non-blocking). Returns job_id."""

    async def wait_for_direct_tools(self, job_ids: list[str], timeout: float | None = None) -> dict[str, JobResult]
    def get_status(self, job_id: str) -> JobStatus | None
    def get_result(self, job_id: str) -> JobResult | None
    def get_running_jobs(self) -> list[JobStatus]
```

---

## Core: Events (`core/events.py`)

```python
@dataclass
class TriggerEvent:
    type: str
    content: str | list[ContentPart] = ""
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    job_id: str | None = None
    prompt_override: str | None = None
    stackable: bool = True

    def get_text_content(self) -> str
    def is_multimodal(self) -> bool
    def with_context(self, **kwargs) -> "TriggerEvent"

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

**Factory functions:**

```python
def create_user_input_event(content: str, source: str = "cli", **extra_context) -> TriggerEvent
def create_tool_complete_event(job_id: str, content: str, exit_code: int | None = None, error: str | None = None, **extra_context) -> TriggerEvent
def create_error_event(error_type: str, message: str, job_id: str | None = None, **extra_context) -> TriggerEvent
```

---

## Core: Job System (`core/job.py`)

```python
class JobState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

class JobType(Enum):
    TOOL = "tool"
    SUBAGENT = "subagent"
    BASH = "bash"

@dataclass
class JobStatus:
    job_id: str
    job_type: JobType
    type_name: str
    state: JobState
    start_time: datetime
    duration: float | None = None
    output_lines: int = 0
    output_bytes: int = 0
    preview: str = ""
    error: str | None = None

    @property
    def is_running(self) -> bool
    @property
    def is_complete(self) -> bool
    def to_context_string(self) -> str

@dataclass
class JobResult:
    job_id: str
    output: str
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool
    def truncated(self, max_chars: int = 2000) -> str
    def get_lines(self, start: int = 0, count: int = 50) -> str

class JobStore:
    def register(self, status: JobStatus) -> None
    def update_status(self, job_id: str, state: JobState | None = None, **kwargs) -> None
    def store_result(self, result: JobResult) -> None
    def get_status(self, job_id: str) -> JobStatus | None
    def get_result(self, job_id: str) -> JobResult | None
    def get_running_jobs(self) -> list[JobStatus]
    def cleanup_old(self, max_age_seconds: float = 3600) -> int
```

---

## Core: Conversation (`core/conversation.py`)

```python
class Conversation:
    def __init__(self, config: ConversationConfig | None = None): ...

    def append(self, role: str, content: str | list[ContentPart], **kwargs) -> Message
    def to_messages(self) -> list[dict[str, Any]]
    def get_messages(self) -> list[Message]
    def get_context_length(self) -> int
    def get_last_message(self) -> Message | None
    def clear(self, keep_system: bool = True) -> None
    def to_json(self) -> str
    @classmethod
    def from_json(cls, json_str: str) -> "Conversation"

@dataclass
class ConversationConfig:
    max_messages: int = 0
    max_context_chars: int = 0
    keep_system: bool = True
```

---

## Core: Session (`core/session.py`)

```python
@dataclass
class Session:
    key: str
    channels: ChannelRegistry
    scratchpad: Scratchpad
    tui: Any | None = None
    extra: dict[str, Any]

def get_session(key: str | None = None) -> Session
def set_session(session: Session, key: str | None = None) -> None
def remove_session(key: str | None = None) -> None
def list_sessions() -> list[str]
```

---

## Core: Configuration (`core/config.py`)

```python
@dataclass
class AgentConfig:
    name: str
    version: str = "1.0"
    session_key: str | None = None
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
    def from_file(cls, path: Path) -> "AgentConfig"
```

---

## Core: Registry (`core/registry.py`)

```python
class Registry:
    def register_tool(self, tool: Tool) -> None
    def get_tool(self, name: str) -> Tool | None
    def get_tool_info(self, name: str) -> ToolInfo | None
    def list_tools(self) -> list[str]
    def register_subagent(self, name: str, config: Any) -> None
    def get_subagent(self, name: str) -> Any | None
    def list_subagents(self) -> list[str]
    def register_command(self, name: str, handler: Callable) -> None
    def get_command(self, name: str) -> Callable | None
    def clear(self) -> None

# Global functions
def get_registry() -> Registry
def register_tool(tool: Tool) -> None

# Decorators
@tool("my_tool")
@command("my_command")
```

---

## Modules: Input (`modules/input/base.py`)

```python
class InputModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def get_input(self) -> TriggerEvent | None

class BaseInputModule(ABC):
    @property
    def is_running(self) -> bool
    async def start(self) -> None
    async def stop(self) -> None
    async def _on_start(self) -> None        # Override in subclass
    async def _on_stop(self) -> None         # Override in subclass
    @abstractmethod
    async def get_input(self) -> TriggerEvent | None
```

---

## Modules: Output (`modules/output/`)

```python
class OutputModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def write(self, content: str) -> None
    async def write_stream(self, chunk: str) -> None
    async def flush(self) -> None
    async def on_processing_start(self) -> None

class BaseOutputModule(ABC):
    @property
    def is_running(self) -> bool
    @abstractmethod
    async def write(self, content: str) -> None
    async def write_stream(self, chunk: str) -> None  # Default calls write()
    async def flush(self) -> None                      # Default no-op

class OutputRouter:
    def __init__(self, default_output, named_outputs=None, suppress_tool_blocks=True, suppress_subagent_blocks=True): ...
    async def route(self, event: ParseEvent) -> None
    async def flush(self) -> None
    def get_output_feedback(self) -> str | None
    def get_output_targets(self) -> list[str]
    def reset(self) -> None
    def clear_all(self) -> None
```

---

## Modules: Tool (`modules/tool/base.py`)

```python
class Tool(Protocol):
    @property
    def tool_name(self) -> str
    @property
    def description(self) -> str
    @property
    def execution_mode(self) -> ExecutionMode  # DIRECT, BACKGROUND, STATEFUL
    async def execute(self, args: dict[str, Any]) -> ToolResult

class ExecutionMode(Enum):
    DIRECT = "direct"
    BACKGROUND = "background"
    STATEFUL = "stateful"

@dataclass
class ToolResult:
    output: str | list[ContentPart] = ""
    exit_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool
    def get_text_output(self) -> str
    def has_images(self) -> bool

class BaseTool:
    @property
    @abstractmethod
    def tool_name(self) -> str
    @property
    @abstractmethod
    def description(self) -> str
    @property
    def execution_mode(self) -> ExecutionMode  # Default: BACKGROUND
    async def execute(self, args: dict) -> ToolResult  # With error handling
    @abstractmethod
    async def _execute(self, args: dict) -> ToolResult
    def get_full_documentation(self) -> str

@dataclass
class ToolContext:
    agent_name: str
    session: Session
    working_dir: Path
    memory_path: Path | None = None

    @property
    def channels(self) -> ChannelRegistry
    @property
    def scratchpad(self) -> Scratchpad

@dataclass
class ToolConfig:
    timeout: float = 60.0
    max_output: int = 0
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
```

---

## Modules: Trigger (`modules/trigger/base.py`)

```python
class TriggerModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def wait_for_trigger(self) -> TriggerEvent | None
    def set_context(self, context: dict[str, Any]) -> None

class BaseTrigger(ABC):
    def __init__(self, prompt: str | None = None, **options): ...
    @property
    def is_running(self) -> bool
    def set_context(self, context: dict[str, Any]) -> None
    def _on_context_update(self, context: dict[str, Any]) -> None  # Override
    @abstractmethod
    async def wait_for_trigger(self) -> TriggerEvent | None
    def _create_event(self, event_type: str, content: str | None = None, context: dict | None = None) -> TriggerEvent
```

---

## Modules: Sub-Agent (`modules/subagent/`)

```python
@dataclass
class SubAgentConfig:
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

    def load_prompt(self, agent_path: Path | None = None) -> str
    @classmethod
    def from_dict(cls, data: dict) -> "SubAgentConfig"

class OutputTarget(Enum):
    CONTROLLER = "controller"
    EXTERNAL = "external"

class ContextUpdateMode(Enum):
    INTERRUPT_RESTART = "interrupt_restart"
    QUEUE_APPEND = "queue_append"
    FLUSH_REPLACE = "flush_replace"

@dataclass
class SubAgentResult:
    output: str = ""
    success: bool = True
    error: str | None = None
    turns: int = 0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

class SubAgentManager:
    def __init__(self, parent_registry, llm, job_store=None, agent_path=None): ...
    def register(self, config: SubAgentConfig) -> None
    def get_config(self, name: str) -> SubAgentConfig | None
    def list_subagents(self) -> list[str]
    async def spawn(self, name: str, task: str, job_id: str | None = None) -> str
    async def wait_for(self, job_id: str, timeout: float | None = None) -> SubAgentResult | None
    async def cancel(self, job_id: str) -> bool
    def get_status(self, job_id: str) -> JobStatus | None
    def get_result(self, job_id: str) -> SubAgentResult | None
```

---

## Parsing (`parsing/`)

```python
@dataclass
class TextEvent:
    text: str

@dataclass
class ToolCallEvent:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

@dataclass
class SubAgentCallEvent:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

@dataclass
class CommandEvent:
    command: str
    args: str = ""

@dataclass
class OutputEvent:
    target: str
    content: str = ""

@dataclass
class BlockStartEvent:
    block_type: str
    name: str | None = None

@dataclass
class BlockEndEvent:
    block_type: str
    success: bool = True
    error: str | None = None

ParseEvent = (
    TextEvent | ToolCallEvent | SubAgentCallEvent |
    CommandEvent | OutputEvent | BlockStartEvent | BlockEndEvent
)

class StreamParser:
    def __init__(self, config: ParserConfig | None = None): ...
    def feed(self, chunk: str) -> list[ParseEvent]
    def flush(self) -> list[ParseEvent]

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
    tool_format: ToolCallFormat = field(default_factory=lambda: BRACKET_FORMAT)
```

---

## LLM Provider (`llm/`)

```python
class LLMProvider(Protocol):
    async def chat(self, messages: list[dict], stream: bool = True, **kwargs) -> AsyncIterator[str] | ChatResponse

class OpenAIProvider(BaseLLMProvider):
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
    ): ...

    async def close(self) -> None
```

---

## Builtins

### Built-in Tools

| Name | Description | Execution Mode |
|------|-------------|---------------|
| `bash` | Execute shell commands | DIRECT |
| `python` | Execute Python code | DIRECT |
| `read` | Read file contents | DIRECT |
| `write` | Create/overwrite files | DIRECT |
| `edit` | Search-replace in files | DIRECT |
| `glob` | Find files by pattern | DIRECT |
| `grep` | Regex search in files | DIRECT |
| `tree` | Directory structure | DIRECT |
| `think` | Extended reasoning step | DIRECT |
| `scratchpad` | Session key-value memory | DIRECT |
| `send_message` | Send to named channel | DIRECT |
| `wait_channel` | Wait for channel message | BACKGROUND |
| `http` | Make HTTP requests | DIRECT |
| `ask_user` | Prompt user for input | DIRECT |
| `json_read` | Query JSON files | DIRECT |
| `json_write` | Modify JSON files | DIRECT |

```python
from kohakuterrarium.builtins.tools import get_builtin_tool, BUILTIN_TOOLS
BashTool = get_builtin_tool("bash")
```

### Built-in Sub-Agents

| Name | Tools | Output |
|------|-------|--------|
| `explore` | glob, grep, read | Controller |
| `plan` | glob, grep, read | Controller |
| `worker` | read, write, edit, bash, glob, grep | Controller |
| `critic` | read, glob, grep | Controller |
| `summarize` | (none) | Controller |
| `research` | http, read, glob, grep | Controller |
| `coordinator` | send_message, wait_channel | Controller |
| `memory_read` | read, glob | Controller |
| `memory_write` | write, read | Controller |
| `response` | (none) | External |

```python
from kohakuterrarium.builtins.subagents import get_builtin_subagent_config, BUILTIN_SUBAGENTS
```

### Built-in Inputs

- `cli` - command-line prompt (`prompt` config)
- `tui` - terminal UI via shared session (`prompt`, `session_key` config)
- `none` - blocks forever, for trigger-only agents

### Built-in Outputs

- `stdout` - standard output with streaming support
- `tui` - terminal UI via shared session (`session_key` config)

### Framework Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `info` | `[/info]bash[info/]` | Get full tool/sub-agent documentation |
| `jobs` | `[/jobs][jobs/]` | List running background jobs |
| `wait` | `[/wait]job_id[wait/]` | Wait for a background job to complete |

---

## Terrarium API (`terrarium/api.py`)

```python
class TerrariumAPI:
    # Channel operations
    async def list_channels(self) -> list[dict[str, str]]
    async def channel_info(self, name: str) -> dict[str, Any] | None
    async def send_to_channel(self, name: str, content: str, sender: str = "human", metadata: dict | None = None) -> str

    # Creature operations
    async def list_creatures(self) -> list[dict[str, Any]]
    async def get_creature_status(self, name: str) -> dict[str, Any] | None
    async def stop_creature(self, name: str) -> bool
    async def start_creature(self, name: str) -> bool

    # Terrarium operations
    def get_status(self) -> dict[str, Any]
    @property
    def is_running(self) -> bool
```

### Terrarium Runtime Hot-Plug

```python
class TerrariumRuntime:
    async def add_creature(self, config: CreatureConfig) -> None
    async def remove_creature(self, name: str) -> bool
    async def add_channel(self, name: str, type: str, description: str) -> None
    async def wire_channel(self, creature: str, channel: str, direction: str) -> None
```

---

## Observer (`terrarium/observer.py`)

```python
class ChannelObserver:
    def __init__(self, session: Session, max_history: int = 1000): ...
    async def observe(self, channel_name: str) -> None
    def on_message(self, callback: Callable) -> None
    def record(self, channel_name: str, msg: ChannelMessage) -> None
    def get_messages(self, channel: str | None = None, last_n: int = 20) -> list[ObservedMessage]
    async def stop(self) -> None

@dataclass
class ObservedMessage:
    channel: str
    sender: str
    content: str
    message_id: str
    timestamp: datetime
    metadata: dict[str, Any]
```

---

## Output Log (`terrarium/output_log.py`)

```python
class OutputLogCapture:
    def get_entries(self, last_n: int = 20, entry_type: str | None = None) -> list[LogEntry]
    def get_text(self, last_n: int = 20) -> str
    @property
    def entry_count(self) -> int
    def clear(self) -> None

@dataclass
class LogEntry:
    timestamp: datetime
    content: str
    entry_type: str = "text"    # "text", "stream_flush", "activity"
    metadata: dict[str, Any] = field(default_factory=dict)

    def preview(self, max_len: int = 80) -> str
```

---

## Testing (`testing/`)

```python
class ScriptedLLM:
    """Deterministic LLM mock implementing LLMProvider."""
    def __init__(self, scripts: list[str] | list[ScriptEntry]): ...
    call_count: int
    last_user_message: str
    call_log: list

class OutputRecorder(BaseOutputModule):
    """Captures all output for assertions."""
    all_text: str
    stream_text: str
    writes: list[str]
    activities: list
    def assert_text_contains(self, text: str) -> None
    def assert_activity_count(self, activity_type: str, count: int) -> None

class EventRecorder:
    """Records events with timing for ordering assertions."""
    count: int
    def types_in_order(self) -> list[str]
    def assert_order(self, *types: str) -> None

class TestAgentBuilder:
    """Builder for test harness with real Controller + Executor."""
    def with_llm_script(self, scripts) -> Self
    def with_builtin_tools(self, tools: list[str]) -> Self
    def with_system_prompt(self, prompt: str) -> Self
    def with_session(self, key: str) -> Self
    def with_named_output(self, name: str, output: OutputModule) -> Self
    def build(self) -> TestEnvironment
```

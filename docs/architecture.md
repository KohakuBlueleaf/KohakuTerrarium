# Architecture Overview

This document explains the core architecture of KohakuTerrarium, including the main components, data flow, and design decisions.

## Design Principles

### 1. Controller as Orchestrator

The controller's role is to **dispatch tasks, not do heavy work itself**.

- Controller outputs should be SHORT: tool calls, sub-agent dispatches, status updates
- Long outputs (user-facing content) should come from **output sub-agents**
- This keeps controller lightweight, fast, and focused on decision-making

### 2. Non-Blocking Tool Execution

Tools execute in the background while the LLM continues streaming:

```
LLM streams → Tool detected → asyncio.create_task() → Continue streaming
                                     ↓ (parallel)
                            Tool execution happens
                                     ↓
                        Results batched as feedback event
```

### 3. Unified Event Model

Everything flows through `TriggerEvent`:

```python
@dataclass
class TriggerEvent:
    type: str                          # "user_input", "tool_complete", "idle", etc.
    content: str | list[ContentPart]   # Main message (supports multimodal)
    context: dict[str, Any]            # Metadata
    timestamp: datetime
    job_id: str | None                 # For tool/subagent completions
    prompt_override: str | None        # Optional prompt injection
    stackable: bool                    # Can batch with simultaneous events
```

Common event types (from `EventType`):
- `USER_INPUT` - User provided input
- `TOOL_COMPLETE` - Tool finished execution
- `SUBAGENT_OUTPUT` - Sub-agent produced output
- `IDLE` - Idle timeout trigger
- `TIMER` - Timer-based trigger
- `ERROR` - Error occurred
- `STARTUP` / `SHUTDOWN` - Lifecycle events

## Core Components

### Agent (`core/agent.py`)

The top-level orchestrator that wires all components together.

**Responsibilities:**
- Load configuration from folder
- Initialize LLM provider, controller, executor, registry
- Load tools, sub-agents, triggers from config
- Build system prompt via aggregation
- Process events through controller
- Track job status and completion
- Route output to appropriate modules

**Lifecycle:**
```python
agent = Agent.from_path("agents/my_agent")  # Load config
await agent.start()                          # Initialize modules
await agent.run()                            # Main event loop
await agent.stop()                           # Cleanup
```

### Controller (`core/controller.py`)

The LLM conversation loop with event queue management.

**Responsibilities:**
- Maintain conversation history with context limits
- Stream LLM output and parse events
- Execute framework commands (read, info, jobs, wait) inline
- Push events via async queue
- Manage job tracking and status

**Key Method: `run_once()`**
```
1. Wait for event from queue
2. Add event content to conversation
3. Stream LLM response
4. Parse response for tool calls, commands, output blocks
5. Yield ParseEvents to caller
```

**Command Handling:**
Commands like `[/info]bash[info/]` are handled inline during streaming:
```
CommandEvent detected → _handle_command() → result converted to TextEvent → yielded
```

### Executor (`core/executor.py`)

Manages async tool execution in the background.

**Execution Flow:**
1. Tool call detected during LLM streaming
2. `start_tool()` creates `asyncio.Task` immediately (non-blocking)
3. LLM continues streaming
4. After streaming ends, `wait_for_direct_tools()` gathers results
5. Results batched into feedback event

**Job Tracking:**
- Each tool execution gets a unique `job_id`
- Status stored in shared `JobStore`
- States: `PENDING` → `RUNNING` → `DONE`/`ERROR`/`CANCELLED`

### JobStore (`core/job.py`)

In-memory storage for job status and results.

```python
@dataclass
class JobStatus:
    job_id: str
    job_type: JobType          # TOOL, SUBAGENT, BASH
    type_name: str             # "bash", "explore", etc.
    state: JobState            # PENDING, RUNNING, DONE, ERROR, CANCELLED
    start_time: datetime
    duration: float | None
    output_lines: int
    output_bytes: int
    preview: str               # First 200 chars
    error: str | None

@dataclass
class JobResult:
    job_id: str
    output: str
    exit_code: int | None
    error: str | None
    metadata: dict
```

### Conversation (`core/conversation.py`)

Manages message history with OpenAI-compatible format.

**Features:**
- Supports multimodal messages (text + images)
- Automatic truncation policies:
  - `max_messages`: Maximum message count
  - `max_context_chars`: Maximum context length
  - `keep_system`: Always keep system messages
- JSON serialization/deserialization
- Metadata tracking (creation time, message count, total chars)

### Registry (`core/registry.py`)

Central registration for tools, sub-agents, and commands.

```python
class Registry:
    def register_tool(self, tool: Tool) -> None
    def get_tool(self, name: str) -> Tool | None
    def list_tools(self) -> list[str]

    def register_subagent(self, name: str, config: Any) -> None
    def get_subagent(self, name: str) -> Any | None
    def list_subagents(self) -> list[str]

    def register_command(self, name: str, handler: Callable) -> None
    def get_command(self, name: str) -> Callable | None
```

## Module System

### Input Modules (`modules/input/base.py`)

Protocol for external input sources:

```python
class InputModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def get_input(self) -> TriggerEvent | None
```

Examples: CLI input, Discord messages, Whisper ASR

### Trigger Modules (`modules/trigger/base.py`)

Protocol for autonomous event generation:

```python
class TriggerModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def wait_for_trigger(self) -> TriggerEvent | None
    def set_context(self, context: dict[str, Any]) -> None
```

Examples: Idle trigger, timer trigger, condition trigger

### Tool Modules (`modules/tool/base.py`)

Protocol for executable tools:

```python
class Tool(Protocol):
    @property
    def tool_name(self) -> str
    @property
    def description(self) -> str
    @property
    def execution_mode(self) -> ExecutionMode
    async def execute(self, args: dict[str, Any]) -> ToolResult

class ExecutionMode(Enum):
    DIRECT = "direct"          # Complete before returning
    BACKGROUND = "background"  # Run in background
    STATEFUL = "stateful"      # Multi-turn interaction
```

### Output Modules (`modules/output/base.py`)

Protocol for output delivery:

```python
class OutputModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def write(self, content: str) -> None
    async def write_stream(self, chunk: str) -> None
    async def flush(self) -> None
    async def on_processing_start(self) -> None
```

### Output Router (`modules/output/router.py`)

Routes parse events to appropriate outputs using a state machine:

**States:**
- `NORMAL` - Regular text output (stdout)
- `TOOL_BLOCK` - Inside tool call (suppress output)
- `SUBAGENT_BLOCK` - Inside sub-agent call (suppress output)
- `COMMAND_BLOCK` - Inside command
- `OUTPUT_BLOCK` - Inside explicit output block

**Routing Logic:**
```
TextEvent → default_output (stdout)
OutputEvent(target="discord") → named_outputs["discord"]
ToolCallEvent → suppress text, queue for handling
```

### Sub-Agent System (`modules/subagent/`)

Sub-agents are nested agents with their own controller and limited tool access.

**SubAgentConfig:**
```python
@dataclass
class SubAgentConfig:
    name: str
    description: str
    tools: list[str]           # Allowed tool names
    system_prompt: str
    can_modify: bool = False   # Allow write/edit tools
    stateless: bool = True
    interactive: bool = False  # Long-lived with context updates
    output_to: OutputTarget    # CONTROLLER or EXTERNAL
    max_turns: int = 10
    timeout: float = 300.0
```

**Output Targets:**
- `CONTROLLER` (default): Results return to parent controller
- `EXTERNAL`: Stream directly to named output module

**SubAgentManager:**
- Registers and spawns sub-agents
- Shares `JobStore` with executor (so `wait` command works)
- Tracks running sub-agents
- Handles interactive sub-agent lifecycle

## Parsing System

### StreamParser (`parsing/state_machine.py`)

Stateful parser for streaming LLM output using a character-by-character state machine.

**Format:**
```
[/function_name]
@@arg=value
content here
[function_name/]
```

**Parse Events:**
- `TextEvent` - Regular text content
- `ToolCallEvent` - Tool call detected
- `SubAgentCallEvent` - Sub-agent call detected
- `CommandEvent` - Framework command detected
- `OutputEvent` - Explicit output block
- `BlockStartEvent` / `BlockEndEvent` - Block boundaries

**ParserConfig:**
```python
@dataclass
class ParserConfig:
    known_tools: set[str]      # Tool names to recognize
    known_subagents: set[str]  # Sub-agent names to recognize
    known_commands: set[str]   # Command names (info, wait, jobs)
    known_outputs: set[str]    # Output target names (discord, tts)
    content_arg_map: dict      # Maps tool name to content argument
```

## Prompt System

### Aggregator (`prompt/aggregator.py`)

Builds complete system prompts from components.

**Skill Modes:**
1. **Dynamic** (default): Model uses `[/info]tool_name[info/]` to read docs on demand
2. **Static**: All tool docs included in system prompt upfront

**What Gets Aggregated:**
1. Base prompt from `system.md` (agent personality/guidelines)
2. Tool list (name + one-line description) - auto-generated
3. Framework hints (tool call syntax, commands, execution model)
4. Output model hints (if named outputs configured)

**Never Put in system.md:**
- Tool list (auto-generated)
- Tool call syntax (in framework hints)
- Full tool documentation (loaded via `[/info]`)

## Agent Process Loop

The main loop in `Agent._process_event_with_controller()` has 6 phases:

```
Phase 1: Setup
    - Reset router state
    - Initialize job tracking lists

Phase 2: Run LLM
    - Stream LLM output via controller.run_once()
    - For each ParseEvent:
        - ToolCallEvent → start tool immediately (asyncio.create_task)
        - SubAgentCallEvent → spawn sub-agent (always background)
        - TextEvent/OutputEvent → route to output_router

Phase 3: Flush Output
    - Flush output router to ensure all content delivered

Phase 4: Collect Feedback
    - Output feedback (what was sent to named outputs)
    - Direct tool results (wait for completion with asyncio.gather)
    - Background job/sub-agent status (RUNNING or completed)

Phase 5: Loop Decision
    - Exit if: no new jobs AND no pending jobs AND no feedback
    - Continue if any jobs still running or feedback to report

Phase 6: Push Feedback
    - Combine all feedback into single event
    - Push to controller for next LLM turn
```

## Data Flow Diagram

```
                    ┌─────────────────┐
                    │   Input Module  │
                    │  (CLI, Discord) │
                    └────────┬────────┘
                             │ TriggerEvent
                             ▼
    ┌───────────────────────────────────────────────────┐
    │                      Agent                        │
    │  ┌─────────────────────────────────────────────┐  │
    │  │               Controller                    │  │
    │  │  ┌─────────────┐    ┌─────────────────┐    │  │
    │  │  │ Conversation │←──│   LLM Provider  │    │  │
    │  │  └─────────────┘    └────────┬────────┘    │  │
    │  │                              │ Stream      │  │
    │  │                              ▼             │  │
    │  │                     ┌──────────────┐       │  │
    │  │                     │ StreamParser │       │  │
    │  │                     └──────┬───────┘       │  │
    │  └──────────────────────────│─────────────────┘  │
    │                             │ ParseEvents        │
    │      ┌──────────────────────┼───────────────┐    │
    │      │                      │               │    │
    │      ▼                      ▼               ▼    │
    │ ┌──────────┐         ┌───────────┐   ┌─────────┐│
    │ │ Executor │         │ SubAgent  │   │ Output  ││
    │ │ (tools)  │         │ Manager   │   │ Router  ││
    │ └────┬─────┘         └─────┬─────┘   └────┬────┘│
    │      │                     │               │     │
    │      │ JobResult           │ SubAgent      │     │
    │      │                     │ Result        │     │
    │      └──────────┬──────────┘               │     │
    │                 │                          │     │
    │                 ▼                          ▼     │
    │          ┌───────────┐              ┌──────────┐│
    │          │ JobStore  │              │ Named    ││
    │          │ (shared)  │              │ Outputs  ││
    │          └───────────┘              └──────────┘│
    └─────────────────────────────────────────────────┘
```

## File Organization

```
src/kohakuterrarium/
├── core/                    # Core abstractions and runtime
│   ├── agent.py             # Agent orchestrator
│   ├── controller.py        # LLM conversation loop
│   ├── conversation.py      # Message history management
│   ├── executor.py          # Background tool execution
│   ├── job.py               # Job status tracking
│   ├── events.py            # TriggerEvent model
│   ├── config.py            # Configuration loading
│   ├── registry.py          # Module registration
│   └── loader.py            # Dynamic module loading
│
├── modules/                 # Plugin APIs
│   ├── input/base.py        # InputModule protocol
│   ├── output/              # OutputModule + Router
│   ├── tool/base.py         # Tool protocol + BaseTool
│   ├── trigger/base.py      # TriggerModule protocol
│   └── subagent/            # SubAgent system
│
├── parsing/                 # Stream parsing
│   ├── state_machine.py     # StreamParser
│   ├── events.py            # ParseEvent types
│   └── patterns.py          # Parser patterns
│
├── prompt/                  # Prompt system
│   ├── aggregator.py        # System prompt building
│   ├── loader.py            # Prompt file loading
│   ├── template.py          # Jinja2 rendering
│   └── plugins.py           # Extensible plugins
│
├── builtins/                # Built-in implementations
│   ├── tools/               # bash, read, write, etc.
│   ├── inputs/              # cli, whisper
│   ├── outputs/             # stdout, tts
│   └── subagents/           # explore, plan, memory
│
├── llm/                     # LLM integration
│   ├── base.py              # LLMProvider protocol
│   ├── openai.py            # OpenAI-compatible provider
│   └── message.py           # Message formatting
│
└── utils/                   # Utilities
    ├── logging.py           # Structured logging
    └── async_utils.py       # Async helpers
```

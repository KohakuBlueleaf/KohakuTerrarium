# Framework Internals

This document covers the internal design of the single-agent framework. For the concepts behind these components, see [Creatures and Agents](../concept/creature.md).

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

**Key method - `run_once()`:**
1. Wait for event from queue
2. Add event content to conversation
3. Stream LLM response
4. Parse response for tool calls, commands, output blocks
5. Yield ParseEvents to caller

**Command handling:**
Commands like `[/info]bash[info/]` are handled inline during streaming - the result is converted to a TextEvent and yielded.

### Executor (`core/executor.py`)

Manages async tool execution in the background.

**Execution flow:**
1. Tool call detected during LLM streaming
2. `start_tool()` creates `asyncio.Task` immediately (non-blocking)
3. LLM continues streaming
4. After streaming ends, `wait_for_direct_tools()` gathers results
5. Results batched into feedback event

**Job tracking:**
- Each tool execution gets a unique `job_id`
- Status stored in shared `JobStore`
- States: `PENDING` -> `RUNNING` -> `DONE`/`ERROR`/`CANCELLED`

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
- Automatic truncation policies: `max_messages`, `max_context_chars`, `keep_system`
- JSON serialization/deserialization
- Metadata tracking (creation time, message count, total chars)

### Session Registry (`core/session.py`)

Keyed shared state for session-scoped objects. A `Session` holds channels, scratchpad, TUI state, and user-provided extras for one agent (or a group of cooperating agents).

```python
@dataclass
class Session:
    key: str
    channels: ChannelRegistry
    scratchpad: Scratchpad
    tui: Any | None = None
    extra: dict[str, Any]
```

Agents with the same `session_key` share the same Session instance. See [Environment-Session](../concept/environment.md) for the full isolation model.

### Registry (`core/registry.py`)

Central registration for tools, sub-agents, and commands. Supports both programmatic registration and decorator-based registration (`@tool("name")`, `@command("name")`).

## Module System

All modules follow a protocol-based design with base class implementations.

### Input Modules (`modules/input/base.py`)

```python
class InputModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def get_input(self) -> TriggerEvent | None
```

Built-in types: `cli`, `tui`, `whisper`, `none`. Custom modules implement the same protocol.

### Trigger Modules (`modules/trigger/base.py`)

```python
class TriggerModule(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def wait_for_trigger(self) -> TriggerEvent | None
    def set_context(self, context: dict[str, Any]) -> None
```

### Tool Modules (`modules/tool/base.py`)

```python
class Tool(Protocol):
    @property
    def tool_name(self) -> str
    @property
    def description(self) -> str
    @property
    def execution_mode(self) -> ExecutionMode  # DIRECT, BACKGROUND, STATEFUL
    async def execute(self, args: dict[str, Any]) -> ToolResult
```

Tools with `needs_context = True` receive a `ToolContext` with agent name, session, working directory, and memory path.

### Output Modules (`modules/output/base.py`)

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

Routes parse events using a state machine:

```
State: NORMAL
  TextEvent           -> write_stream() to default output
  BlockStartEvent     -> transition to TOOL_BLOCK / SUBAGENT_BLOCK / OUTPUT_BLOCK
  OutputEvent         -> route to named output module

State: TOOL_BLOCK
  TextEvent           -> SUPPRESSED
  BlockEndEvent       -> transition to NORMAL

State: OUTPUT_BLOCK
  TextEvent           -> SUPPRESSED (content comes via OutputEvent)
  BlockEndEvent       -> transition to NORMAL
```

Activity notifications (`on_activity()`) are separate from text output - they are used for tool_start, tool_done, tool_error, etc.

### Sub-Agent System (`modules/subagent/`)

Sub-agents are always background jobs. The `SubAgentManager` registers and spawns sub-agents, sharing the `JobStore` with the executor. See [Creatures - Sub-Agents](../concept/creature.md#sub-agents) for the conceptual overview.

## Parsing System

### StreamParser (`parsing/state_machine.py`)

Stateful parser for streaming LLM output using a character-by-character state machine.

**Parse events:**
- `TextEvent` - regular text content
- `ToolCallEvent` - tool call detected
- `SubAgentCallEvent` - sub-agent call detected
- `CommandEvent` - framework command detected
- `OutputEvent` - explicit output block
- `BlockStartEvent` / `BlockEndEvent` - block boundaries

The parser uses `ToolCallFormat` to support multiple tool call syntaxes. See [Tool Formats](../concept/tool-formats.md).

## Prompt System

### Aggregator (`prompt/aggregator.py`)

Builds complete system prompts from components:

1. **Base prompt** from `system.md` (agent personality/guidelines)
2. **Tool list** (name + one-line description) - auto-generated from registry
3. **Framework hints** (tool call syntax, commands, execution model)
4. **Output model hints** (if named outputs configured)

**Skill modes:**
- **Dynamic** (default): Model uses `[/info]tool_name[info/]` to read docs on demand
- **Static**: All tool docs included in system prompt upfront

## Agent Process Loop

The full event processing loop in `agent_handlers.py` has six phases:

```
Phase 1: Reset router state for new iteration
Phase 2: Run controller.run_once()
         +-- ToolCallEvent     -> start_tool_async() (direct or background)
         +-- SubAgentCallEvent -> start_subagent_async() (always background)
         +-- CommandResultEvent-> on_activity()
         +-- Other             -> output_router.route()
Phase 3: Termination check (max_turns, keywords, duration)
Phase 4: Flush output, update job tracking
Phase 5: Collect feedback
         +-- Output feedback (what was sent to named outputs)
         +-- Direct tool results (waited for)
         +-- Background job status (RUNNING or DONE)
Phase 6: Push feedback to controller -> loop back to Phase 1

Exit condition: no new jobs AND no pending jobs AND no feedback
```

## File Organization

```
src/kohakuterrarium/
+-- core/                    # Core abstractions and runtime
|   +-- agent.py             # Agent orchestrator
|   +-- controller.py        # LLM conversation loop
|   +-- conversation.py      # Message history management
|   +-- executor.py          # Background tool execution
|   +-- job.py               # Job status tracking
|   +-- events.py            # TriggerEvent model
|   +-- session.py           # Session registry (keyed shared state)
|   +-- config.py            # Configuration loading
|   +-- registry.py          # Module registration
|   +-- loader.py            # Dynamic module loading
|
+-- modules/                 # Plugin APIs
|   +-- input/base.py        # InputModule protocol
|   +-- output/              # OutputModule + Router
|   +-- tool/base.py         # Tool protocol + BaseTool
|   +-- trigger/base.py      # TriggerModule protocol
|   +-- subagent/            # SubAgent system
|
+-- parsing/                 # Stream parsing
|   +-- state_machine.py     # StreamParser
|   +-- events.py            # ParseEvent types
|   +-- patterns.py          # Parser patterns
|   +-- format.py            # ToolCallFormat definitions
|
+-- prompt/                  # Prompt system
|   +-- aggregator.py        # System prompt building
|   +-- loader.py            # Prompt file loading
|   +-- template.py          # Jinja2 rendering
|   +-- plugins.py           # Extensible plugins
|
+-- builtins/                # Built-in implementations
|   +-- tools/               # bash, read, write, etc.
|   +-- inputs/              # cli, whisper, none
|   +-- outputs/             # stdout, tts
|   +-- tui/                 # TUI session, input, output
|   +-- subagents/           # explore, plan, memory
|
+-- llm/                     # LLM integration
|   +-- base.py              # LLMProvider protocol
|   +-- openai.py            # OpenAI-compatible provider
|   +-- message.py           # Message formatting
|
+-- utils/                   # Utilities
    +-- logging.py           # Structured logging
    +-- async_utils.py       # Async helpers
```

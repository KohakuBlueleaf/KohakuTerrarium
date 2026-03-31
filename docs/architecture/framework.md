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
agent = Agent.from_path("examples/agent-apps/my_agent")  # Load config
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
2. `submit()` creates `asyncio.Task` immediately (non-blocking)
3. LLM continues streaming
4. For DIRECT tools: processing loop waits for task, feeds result back
5. For BACKGROUND tools: placeholder added to conversation, result delivered later via `_on_complete` callback

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

Tools with `needs_context = True` receive a `ToolContext` with agent name, session, working directory, memory path, environment, and tool_format.

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

Sub-agents are background jobs. The `SubAgentManager` registers and spawns sub-agents, sharing the `JobStore` with the executor. Results are delivered via the executor's `_on_complete` callback, same as background tools. See [Creatures - Sub-Agents](../concept/creature.md#sub-agents) for the conceptual overview.

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
- **Dynamic** (default): Model uses the `info` tool to read docs on demand
- **Static**: All tool docs included in system prompt upfront

## Agent Event Architecture

The agent has three concurrent event sources, all converging on `_process_event()`:

```
                  +-------------------+
                  |  _process_event() |  <-- processing lock serializes access
                  +-------------------+
                    ^       ^       ^
                    |       |       |
              +-----+  +---+---+  +--------+
              |Input |  |Trigger|  |BG Tool |
              |Loop  |  |Tasks  |  |Complete|
              +------+  +-------+  +--------+

Input Loop:    agent.run() -> input.get_input() -> _process_event()
Trigger Tasks: asyncio.create_task(_run_trigger()) -> _process_event()
BG Complete:   executor._on_complete callback -> asyncio.create_task(_process_event())
```

**Input loop** (`agent.run()`): Blocks on `input.get_input()`, processes user messages.

**Trigger tasks**: Each trigger runs as a separate `asyncio.Task`. When a trigger fires (channel message, timer, etc.), it calls `_process_event()` directly.

**Background completion**: When a background tool finishes, the executor calls `_on_bg_complete` which creates a new task calling `_process_event()`. This is the SAME delivery path as triggers.

The `_processing_lock` (asyncio.Lock) ensures only one `_process_event` runs at a time, serializing concurrent trigger fires and background completions.

## Processing Loop

`_process_event_with_controller()` handles ONE event and all its direct tool calls:

```
Phase 1: Reset router, prepare tracking
Phase 2: Run controller.run_once()
         +-- ToolCallEvent (direct)    -> start task, track in direct_tasks
         +-- ToolCallEvent (background)-> start task, add placeholder to conversation
         +-- SubAgentCallEvent         -> start sub-agent (background)
         +-- CommandResultEvent        -> on_activity()
         +-- TextEvent / Other         -> output_router.route()
Phase 3: Termination check
Phase 4: Flush output, collect feedback
         +-- Output feedback (named outputs)
         +-- Direct tool results (waited for)
Phase 5: Exit if no feedback; continue if direct results pending
Phase 6: Push feedback to controller -> loop to Phase 1
```

**Key design: background tools do NOT block the loop.** They get a placeholder response ("Running in background") so the API always sees a tool result for every tool call. When the background tool finishes, the executor's `_on_complete` callback fires `_process_event` as a new event -- the agent is back in idle by then, waiting for input or the next trigger.

### Tool Execution Modes

| Mode | Declaration | Behavior |
|------|-------------|----------|
| **DIRECT** | `execution_mode = ExecutionMode.DIRECT` | Loop waits for result, feeds back to LLM |
| **BACKGROUND** | `execution_mode = ExecutionMode.BACKGROUND` | Placeholder response, result delivered later via `_on_complete` |
| **Opt-in background** | Model passes `run_in_background=True` | Same as BACKGROUND, but decided by the model at call time |

Tools declaring `BACKGROUND` mode are FORCED background -- the model cannot make them direct. This is used for tools like `terrarium_observe` that wait indefinitely for external events.

### Example: Root Agent + Background Observe

```
1. User: "Fix the auth bug"
2. _process_event(user_input)
   -> LLM calls terrarium_send(channel=tasks, message="Fix auth bug")  [direct]
   -> LLM calls terrarium_observe(channel=results)                      [forced bg]
   -> terrarium_send completes, result fed back
   -> terrarium_observe gets placeholder "Running in background"
   -> LLM responds: "Task dispatched, team is working on it"
   -> No more feedback -> loop exits
3. Agent idle, waiting for input.get_input()
4. ... swe creature works, posts to results channel ...
5. terrarium_observe receives message, executor fires _on_complete
6. _on_bg_complete -> asyncio.create_task(_process_event(tool_complete_event))
7. _process_event runs with the observe result
   -> LLM sees the result, summarizes for user
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

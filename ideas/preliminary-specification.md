# KohakuTerrarium Framework Specification

> A universal agent framework for building any type of fully self-driven agent system.

## Table of Contents

1. [Vision & Goals](#vision--goals)
2. [Core Architecture](#core-architecture)
   - [Five Major Systems](#five-major-systems)
   - [Unified Event Model (TriggerEvent)](#unified-event-model-triggerevent)
3. [Controller as Orchestrator (Key Design Principle)](#controller-as-orchestrator-key-design-principle)
4. [Module Specifications](#module-specifications)
5. [Sub-Agent System](#sub-agent-system)
6. [Configuration System](#configuration-system)
7. [Memory System](#memory-system)
8. [Parsing & State Machine](#parsing--state-machine)
9. [Error Handling](#error-handling)
10. [Lifecycle Management](#lifecycle-management)
11. [Observability](#observability)
12. [Example Agents](#example-agents)
13. [Implementation Guidelines](#implementation-guidelines)
14. [Appendix: Glossary](#appendix-glossary)

---

## Vision & Goals

### What is KohakuTerrarium?

KohakuTerrarium is a framework that allows building **any type of agent system**. Not just "any LLM can be used" but "any purpose, any design, any workflow of agent" can be implemented.

The name comes from:
- **Kohaku**: Project common prefix
- **Terrarium**: Self-contained ecosystems - the framework lets you build different agent "terrariums" that can be fully autonomous (daemon) or open (request-response)

### Core Philosophy

1. **Universal Agent Abstraction**: Many agent systems have different running logic but the same component logic. The difference is in composition and execution order.
2. **Controller as Pure Orchestrator**: The controller's role is to dispatch tasks, not to do heavy work itself. Long outputs should come from sub-agents, not the controller directly.
3. **Low-Code for Built-ins**: Users can create agents using only configuration files (JSON + Markdown)
4. **Dev-Friendly for Extensions**: Developers can easily create custom Input/Output/Tool modules as Python plugins
5. **Streaming-First**: Output streaming is a first-class citizen for minimal latency
6. **Background Execution**: Tools and sub-agents run in background without blocking controller
7. **Unified Event Model**: Everything flows through TriggerEvent - inputs, triggers, tool completions, sub-agent outputs

### Example Use Cases

| Agent Type | Input | Controller Logic | Output |
|------------|-------|------------------|--------|
| SWE Agent (Claude Code) | User request | Read codebase, plan, execute tools | File diffs, stdout |
| Group Chat Bot | Chat messages | Decide: respond / search memory / update memory | Chat API |
| Neuro-sama Bot | ASR stream | Generate response + memory lookup | Streaming TTS |
| Monitoring System | Triggers (timers, sensors) | Analyze data, debug, reprogram | System commands |
| Drone Controller | Sensor data triggers | Self-diagnosis, component bypass | Control commands |

---

## Core Architecture

### Five Major Systems

```
┌─────────────────────────────────────────────────────────────────┐
│                        KohakuTerrarium                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐     ┌─────────┐                                   │
│  │  INPUT  │     │ TRIGGER │                                   │
│  │         │     │         │                                   │
│  │ - User  │     │ - Timer │                                   │
│  │ - ASR   │     │ - Event │                                   │
│  │ - Chat  │     │ - Cond. │                                   │
│  │ - API   │     │ - Comp. │                                   │
│  └────┬────┘     └────┬────┘                                   │
│       │               │                                         │
│       └───────┬───────┘                                         │
│               ▼                                                 │
│       ┌──────────────┐         ┌──────────────┐                │
│       │  CONTROLLER  │◄───────►│ TOOL CALLING │                │
│       │              │         │              │                │
│       │  (Main LLM)  │         │ - Commands   │                │
│       │              │         │ - Functions  │                │
│       │  Streaming   │         │ - Sub-agents │                │
│       │  Output      │         │              │                │
│       └──────┬───────┘         └──────────────┘                │
│              │                                                  │
│              ▼                                                  │
│       ┌──────────────┐                                         │
│       │    OUTPUT    │                                         │
│       │              │                                         │
│       │ - Stdout     │                                         │
│       │ - File write │                                         │
│       │ - TTS stream │                                         │
│       │ - API call   │                                         │
│       └──────────────┘                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Input** is an explicit "input information + trigger agent" mechanism
   - User explicitly provides input which triggers the agent

2. **Trigger** is an automatic system that triggers agent operations
   - Can have built-in prompts that tell agent what to do for this trigger
   - Provides: trigger type, reason, and relevant context
   - Input is essentially a specialized user-controlled trigger

3. **Controller** is the main LLM in an agent
   - Processes input/trigger context
   - Outputs streaming tokens
   - Can embed tool calls and sub-agent calls in output

4. **Tool Calling** intercepts patterns from controller output
   - Starts background threads/tasks for each tool call
   - Does NOT block the main LLM
   - Reports status back to controller

5. **Output** handles the final output
   - Triggered when controller enters "outputting mode"
   - Can stream tokens directly (TTS) or pack full output
   - State machine routes different formats to different output modules

### Unified Event Model (TriggerEvent)

All components communicate through a single event type - `TriggerEvent`. This lives in `core/events.py`:

```python
@dataclass
class TriggerEvent:
    """Universal event type that flows through the entire system."""

    type: str                    # "user_input", "idle", "tool_complete", "subagent_output"
    content: str = ""            # Main content/message
    context: dict[str, Any]      # Additional context data
    timestamp: datetime

    job_id: str | None = None    # For tool/subagent completion
    prompt_override: str | None = None  # Optional prompt injection
    stackable: bool = True       # Can be batched with simultaneous events
```

**Event Flow**:
```
Input Module      ──► TriggerEvent(type="user_input")
Timer Trigger     ──► TriggerEvent(type="idle")          ──┐
Tool Completion   ──► TriggerEvent(type="tool_complete")   ├──► Controller Queue
SubAgent Output   ──► TriggerEvent(type="subagent_output") │     (batches stackable)
Monitor Trigger   ──► TriggerEvent(type="monitor")       ──┘
```

**Stackable Events**: When multiple triggers fire simultaneously, stackable events are batched:
```
Controller receives:
  user: What happened yesterday?
  monitoring: Memory usage above 80%
```

---

## Controller as Orchestrator (Key Design Principle)

This is a **fundamental architectural principle** that shapes the entire framework.

### The Principle

The controller's primary role is to **orchestrate and dispatch**, not to generate long content:

| Controller SHOULD | Controller SHOULD NOT |
|-------------------|----------------------|
| Dispatch tool calls | Generate long explanations |
| Spawn sub-agents | Write lengthy code directly |
| Make decisions | Produce verbose output |
| Read/check job status | Do work that could be delegated |
| Trigger final output | Stream content directly (usually) |

### Why This Matters

1. **Controller stays lightweight**: Short context, fast decisions, can handle many concurrent tasks
2. **Separation of concerns**: Decision-making ≠ content generation
3. **Specialization**: Output sub-agents can have role-play personalities, specialized formats
4. **Scalability**: Controller can manage many workers without bloating its context

### Controller Output Patterns

**Good** - Controller as dispatcher:
```
##subagent:memory_search##
query: conversations from yesterday
##subagent##

##subagent:output_agent##
context: User asking about yesterday, searching memory...
##subagent##
```

**Avoid** - Controller doing everything:
```
Let me search through the memory and find what we discussed yesterday.
Based on my search, I found that we talked about three main topics:
1. The new authentication system design...
2. Database migration strategy...
[500 more lines of content]
```

### The Output Sub-Agent Pattern

For agents that need user-facing output (chatbots, assistants), use an **output sub-agent**:

```
┌─────────────────────────────────────────────────────────────┐
│                       Controller                             │
│  - Receives triggers (input, tool results, etc.)            │
│  - Dispatches memory search/write sub-agents                │
│  - Sends context updates to output sub-agent                │
│  - Makes high-level decisions                               │
│  - SHORT outputs only                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌──────────────────┐
│ memory_ret  │  │ memory_write│  │  output_agent    │
│ (worker)    │  │ (worker)    │  │  (interactive)   │
│             │  │             │  │                  │
│ Returns:    │  │ Returns:    │  │ - Receives ctx   │
│ memories    │  │ "done"      │  │ - Decides WHAT   │
│             │  │             │  │ - Decides IF     │
│ → Controller│  │ → Controller│  │ - Streams output │
└─────────────┘  └─────────────┘  │ → User directly  │
                                  └──────────────────┘
```

### Output Sub-Agent Capabilities

Output sub-agents marked with `output_to: external` can:

1. **Decide WHAT to say**: Has full context, generates appropriate response
2. **Decide WHETHER to say**: Can choose silence (adaptive no-output)
3. **Stream directly to user**: TTS, chat API, terminal
4. **Stay interactive**: Receives context updates, can produce multiple outputs

```yaml
subagents:
  - name: memory_search
    output_to: controller      # Results go to parent (default)

  - name: output_agent
    output_to: external        # Can output directly to user
    output_module: tts_stream  # Which output module to use
    interactive: true          # Stays alive, receives updates
```

### Example: Conversation Bot Architecture

```
User speaks: "What did we talk about yesterday?"
                         │
                         ▼
               TriggerEvent(type="user_input")
                         │
                         ▼
                  ┌─────────────┐
                  │ Controller  │
                  │             │
                  │ Decision:   │
                  │ 1. Search memory
                  │ 2. Update output agent
                  │ 3. Let output agent handle response
                  └──────┬──────┘
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
##subagent##      ##subagent##       ##subagent:output##
memory_search     context_update     (interactive)
  "yesterday"       (parallel)
##subagent##      ##subagent##       Receives:
      │                │             - User query
      │                │             - "searching memory..."
      ▼                ▼                  │
  Returns           Returns               │
  memories          "done"                │
      │                │                  │
      └────────► Controller ◄─────────────┘
                      │
                      ▼
              ##update output_agent##
              new_context: [memory results]
              ##update##
                      │
                      ▼
              Output agent decides:
              - What to say based on memories
              - How to phrase it (personality)
              - Whether to say anything
                      │
                      ▼
              Streams to TTS → User hears response
```

### When Controller CAN Output Directly

For simple agents (SWE-agent style), controller can output directly when:
- Output is short (status updates, confirmations)
- No personality/role-play needed
- Immediate response required

```yaml
# SWE agent - controller outputs directly for short responses
output:
  type: stdout
  controller_direct: true  # Allow controller to output

# Chat agent - controller delegates to output sub-agent
output:
  type: tts_stream
  controller_direct: false  # Controller must use output sub-agent
```

---

## Module Specifications

### Input Module

**Purpose**: Receive external input and trigger agent processing

**Interface**: Standard interface with extension points

```python
class InputModule(Protocol):
    async def get_input(self) -> InputEvent:
        """Wait for and return the next input event."""
        ...

    async def stream(self) -> AsyncIterator[InputChunk]:
        """Stream input in real-time (for ASR, etc.)."""
        ...
```

**Built-in Implementations**:
- CLI/TUI Input (user typing)
- ASR Input (speech recognition)
- Discord Bot Input (chat messages)
- API Input (webhook/REST)

**Characteristics**:
- Can be real-time + buffered
- Uses triggers for timed reading (e.g., check input when controller finishes speaking)

---

### Trigger Module

**Purpose**: Automatically trigger agent based on conditions

**Trigger Types**:

| Type | Description | Example |
|------|-------------|---------|
| Time-based | Cron, interval, idle detection | "Check every 5 minutes", "After 30s idle" |
| Event-based | External events | Webhooks, file changes, system events |
| Condition-based | Internal state | Memory threshold, context length |
| Composite | AND/OR combinations | "Idle AND new_memory_available" |

**Trigger Event Structure**:
```python
@dataclass
class TriggerEvent:
    trigger_type: str           # What kind of trigger
    trigger_reason: str         # Why it triggered
    context: dict[str, Any]     # Relevant context data
    timestamp: datetime
    prompt_override: str | None # Optional prompt for this trigger
```

**Key Points**:
- Trigger provides context that affects controller behavior
- Trigger can include built-in prompt (like skills)
- Multiple triggers can be active simultaneously

---

### Controller Module

**Purpose**: Main LLM that **orchestrates** the agent - dispatching tasks and making decisions

> **Key Principle**: The controller should act as an orchestrator, not a worker. See [Controller as Orchestrator](#controller-as-orchestrator-key-design-principle) for details.

**What Controller Does**:
- Receives TriggerEvents (input, tool results, sub-agent outputs)
- Makes decisions about what to do next
- Dispatches tools and sub-agents
- Manages context and job status
- Produces SHORT outputs (status, decisions, dispatch commands)

**What Controller Delegates**:
- Long content generation → output sub-agent
- Memory search/write → specialized sub-agents
- Complex computations → tools or sub-agents
- Role-play/personality → output sub-agent

**Conversation Model**:

The controller operates as a multi-turn conversation with the system:

```
Turn 1:
  System: [context + input/trigger info]
  Controller: [streaming output with tool calls]

Turn 2:
  System: [previous output summary + job status updates]
  Controller: [decide to read job results or continue]

Turn 3:
  System: [requested job results + new status]
  Controller: [continue processing or output final]
```

**Context Compaction**:

The system manages context to avoid duplication:

```
# Before compaction:
ctx
info1
read_req1
result1
info2

# After compaction:
ctx
result1 (folded into context)
info2
```

**System Prompt Aggregation**:

Static aggregation at startup includes:
- Original system prompt from config
- Framework hints about crucial commands
- Tool list (name + one-line description for accurate selection)
- Sub-agent list (name + one-line description for accurate selection)

Controller uses framework commands to request detailed info:
- `##info tool_name##` - Get full tool documentation (args, examples, output format)
- `##info subagent_name##` - Get full sub-agent documentation (purpose, capabilities)

---

### Tool Calling Module

**Purpose**: Execute tools in background, report results to controller

**Tool Types**:

1. **Stateless Functions**: Pure functions, no persistent state
2. **Stateful Tools**: Maintain state between calls (connection pools, handles)
3. **Tool Instances**: Instantiated with config, have lifecycle (init/cleanup)

> Note: Multi-turn stateful tools should be implemented as sub-agents (where controller can be non-LLM)

**Execution Modes**:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Direct/Blocking** | All jobs complete, return all results | Simple tools, need result immediately |
| **Background** | Periodic status updates, refresh context | Long-running tasks, can continue without result |
| **Stateful** | Multi-turn input↔output (like yield) | Interactive tools, sub-agents |

**Job Status Information**:

When reporting to controller, include:
- Basic: job_id, job_type, status (running/done/error)
- Timing: start_time, duration_so_far
- Output stats: lines_count, bytes_count
- Preview: first_n_chars, last_n_chars (without full content)

**Reading Job Results**:

Controller explicitly requests results:
```
##read job_id [--lines N] [--offset M]##
```

This is itself a "tool call" - framework intercepts and returns the requested portion.

---

### Output Module

**Purpose**: Route and deliver final output to appropriate destinations

**Architecture**: State Machine + Router

```
Controller Output Stream
         │
         ▼
    ┌─────────────┐
    │ State       │
    │ Machine     │
    │ (Parser)    │
    └─────┬───────┘
          │
    ┌─────┴─────┬─────────┬─────────┐
    ▼           ▼         ▼         ▼
┌───────┐ ┌─────────┐ ┌───────┐ ┌───────┐
│Stdout │ │File     │ │TTS    │ │API    │
│       │ │Writer   │ │Stream │ │Call   │
└───────┘ └─────────┘ └───────┘ └───────┘
```

**Key Characteristics**:
- Support both streaming AND/OR full output
- Format/pattern triggers specific output module
- Stdout can be captured for group chat/TTS (minimal latency path)
- Parallel outputs via wrapper class (e.g., `ParallelOutput`)

**Built-in Implementations**:
- Standard Output (terminal)
- Diff-format File Output (with modified time guard)
- TTS Streaming Output
- Discord Bot Output
- API/Webhook Output

**State Machine Triggers**:

Using Python `match-case` for clean pattern matching:
```python
match state:
    case OutputState.NORMAL:
        # Regular text → stdout
    case OutputState.FILE_BLOCK:
        # Diff format → file writer
    case OutputState.TTS_BLOCK:
        # Speech text → TTS stream
```

---

## Sub-Agent System

### What is a Sub-Agent?

A sub-agent is a **fully working agent** with:
- Its own Controller (can be LLM or non-LLM)
- Its own Tool Calling capability
- Configurable Output (to parent OR directly to user)

**Default Constraints**:
- Input: Only from parent controller's sub-agent call
- Output: To parent controller only

**Special Case - Output Sub-Agent**:
- Can be configured with `output_to: external`
- Streams directly to user (TTS, chat, terminal)
- Can be `interactive: true` to receive ongoing context updates
- Decides WHAT to say and WHETHER to say it

> This pattern is central to the [Controller as Orchestrator](#controller-as-orchestrator-key-design-principle) principle.

### Parent-Child Relationship

```
┌─────────────────────────────────────────┐
│            Parent Agent                  │
│  ┌───────────────────────────────────┐  │
│  │          Controller               │  │
│  │  - Sees sub-agent state in prompt │  │
│  │  - Decides when to read results   │  │
│  │  - Decides when to cleanup        │  │
│  └─────────────┬─────────────────────┘  │
│                │                         │
│     ┌──────────┴──────────┐             │
│     ▼                     ▼             │
│  ┌──────────┐       ┌──────────┐        │
│  │Sub-Agent │       │Sub-Agent │        │
│  │(explore) │       │(memory)  │        │
│  └──────────┘       └──────────┘        │
│                                          │
└──────────────────────────────────────────┘
```

### Sub-Agent State Visibility

Parent controller's system prompt includes:
```
## Running Sub-Agents
- explore_task_123: status=running, duration=5.2s, output_lines=42
- memory_search_456: status=done, duration=1.1s, output_lines=8
```

Parent can then:
```
##read explore_task_123 --lines 20##
```

### Nesting Configuration

- **Default**: 1 level of nesting allowed
- **Configurable**: Can allow deeper nesting
- **Warning**: System warns at startup if nesting > 1 configured

### Sub-Agent vs Skill vs Tool

| Concept | Definition | Documentation Focus |
|---------|------------|---------------------|
| **Tool** | Executable function | "How to call, what happens, how to understand output" |
| **Sub-Agent** | Nested agent with limited scope | "What this setup is specific for" |
| **Skill** | Procedural knowledge | "How to do something" |

---

## Configuration System

### Agent Folder Structure

```
my_agent/
├── config.yaml          # Main configuration
├── prompts/
│   ├── system.md        # Main system prompt
│   ├── tools/
│   │   ├── bash.md      # Tool documentation
│   │   └── search.md
│   └── subagents/
│       ├── explore.md   # Sub-agent documentation
│       └── memory.md
├── memory/              # First-citizen memory (read-write)
│   ├── rules.md         # Can be marked protected
│   └── context.md
└── custom/              # Optional Python plugins
    ├── __init__.py
    ├── tools.py
    └── outputs.py
```

### Configuration Format

**Main Config (YAML/JSON/TOML)**:
```yaml
name: my_swe_agent
version: "1.0"

controller:
  model: gpt-4
  temperature: 0.7
  max_tokens: 4096

input:
  type: cli

triggers:
  - type: idle
    timeout: 30
    prompt: "User has been idle. Consider if any proactive action needed."

tools:
  - name: bash
    type: builtin
    doc: prompts/tools/bash.md
  - name: custom_tool
    type: plugin
    module: custom.tools
    class: MyCustomTool

subagents:
  - name: explore
    config: subagents/explore.yaml

output:
  type: parallel
  modules:
    - type: stdout
    - type: file_diff
      extensions: [".py", ".js", ".ts"]

parsing:
  tool_format: "##tool##\n{content}\n##tool##"
  subagent_format: "##subagent:{name}##\n{args}\n##subagent##"
```

**Prompt Templates (Markdown with Jinja-like syntax)**:
```markdown
# System Prompt

You are a helpful coding assistant.

## Available Tools
{% for tool in tools %}
- {{ tool.name }}: {{ tool.short_desc }}
{% endfor %}

## Tool Call Format
To call a tool, use:
##tool##
name: <tool_name>
args: <arguments>
##tool##
```

### Module Registration

Two methods supported:

1. **Decorators** (for Python modules):
```python
@register_tool("my_tool")
class MyTool:
    async def execute(self, args: dict) -> str:
        ...
```

2. **Config-driven** (for config-only tools):
```yaml
tools:
  - name: web_search
    type: builtin
    config:
      engine: google
      max_results: 10
```

---

## Memory System

### Types of Memory

1. **First-Citizen Memory** (Document-based)
   - Folder with txt/md files
   - Read-write by default
   - Some files can be marked as protected (read-only)
   - Agent can add notes beside protected content
   - Loaded into context, important info always available

2. **Long-term Memory** (via Tools)
   - RAG-like systems
   - Vector database (KohakuVault)
   - BM25 search
   - Implemented as tool calls

### Memory Access

```yaml
memory:
  path: ./memory
  protected:
    - rules.md        # Agent cannot modify
    - persona.md      # Agent cannot modify
```

Agent interaction:
```
##tool##
name: memory_write
args:
  file: context.md
  content: "User prefers TypeScript over JavaScript"
##tool##
```

### Context Window Management

**Strategy**: Configurable sliding window + summarization

1. **Sliding Window**: Keep recent N messages/tokens
2. **Summarization**: When context grows, use external summarize tool
3. **First-citizen Memory**: Important info stays in context
4. **On-demand Loading**: Tool/sub-agent details loaded when requested

```yaml
context:
  max_tokens: 16000
  summarize_threshold: 12000
  keep_recent: 10  # messages
  summarizer:
    type: subagent
    name: summarize
```

---

## Parsing & State Machine

### Call Syntax Design

**Requirements**:
- Short (minimal token usage)
- Easy to parse
- State-machine friendly
- Configurable per agent

**Default Format** (can be overridden):
```
##tool##
name: bash
args:
  command: ls -la
##tool##

##subagent:explore##
query: Find all Python files related to authentication
##subagent##

##read job_123 --lines 50##
```

### State Machine Implementation

Manual state machine (not Lark) for lightweight parsing:

```python
class OutputParser:
    class State(Enum):
        NORMAL = auto()
        TOOL_BLOCK = auto()
        SUBAGENT_BLOCK = auto()
        OUTPUT_BLOCK = auto()

    def __init__(self, config: ParserConfig):
        self.state = State.NORMAL
        self.buffer = []
        self.config = config

    def feed(self, chunk: str) -> list[ParseEvent]:
        events = []
        for char in chunk:
            match self.state:
                case State.NORMAL:
                    if self._matches_start_pattern(char):
                        self.state = self._determine_block_type()
                        events.append(BlockStartEvent(...))
                    else:
                        events.append(TextEvent(char))
                case State.TOOL_BLOCK:
                    if self._matches_end_pattern(char):
                        events.append(ToolCallEvent(self._parse_tool()))
                        self.state = State.NORMAL
                    else:
                        self.buffer.append(char)
                # ... other states
        return events
```

### Streaming Parse Behavior

- **Buffer until complete**: Wait for closing tag before triggering action
- Opening tag detected → prepare/allocate resources
- Closing tag detected → execute action
- Incomplete blocks at stream end → error handling

---

## Error Handling

### Error Categories

| Error Type | Handling Strategy |
|------------|-------------------|
| Bad tool call format | Report to controller, let it retry |
| Tool execution error | Report to controller, can rerun |
| Sub-agent crash | Report to controller, can restart |
| API error (429, etc.) | Exponential backoff with jitter |
| Invalid LLM response | Parse what's possible, report issues |

### Configuration

```yaml
error_handling:
  api_retry:
    max_attempts: 5
    base_delay: 1.0
    max_delay: 60.0
    jitter: true
  tool_errors:
    report_to_controller: true
    auto_retry: false
  subagent_errors:
    report_to_controller: true
    allow_restart: true
```

### Error Reporting to Controller

```
## Job Error Report
- job_id: bash_123
- job_type: tool/bash
- error_type: execution_failed
- error_message: "Command not found: nonexistent_command"
- suggestion: "Check if the command exists or use an alternative"
```

---

## Lifecycle Management

### Agent Modes

| Mode | Characteristics | Use Case |
|------|-----------------|----------|
| **Request-Response** | Start per request, state persisted externally | SWE agents, API services |
| **Daemon** | Long-running, state in memory | Chatbots, monitoring |
| **Hybrid** | Starts as req-resp, can become daemon | Adaptive systems |

**Determination**: Based on trigger configuration
- No timer triggers → request-response
- Timer/monitor triggers → daemon mode

### State Persistence

State consists of:
- Job states (running tasks)
- Context (chat history)
- Memory updates

For request-response mode:
```python
class AgentState:
    context: Conversation
    jobs: dict[str, JobState]
    memory_updates: list[MemoryUpdate]

    def serialize(self) -> bytes: ...
    def deserialize(self, data: bytes) -> "AgentState": ...
```

---

## Observability

### Logging

**Terminal**: Minimal but informative (like existing SWE agents)
```
[12:34:56] INPUT: User request received
[12:34:57] TOOL: Starting bash_123 (ls -la)
[12:34:58] TOOL: bash_123 completed (0.8s, 42 lines)
[12:34:59] OUTPUT: Streaming response...
```

### Web Dashboard

Features:
- Running tasks/jobs overview
- Job status and output preview
- Overall agent output stream
- Memory state visualization
- Context window usage

### Metrics

```python
@dataclass
class AgentMetrics:
    total_requests: int
    total_tokens_in: int
    total_tokens_out: int
    tool_calls: dict[str, int]
    subagent_calls: dict[str, int]
    error_count: int
    avg_response_time: float
```

---

## Example Agents

### 1. SWE Agent (Claude Code style)

**Architecture**: Controller with direct output (simpler pattern)

**Input**: User request (CLI)
**Trigger**: None (pure request-response)
**Controller Role**:
- Receives user request
- Dispatches exploration, planning sub-agents
- Dispatches tool calls (bash, file read/write)
- Outputs short status updates directly
- Delegates file writing to diff-format output module

**Tools**: bash, file_read, file_write, web_search
**Sub-agents**:
- `explore`: Codebase exploration (returns findings to controller)
- `plan`: Planning generation (returns plan to controller)

**Output**: Stdout (direct) + diff-format file writing

**Why Controller Can Output Directly**:
- Outputs are short (status, confirmations)
- No personality/role-play needed
- SWE context benefits from controller having full picture

```yaml
output:
  type: parallel
  controller_direct: true  # Controller can output
  modules:
    - type: stdout
    - type: file_diff
```

---

### 2. Group Chat Agent

**Architecture**: Controller as pure orchestrator with output sub-agent

**Input**: Chat messages (Discord/API)
**Triggers**:
- New message → decide to respond
- Long idle → generate topic

**Controller Role** (orchestrator only):
- Receives message trigger
- Decides: respond? search memory? update memory?
- Dispatches appropriate sub-agents
- Does NOT generate response content itself

**Tools**: (none - all via sub-agents)
**Sub-agents**:
- `memory_search`: Search long-term memory (returns to controller)
- `memory_write`: Update memory (returns to controller)
- `response_agent`: **output_to: external** - generates and sends response

**Output**: Chat API (via response_agent)

**Special Features**:
- **Adaptive no-output**: response_agent decides whether to speak
- **Role-play**: response_agent has personality, controller doesn't

```yaml
subagents:
  - name: memory_search
    output_to: controller

  - name: response_agent
    output_to: external        # Sends to chat directly
    output_module: discord
    interactive: false         # One-shot per trigger
```

**Flow**:
```
New message arrives
       │
       ▼
Controller: "Should I respond to this?"
       │
       ├─► Yes → Dispatch memory_search + response_agent
       │            │
       │            ▼
       │         response_agent decides:
       │         - Generate response (streams to Discord)
       │         - OR stay silent (topic doesn't match character)
       │
       └─► No → Do nothing (adaptive silence)
```

---

### 3. Conversational Agent (Neuro-sama style)

**Architecture**: Controller as orchestrator with output sub-agent

**Input**: ASR stream (real-time + buffered)
**Triggers**:
- ASR complete → process
- Long idle → new topic

**Controller Role** (minimal, fast decisions):
- Receives ASR trigger
- Immediately dispatches output_agent with current context
- Dispatches memory sub-agents in parallel
- Sends context updates to output_agent as memory results arrive
- Output agent's output becomes part of controller's context

**Tools**: (none - all via sub-agents)
**Sub-agents**:
- `memory_retrieve`: Search memories (returns to controller)
- `memory_update`: Update long-term memory (returns to controller)
- `output_agent`: **output_to: external, interactive: true**

**Output**: Streaming TTS (via output_agent)

**Key Design**: Minimal latency through parallelism
- Output agent starts generating IMMEDIATELY
- Memory results arrive and update output agent's context
- Output agent can revise/continue based on new context

**Output Agent Design**:
- **Logically stateless**: Simply does `context → decide whether to output → output what`
- **Technically stateful**: Kept alive (`interactive: true`) mainly to keep ASR/TTS models in RAM (setup is slow)
- Output agent's output feeds back to controller as part of conversation context

```yaml
subagents:
  - name: memory_retrieve
    output_to: controller

  - name: memory_update
    output_to: controller

  - name: output_agent
    output_to: external
    output_module: tts_stream
    interactive: true          # Kept alive for model warmth, logically stateless
```

**Flow**:
```
User speaks: "What did we do yesterday?"
                    │
                    ▼
           TriggerEvent(user_input)
                    │
                    ▼
              Controller (fast)
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
memory_retrieve  memory_update   output_agent
"yesterday"      (background)    (starts immediately)
    │                                  │
    │                            Streams: "Hmm, let me
    │                            think about yesterday..."
    │                                  │
    ▼                                  │
Returns memories                       │
    │                                  │
    ▼                                  ▼
Controller ──► Update output_agent context
                                       │
                                       ▼
                              Streams: "Oh right! We talked
                              about the new project and..."
                                       │
                                       ▼
                                    TTS → User
```

---

### 4. Monitoring/Autonomous Agent (Drone Controller style)

**Architecture**: Trigger-driven controller with no user-facing output

**Input**: None (fully autonomous)
**Triggers**:
- Timer: Check sensors every 60s
- Condition: Anomaly detected in readings
- Event: Component failure signal

**Controller Role**:
- Receives monitoring triggers
- Analyzes data via tools
- Dispatches diagnostic sub-agents
- Decides on corrective actions
- Writes new control code

**Tools**: read_sensors, execute_command, compile_code
**Sub-agents**:
- `diagnostics`: Analyze component status
- `code_generator`: Generate bypass/fix code

**Output**: System commands + code files (no user output)

```yaml
input: null  # No user input

triggers:
  - type: timer
    interval: 60
    prompt: "Check sensor readings for anomalies"

  - type: condition
    check: "sensor.cpu_temp > 80"
    prompt: "CPU temperature critical, diagnose and fix"

output:
  type: system_command
  controller_direct: true
```

**Flow**:
```
Timer trigger (60s)
       │
       ▼
Controller: Check sensors
       │
       ▼
##tool:read_sensors##
       │
       ▼
Controller: Anomaly in motor_3!
       │
       ▼
##subagent:diagnostics##
motor_3 analysis
##subagent##
       │
       ▼
Returns: "Motor 3 bearing failure, recommend bypass"
       │
       ▼
##subagent:code_generator##
Generate bypass code for motor_3
##subagent##
       │
       ▼
##tool:compile_code##
##tool:execute_command## deploy
       │
       ▼
System continues with motor_3 bypassed
```

---

## Implementation Guidelines

### Project Structure

```
src/kohakuterrarium/
├── __init__.py
├── core/
│   ├── agent.py           # Main Agent class
│   ├── controller.py      # Controller/LLM interface
│   ├── conversation.py    # Conversation management
│   └── config.py          # Configuration loading
├── modules/
│   ├── input/
│   │   ├── base.py        # Input protocol
│   │   ├── cli.py         # CLI input
│   │   └── asr.py         # ASR input
│   ├── trigger/
│   │   ├── base.py        # Trigger protocol
│   │   ├── timer.py       # Time-based triggers
│   │   └── event.py       # Event triggers
│   ├── tools/
│   │   ├── base.py        # Tool protocol
│   │   ├── bash.py        # Bash command
│   │   └── memory.py      # Memory tools
│   └── output/
│       ├── base.py        # Output protocol
│       ├── stdout.py      # Standard output
│       ├── file.py        # File output
│       └── parallel.py    # Parallel output wrapper
├── parsing/
│   ├── state_machine.py   # Output parser
│   └── formats.py         # Format definitions
├── llm/
│   ├── base.py            # LLM protocol (OpenAI-oriented)
│   ├── openai.py          # OpenAI implementation
│   └── adapters.py        # Custom backend adapters
└── utils/
    ├── async_utils.py     # Async helpers
    └── logging.py         # Logging setup
```

### Async Pattern

```python
# Full asyncio throughout
async def run_agent(config: AgentConfig) -> None:
    agent = Agent(config)
    await agent.start()

    try:
        async for event in agent.events():
            match event:
                case InputEvent():
                    await agent.process_input(event)
                case TriggerEvent():
                    await agent.process_trigger(event)
                case JobCompleteEvent():
                    await agent.notify_controller(event)
    finally:
        await agent.shutdown()

# For sync tools, mark and use to_thread
@register_tool("sync_tool", requires_blocking=True)
class SyncTool:
    def execute(self, args: dict) -> str:  # sync method
        return subprocess.run(...).stdout
```

### LLM Interface

```python
class LLMProvider(Protocol):
    """OpenAI API-oriented interface with pluggable backends."""

    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
        tools: list[ToolDef] | None = None,
    ) -> AsyncIterator[ChatChunk]:
        ...

# Conversation class wraps message management
class Conversation:
    def __init__(self):
        self._messages: list[Message] = []

    def append(self, message: Message) -> None: ...
    def compact(self, summarizer: Callable) -> None: ...
    def to_messages(self) -> list[dict]: ...
    def serialize(self) -> str: ...
```

---

## Appendix: Glossary

| Term | Definition |
|------|------------|
| **Controller** | The main LLM that **orchestrates** the agent - dispatches tasks, makes decisions, produces short outputs |
| **Tool** | An executable function with defined interface |
| **Sub-agent** | A nested agent with own controller, typically returns results to parent |
| **Output Sub-agent** | Special sub-agent with `output_to: external` that can stream directly to user |
| **Interactive Sub-agent** | Sub-agent with `interactive: true` that stays alive and receives context updates |
| **Skill** | Procedural knowledge on how to accomplish something |
| **Trigger** | Automatic system that activates agent based on conditions |
| **TriggerEvent** | Universal event type that flows through the entire system (input, triggers, tool results, sub-agent outputs) |
| **Stackable Events** | TriggerEvents that can be batched together when occurring simultaneously |
| **First-citizen Memory** | Document-based memory always available in context |
| **Job** | A running tool or sub-agent instance |
| **Context Compaction** | Folding old results into summarized context |
| **Orchestrator Pattern** | Design principle where controller dispatches work instead of doing it directly |

---

*Document Version: 1.1*
*Last Updated: Added Controller as Orchestrator principle, Unified Event Model, expanded examples*

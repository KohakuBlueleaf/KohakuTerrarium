# Initial Design Discussion - Full Detail

> Complete Discord discussion and interview that led to KohakuTerrarium specification

---

## Core Systems Overview (KBlueLeaf)

The framework includes five major systems:
- **Input**
- **Trigger**
- **Controller**
- **Tool calling**
- **Output**

Where **sub-agent** is a special subset of controller + tool calling:
- Its input only comes from controller
- Its output only goes to controller

---

## Framework Key Points

1. Common modules can be configured via JSON + Markdown (system prompt)
2. Can write trigger prompts for sub-agents (like skills)
3. Output supports streaming
4. Input/tool-calling/sub-agent allows partial finished to trigger controller thinking (background task)

---

## Base Concept

Many agent running logic differs but "agent" component logic is the same. The difference is in:
- Composition
- Running order logic

---

## Detailed Examples

### SWE-Agent (like Claude Code)

- **Input**: User instructions
- **Controller**: Decides:
  - Which part of codebase to read
  - What thinking and planning to do
  - What output and modifications to make
- **Exploration**: Can be a sub-agent
- **Planning generation**: Can be a sub-agent
- **Read file**: Tool call
- **Command execution**: Tool call
- **Output**: Tool call (diff format apply to file with modified time guard)

### Group Chat Bot

- **Input**: Group chat updates (any new message)
- **Controller** starts thinking:
  1. Should we respond (based on existing context)?
  2. Should we search memory for possible context?
  3. Should we summarize current context as new memory?
- Once any of these trigger (can be simultaneous), it triggers search/write
- Can output result to group chat API
- **Idle trigger**: When there's long idle, bot can create new conversation topic based on current context + memory

### Neuro-sama Like Conversational Agent

- **Input**: ASR result from other people
- **Controller** puts context to:
  - "thinking response" sub-agent
  - "check memory" sub-agent
  - "update memory" sub-agent
  - (All optional - none are must-do, can skip)
- **Controller** monitors "thinking response" sub-agent's output
- Summarizes to final output based on role-play system prompt
- **Output module**: Streaming TTS - directly stream tokens from controller's output phase to TTS module for minimal latency

**Alternative flow**:
1. Controller calls sub-agents then directly generates answer and streams
2. After first answering (or controller decides to wait), calls update context sub-agent (thinking, retrieve memory) and memory update sub-agent (for long-term memory, RAG-like or doc-based)
3. Controller can decide to output new answer based on previous output + new context, or wait for user's answer (or wait for long idle trigger)

**Input details**:
- ASR can be real-time + buffer
- Uses trigger for timed reading
- Controller reads input immediately after speaking
- Uses timestamps to mark "when I was saying X, user was saying Y"

---

## Vision Statement

> "I want to make something that no matter what you think of, I can probably implement it in this framework"

Create a framework that can build **ANY agent** - not just "any LLM can be used" but:
- **Any purpose**
- **Any design**
- **Any workflow**
- Including custom input/output/tool calls
- Can be implemented with or without code (low-code for built-ins)

Examples of what should be buildable:
- Claude Code
- Codex
- Neuro-sama
- Drone systems
- Underwater machines with self-recovery
- Monitoring systems

---

## Data Flow Details

### Input System
- An explicit "input information + trigger whole agent" thing
- Input is essentially a specialized trigger (user-controlled)

### Trigger System
- Automatic system which triggers agent things
- Trigger may have built-in prompt to tell agent what to do for this trigger
- Provides: trigger type, reason, and relative context
- Context affects controller behavior (that's how agents work - prompt affects behavior)
- Types supported: time-based, event-based, condition-based, composite (AND/OR)

### Controller System
- The main LLM in an agent
- Output is streaming (may have lots of tool calls + direct output before tool finish or next run)

### Tool Calling System
- Controller may output "tool call req" during output
- Once output matches tool calling format, opens another thread to process (don't block main LLM)
- Tool calling can be: command, procedure, other specialized LLM call

### Output System
- Once main LLM jumps to "outputting mode", we stream or pack full output as input to Output module
- State machine + router based approach
- Format/state triggers specific output module
- Parallel outputs via wrapper class (ParallelOutput)
- Some output → specific process module, some → stdout (captured for group chat/TTS for lower latency)

---

## Controller Conversation Model (Critical Detail)

The controller is like a chatbot, but "our system" chats with it:

1. System gives controller the input/trigger things
2. Controller streaming, system catches tool/sub-agent requests and starts background tools/sub-agents
3. After streaming in step 2 (controller should tell us time to wait, configurable min/max), system sends tool status to controller
4. Controller can now decide which to read (with minimal tokens like "read job xxx") and we send current status (with line limit feature)

**Key**: Multi-run conversation with keep updating info. System prompt is same but conversation can be modified (info things or read things).

### Context Compaction Example

```
# State 1:
ctx
info1
read_req1
result1

# Becomes State 2:
ctx
result1 (early result, noted)
info2
read_req2
result2

# Becomes State 3:
ctx
result1
result2
info3
read_req3
....
```

No duplicated ctx things - pretend "result1/2" (can be early result, remember to note) are part of info.

---

## Sub-Agent Details

A sub-agent is a **fully working agent** with:
- Controller + tool-calling (and possible limiting "output" module)
- Input: directly from parent's sub-agent call
- Output: "optional text for controller"

**Parent visibility**:
- Controller has "what sub-agent is running and its state" in system prompt
- Can decide to check result whenever it wants (may have multiple outputs from sub-agent or streaming result)
- For finished sub-agent, controller can decide to "clean up" when all results are read and relative context is finished

**Nesting**:
- Configurable depth
- Default to one-level
- For any >1 level, should have warning at startup

**Stateful tools vs sub-agents**:
- Stateful tools with multiple calls on single instance should be considered a multi-turn sub-agent
- The "agent" or "controller" can be non-LLM
- Stateless functions, stateful tools, tool instances are all valid tool types
- Full tool agents = sub-agents

---

## Skills vs Sub-agents vs Tools

| Concept | Markdown Documentation Focus |
|---------|------------------------------|
| **Tool** | How to call the command, what will happen, how to understand output |
| **Sub-agent** | What this setup is specific for |
| **Skill** | How to do something |

**Sub-agent details**:
- Nested agent with addon/different system prompt
- Limited functionality (some modules banned, configurable)
- Causes different system prompt

**Self-calling consideration**:
- Top level agent allowed to call a sub-agent "with its own setup"
- With skills and special situations, agent can call itself
- Top level agent's setup is valid sub-agent (banned tools still banned, no sub-agent call by default)
- Decision: Keep simple, self-call may not be good idea initially

---

## Configuration System

### JSON/YAML/TOML (Main Config)
- Overall setup
- Controller setup
- Input configuration
- Trigger configuration
- Tool definitions
- Output module selection

### Markdown (Prompts)
- System prompt for each module
- Aggregation system to combine configuration into one system prompt
- Includes: setup prompt, structure, tools available, how to trigger them
- Can have Jinja-like or Python format string for formatting

### System Prompt Aggregation
- Static from agent folder
- Aggregates: original system prompt, framework hints about crucial commands, tool list info, sub-agent list info
- **Important**: Don't put ALL tool/sub-agent/skills info into original system prompt
- Only when controller uses "framework command" to request info, we give them info
- Tools/sub-agents are "skills with executable things"

### Tool Calling Format
Configurable, example:
```
##sub-agent##
- name: <sub-agent name>
- args...
- kwargs...
##sub-agent##
```

Once system finds `##sub-agent##` quote, directly triggers call in background while letting controller keep output.

**Format requirements**:
- Short
- Easy to parse
- Easy to utilize state machine (or Lark?) - Decision: State machine (manual)

---

## Tool Execution Modes

1. **Direct finish (blocking)**: All jobs with this type in single controller output finish, return all results to controller
2. **Background**: Tell model about info periodically, refresh ctx instead of adding
3. **State things**: Multiple input ↔ output interaction (like Python generator with `x = yield`)
   - Parent controller can interact with sub-agent like user interacts with SWE-agents
   - Marked as "not recommended but will implement eventually"

---

## Job Status Information

When reporting to controller, include:
- **Basic**: job_id, job_type, status (running/done/error)
- **Timing**: start_time, duration_so_far
- **Output stats**: lines_count, bytes_count
- **Preview**: first_n_chars, last_n_chars (without full content)

---

## Memory System

### Via tools/sub-agents (not first-class module)

### First-citizen memory
- Doc-based like claude.md or skills
- For important info
- Folder with txt/md files
- Read-write by agent
- Some memory can be manually marked read-only (user injected, protected memory) - crucial for role-playing
- Agent allowed to "add notes beside" protected content (whole folder is read-write)

### Long-term memory
- Non-first-citizen system
- RAG, vector database, complex database
- For super long-term memory
- Mainly for role-play, group chat, large projects
- Implemented as tool calling

---

## Context Management

Configurable strategy:
- **Sliding window** (because controller part is conversation-based)
- **Summarized context**: When context getting a bit long, use external summarize tool and replace old context with tool's result
- **First-citizen memory**: Doc-based for important info
- **On-demand loading**: Tool/sub-agent details loaded via framework commands

---

## Input/Output Module Design

### Input
- Standard interface + extension points
- Built-in implementations planned: CLI/TUI, ASR, Discord bot, API

### Output
- State machine + router based on format detection
- Multiple output modules can run in parallel via wrapper class
- Some can support chaining internally
- Using Python 3.12+ with `match case` for clean state machine
- **Key requirements**:
  1. Support both streaming AND/OR full output
  2. Some output → specific process module, some → stdout directly
  3. Stdout can be captured for group chat/TTS (smaller latency)

### Trigger
- All types: time-based, event-based, condition-based, composite
- Input is specialized trigger

---

## Error Handling

- **Bad tool-calling format or similar**: Report to controller
- **API errors (429, etc.)**: Random exponential backoff
- **Configurable**: max_try, max_wait_time
- **Tool-call or sub-agent error**: Parent can decide to rerun

---

## LLM Integration

- Abstract LLM interface based on OpenAI API
- OpenAI API-oriented pluggable backends
- Streaming support essential

---

## Lifecycle

- **State** = job state (if running) + ctx (chat history)
- Can be **request-response** if no long-running background task
- Should be able to become **long-running daemon** for chatbots, monitoring agents, self-recovering systems
- Determination: If no timer triggers for periodic wake-up or only SWE-agent-like communication → req-resp; if long-running triggers for monitoring → daemon

---

## Observability

- Minimal but informative logging in terminal (like SWE-agent)
- Web dashboard for observing tasks, jobs, overall output

---

## Module Registration

Two methods:
1. **Decorators**: `@register_input('name') def my_input(): ...`
2. **Config-driven**: For config-only tools/sub-modules/skills

---

## Streaming Parse Behavior

- **Buffer until complete**: Wait for closing tag before triggering action
- Using manual state machine (not Lark) for lightweight parsing

---

## Distribution Model

An agent system = folder with:
- JSON/TOML/YAML config (format flexible)
- Markdown config (prompts, prompt format, skills def, tools def, sub-agent def)
- Custom Python package/module (for plugin, custom output/tool/input/trigger)

**Built-in implementations planned**:
- Output: diff-format file, stdout, TTS stream, Discord bot
- Input: CLI/TUI, ASR, Discord bot
- Tools: bash/pwsh command, web search, web fetch, memory (KohakuVault for vector + BM25 search, KohakuRAG concepts)

---

## Project Details

### Name
**KohakuTerrarium**
- Kohaku: Project common prefix
- Terrarium: Framework allows building all types of fully self-driven agent systems, like different terrariums (some fully closed/daemon, some open/req-resp)

### First Release Scope
Full structure complete + implement builtin modules for example agents:
1. **SWE-agent**: Codex/Claude-Code/Gemini-CLI/OpenCode-like
2. **Group chat agent**: Demo timer trigger, long-term memory, adaptive no-output (not all messages need reply)

### Technical Stack
- Python 3.12+
- Full asyncio (sync modules marked as "require blocking" or "can be to_thread")
- Conversation class for context management
- Practical dependencies OK (pydantic, httpx, rich)
- State machine (manual) for parsing
- Decorators + config-driven for registration

---

## Code Conventions

- Source: `src/kohakuterrarium/`
- Examples: `agents/`
- Docs: `docs/`
- Ideas: `ideas/`
- **Max lines per file**: 600 (hard max: 1000)
- Highly modularized

### Import Rules
1. No imports inside functions (except cycle import or bad init avoidance)
2. Import grouping: builtin > 3rd party > kohakuterrarium
3. Import ordering: `import` > `from import` | short path > long path (by dots) | alphabetic (a-z)

### Python Style
- Modern Python: no `List`, `Tuple`, `Dict`, `Union`, `Optional`
- Use `list`, `tuple`, `dict`, `X | None`
- Prefer `match-case` over deeply nested `if-elif-else`

---

## Use Case: Autonomous Systems

Example from discussion - drone/underwater machine:
- May have broken component but with re-programming can be functional again (ignore broken component)
- May be offline, so have "monitoring trigger"
- Once trigger finds weird number/behavior, triggers agent to:
  - Read data
  - Process data
  - Run command to debug
  - Re-program control system to use good components

In this system:
- Only input is trigger
- Only output is "write to system code"
- Uses tool calling to apply new code or compile

---

## Open Questions Resolved

1. **Call self pattern**: Keep simple for v1, useful for reflection/self-critique but needs safeguards (max recursion, mode flag)
2. **Parser choice**: State machine (manual) over Lark - lighter weight, full control
3. **Output parallel**: Allowed via wrapper class, interface is single
4. **First-citizen memory access**: Read-write folder, some files can be protected, agent can add notes beside protected content

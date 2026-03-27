# KohakuTerrarium

> **Build any agent. Any purpose. Any workflow.**

KohakuTerrarium is a universal Python framework for building fully autonomous agent systems -- from coding assistants like Claude Code to conversational AI like Neuro-sama to self-healing monitoring drones to multi-agent coordination swarms.

```
     ┌──────────────────────────────────────────────────┐
     │              KohakuTerrarium                     │
     │                                                  │
     │    ┌─────────┐      ┌─────────┐                 │
     │    │  Input  │      │ Trigger │                 │
     │    └────┬────┘      └────┬────┘                 │
     │         └──────┬─────────┘                      │
     │                ▼                                │
     │         ┌────────────┐                          │
     │         │ Controller │◄──► Tools                │
     │         │    (LLM)   │◄──► Sub-Agents           │
     │         └──┬──────┬──┘                          │
     │            │      │                             │
     │            ▼      ▼                             │
     │      ┌────────┐ ┌──────────┐                    │
     │      │ Output │ │ Channels │◄──► Other Agents   │
     │      └────────┘ └──────────┘                    │
     └──────────────────────────────────────────────────┘
```

## Why KohakuTerrarium?

Most agent frameworks are built for one thing -- chatbots, or coding assistants, or automation. KohakuTerrarium is different: **one framework, infinite possibilities**.

| Feature | KohakuTerrarium | Traditional Frameworks |
|---------|-----------------|------------------------|
| **Agent Types** | Any -- coding, chat, monitoring, multi-agent | Usually single-purpose |
| **Communication** | Async channels for cross-agent messaging | No inter-agent protocol |
| **Output** | Streaming-first with parallel routing | Often blocking |
| **Tools** | Background execution, non-blocking, DI via ToolContext | Sequential execution |
| **Sub-Agents** | Full nested agents with own LLM + channels | Simple function calls |
| **Memory** | First-citizen folder-based system + session scratchpad | External databases only |
| **Configuration** | YAML + Markdown, minimal code | Heavy code required |

## Quick Start

```bash
# Clone and install
git clone https://github.com/KBlueLeaf/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e .

# Set API key
export OPENROUTER_API_KEY=your_key_here

# Run the SWE agent
python -m kohakuterrarium.run agents/swe_agent

# Run the multi-agent coordinator
python -m kohakuterrarium.run agents/multi_agent

# Run the planner agent
python -m kohakuterrarium.run agents/planner_agent
```

## Core Concepts

### Five Systems, One Framework

```
Input ──────┐
            ├──► Controller ◄──► Tool Calling
Trigger ────┘         │
                      ├──► Output
                      └──► Channels ──► Other Agents
```

1. **Input**: User requests, chat messages, API calls, ASR streams
2. **Trigger**: Timers, channel messages, events -- for autonomous operation
3. **Controller**: The LLM brain -- orchestrates everything (doesn't do heavy work)
4. **Tool Calling**: Background execution of tools and sub-agents (non-blocking, parallel)
5. **Output**: Streaming to stdout, files, TTS, APIs -- with smart routing

### Controller as Orchestrator (Key Design Principle)

The controller's job is to **dispatch tasks**, not do heavy work itself:

```
Controller decides ──► Tools/Sub-agents execute ──► Results flow back
        │                       │                        │
    (fast, lean)           (parallel)             (batched events)
```

- Controller outputs should be SHORT: tool calls, status updates, decisions
- Long outputs (code, explanations) come from specialized sub-agents
- This keeps the controller lightweight, context small, decisions fast

### Sub-Agents: Nested Intelligence

Sub-agents are full agents with their own LLM, but scoped and specialized:

```
[/explore]Find authentication code[explore/]
[/plan]Design the login flow[plan/]
[/worker]Implement the plan[worker/]
```

**Built-in Sub-Agents**:

| Sub-Agent | Purpose | Tools Access |
|-----------|---------|--------------|
| `explore` | Search and analyze codebase | glob, grep, read (read-only) |
| `plan` | Implementation planning | glob, grep, read (read-only) |
| `memory_read` | Retrieve from memory | read, glob (read-only) |
| `memory_write` | Store to memory | read, write |
| `response` | Generate user responses | (output sub-agent) |
| `summarize` | Compress and summarize content | (no tools) |
| `critic` | Review and validate work quality | (no tools) |
| `research` | Gather information on a topic | read, glob, grep, http |
| `worker` | Execute tasks with full tool access | bash, read, write, edit, glob, grep |
| `coordinator` | Orchestrate parallel sub-agent work | send_message, wait_channel, scratchpad |

### Channels: Cross-Agent Communication

Channels are async named message queues that let agents, tools, and triggers talk to each other without tight coupling:

```
[/send_message]
@@channel=results
Task A complete: found 3 endpoints
[send_message/]

[/wait_channel]@@channel=results[wait_channel/]
```

Channels power multi-agent patterns -- a controller dispatches research and worker sub-agents, coordinates via channels, and aggregates results. The `ChannelTrigger` lets autonomous agents wake up when messages arrive.

### Memory: First-Class Citizen

Folder-based memory that's always available, no external database needed:

```
memory/
├── character.md     # Protected - character/agent definition
├── rules.md         # Protected - constraints and guidelines
├── preferences.md   # Writable - user preferences
├── facts.md         # Writable - learned information
└── context.md       # Writable - current session context
```

**Scratchpad** provides session-scoped key-value working memory -- structured, cheap, auto-injected into context, cleared on restart. Different from file-based memory which persists across sessions.

## Multi-Agent Patterns

### Parallel Dispatch with Channel Coordination

The controller dispatches multiple sub-agents, then waits for their results through channels:

```
Controller
   ├──► [/research]Investigate auth patterns[research/]
   ├──► [/worker]Scaffold the module[worker/]
   └──► [/wait_channel]@@channel=results[wait_channel/]
              │
              ▼
        Aggregated results from all sub-agents
```

### Plan-Execute-Review Loop

The planner agent uses a scratchpad-driven loop: plan steps, execute each with a worker, validate with a critic, iterate:

```
[/plan]Design migration strategy[plan/]
   └──► Writes plan to scratchpad
[/worker]Execute step 1[worker/]
   └──► Returns result
[/critic]Review step 1 against the plan[critic/]
   └──► PASS or FAIL with issues
```

### Trigger-Driven Autonomous Agents

Agents with no user input, driven entirely by timers and channel triggers:

```yaml
input:
  type: none

triggers:
  - type: timer
    interval: 60
    prompt: "Run health check"
  - type: channel
    channel: monitor_alerts
    prompt: "Investigate this alert: {content}"
```

## Example Agents

### SWE Agent (Coding Assistant)

A software engineering agent for code analysis, file manipulation, and system tasks -- the Claude Code pattern.

```yaml
# agents/swe_agent/config.yaml
name: swe_agent
tools: [bash, python, read, write, edit, glob, grep, think, scratchpad, ask_user]
subagents: [explore, plan, worker, critic, summarize]
termination:
  max_turns: 100
  keywords: ["TASK_COMPLETE"]
```

### Multi-Agent (Coordination Demo)

A controller that dispatches research and worker sub-agents via channels, combining results for complex tasks.

```yaml
# agents/multi_agent/config.yaml
name: multi_agent
tools: [send_message, wait_channel, scratchpad, think, read, write, edit,
        bash, glob, grep, http]
subagents: [explore, research, worker, coordinator, summarize, critic]
termination:
  max_turns: 30
  keywords: ["ALL_TASKS_COMPLETE"]
```

### Planner Agent (Plan-Execute-Reflect)

A plan-and-execute agent with scratchpad-driven planning, worker execution, and critic review loops.

```yaml
# agents/planner_agent/config.yaml
name: planner_agent
tools: [read, write, edit, bash, glob, grep, scratchpad, think]
subagents: [plan, worker, critic, summarize]
termination:
  max_turns: 50
  keywords: ["ALL_STEPS_COMPLETE"]
```

### Monitor Agent (Autonomous System)

A trigger-driven agent with no user input -- runs health checks on timers and responds to channel alerts.

```yaml
# agents/monitor_agent/config.yaml
name: monitor_agent
input: { type: none }
triggers:
  - type: timer
    interval: 60
    prompt: "Run health check"
  - type: channel
    channel: monitor_alerts
    prompt: "Investigate this alert: {content}"
tools: [bash, http, read, scratchpad, send_message, think]
subagents: [explore, summarize]
```

### Conversational Agent (Neuro-sama Style)

A streaming conversational agent with Whisper ASR input, interactive output sub-agent, and TTS output.

```yaml
# agents/conversational/config.yaml
name: conversational
input: { type: whisper, model: small, device: cuda }
tools: [read, write, think, scratchpad]
subagents: [memory_read, memory_write, research, critic, output]
output: { type: custom, controller_direct: false }
```

### RP Agent (Character Chatbot)

A roleplay chatbot with persistent character memory and output sub-agent pattern.

```yaml
# agents/rp_agent/config.yaml
name: rp_agent
tools: [tree, read, write, edit, grep, glob]
subagents: [memory_read, memory_write, output]
memory:
  init_files: [character.md, rules.md]
  writable_files: [context.md, facts.md, preferences.md]
```

### Discord Bot (Group Chat)

A group chat bot with ephemeral context, named outputs, and custom emoji tools.

```yaml
# agents/discord_bot/config.yaml
name: discord_bot
input: { type: custom, module: ./custom/discord_io.py }
output:
  named_outputs:
    discord: { type: custom, module: ./custom/discord_io.py }
tools: [tree, read, write, edit, glob, grep, emoji_search, emoji_list, emoji_get]
subagents: [memory_read, memory_write]
```

## Built-in Tools

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands |
| `python` | Run Python scripts |
| `read` | Read file contents |
| `write` | Create or overwrite files |
| `edit` | Modify files with search-replace |
| `glob` | Find files by pattern |
| `grep` | Search file contents with regex |
| `tree` | Display directory structure |
| `think` | Extended reasoning scratchpad (no side effects) |
| `scratchpad` | Session-scoped key-value working memory |
| `send_message` | Send message to a named channel |
| `wait_channel` | Wait for a message on a named channel |
| `http` | Make HTTP requests |
| `ask_user` | Prompt the user for clarification |
| `json_read` | Read and query JSON files |
| `json_write` | Write structured JSON data |

## Architecture

```
src/kohakuterrarium/
├── core/                     # Runtime engine
│   ├── agent.py              # Main orchestrator - wires everything together
│   ├── agent_init.py         # Agent initialization logic
│   ├── agent_handlers.py     # Event handler implementations
│   ├── controller.py         # LLM conversation loop + event queue
│   ├── executor.py           # Background job runner (parallel execution)
│   ├── events.py             # Unified TriggerEvent system
│   ├── channel.py            # Async named channels for cross-agent messaging
│   ├── scratchpad.py         # Session-scoped key-value working memory
│   ├── termination.py        # Termination condition evaluation
│   ├── conversation.py       # Message history management
│   ├── config.py             # Config loading (YAML/JSON/TOML)
│   ├── loader.py             # Module dynamic loading
│   ├── job.py                # Job status tracking
│   └── registry.py           # Module registration
│
├── modules/                  # Pluggable modules (protocols)
│   ├── input/                # Input handlers (CLI, Whisper ASR, custom)
│   ├── trigger/              # Triggers (timer, channel, custom)
│   ├── tool/                 # Tool base + ToolContext (DI)
│   ├── output/               # Output routing (stdout, named outputs, custom)
│   └── subagent/             # Sub-agent lifecycle + interactive management
│
├── parsing/                  # Stream parsing
│   ├── state_machine.py      # Real-time [/tool] block detection
│   ├── patterns.py           # Pattern definitions
│   └── events.py             # ParseEvent types
│
├── builtins/                 # Built-in implementations
│   ├── tools/                # 16 tools (bash, read, write, edit, ...)
│   ├── subagents/            # 10 sub-agents (explore, plan, worker, ...)
│   ├── inputs/               # CLI, Whisper ASR
│   └── outputs/              # stdout, TTS
│
├── prompt/                   # Prompt system
│   ├── aggregator.py         # System prompt building + plugin architecture
│   └── template.py           # Jinja2 templating
│
├── llm/                      # LLM abstraction
│   ├── base.py               # Provider protocol
│   └── openai.py             # OpenAI/OpenRouter implementation
│
└── utils/                    # Utilities
    └── logging.py            # Structured colored logging
```

## Tool Call Format

KohakuTerrarium uses a bracket-based call format that works with any LLM:

```
# Simple command
[/bash]ls -la[bash/]

# Named arguments with @@
[/read]@@path=src/main.py[read/]

# Content body with arguments
[/write]
@@path=hello.py
print("Hello, World!")
[write/]

[/edit]
@@path=config.py
@@old=debug = False
@@new=debug = True
[edit/]

# Sub-agent delegation
[/explore]Find all API endpoints[explore/]

# Channel messaging
[/send_message]
@@channel=results
Analysis complete: found 12 issues
[send_message/]

# On-demand documentation
[/info]bash[info/]
```

## Event-Driven Architecture

Everything flows through `TriggerEvent`:

```python
TriggerEvent(
    type="user_input" | "tool_complete" | "subagent_output" | "timer" | "channel",
    content="...",
    context={...},
    job_id="...",
    stackable=True  # Can batch with simultaneous events
)
```

**Event Sources**:
- Input modules -> `"user_input"`
- Triggers (timers, channels) -> `"timer"`, `"channel"`, etc.
- Tool executor -> `"tool_complete"`
- Sub-agents -> `"subagent_output"`

**Flow**:
```
Event collected -> Controller batches events -> LLM responds
    -> Parser detects [/tool] calls -> Tools execute in background
    -> Results batched -> Re-injected as new event -> Repeat
```

## Key Features

### Non-Blocking Tool Execution
```python
# Tools start immediately when detected in stream
# Controller continues streaming while tools run
# All tools execute in parallel via asyncio.gather()
```

### Automatic Retry with Backoff
```python
# LLM provider retries on:
# - 5xx server errors
# - 429 rate limits
# - Connection errors (incomplete reads, timeouts)
# With exponential backoff: 1s, 2s, 4s
```

### Structured Logging
```
[14:32:05] [kohakuterrarium.core.agent] [INFO] Agent started
[14:32:06] [kohakuterrarium.llm.openai] [DEBUG] Streaming response
[14:32:07] [kohakuterrarium.core.channel] [INFO] Message sent on channel 'results'
```

### On-Demand Documentation
```
# Get full documentation for any tool or sub-agent
[/info]bash[info/]
[/info]explore[info/]
```

## Current Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Done | Core foundation (LLM, events, conversation) |
| Phase 2 | Done | Stream parsing (bracket-style tool detection) |
| Phase 3 | Done | Controller loop (multi-turn conversation) |
| Phase 4 | Done | Tool execution (background, parallel) |
| Phase 5 | Done | Agent assembly (config loading, I/O) |
| Phase 6 | Done | Sub-agents (nested agents with lifecycle) |
| Phase 7 | Done | Advanced features (triggers, channels, output routing) |
| Phase 8 | Done | Multi-agent coordination (channels, scratchpad, termination) |

## Why "Terrarium"?

A terrarium is a self-contained ecosystem -- some fully closed and autonomous, others open to interaction. KohakuTerrarium lets you build different agent "terrariums":

- **Closed**: Monitoring systems that run autonomously (no user input)
- **Open**: Coding assistants that respond to user requests
- **Hybrid**: Chat bots that both respond and initiate conversation
- **Connected**: Multi-agent swarms that communicate via channels

The name reflects the vision: build self-contained agent ecosystems, each with their own rules, tools, and behaviors -- and connect them when they need to collaborate.

## Documentation

- [CLAUDE.md](CLAUDE.md) - Code conventions and project guidelines
- [docs/architecture.md](docs/architecture.md) - Architecture overview
- [docs/api/](docs/api/) - API reference
- [docs/guides/](docs/guides/) - Usage guides

## Contributing

Contributions are welcome! Please read [CLAUDE.md](CLAUDE.md) for:
- Code conventions (imports, typing, file organization)
- Architecture guidelines (controller as orchestrator)
- Logging standards (structured, colored, no print())

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <i>Build agents that think, act, remember, and collaborate.</i>
  <br><br>
  <b>KohakuTerrarium</b> - Universal Agent Framework
</p>

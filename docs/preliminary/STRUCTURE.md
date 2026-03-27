# KohakuTerrarium Project Structure

## Directory Tree with File Descriptions

```
KohakuTerrarium/
├── src/
│   └── kohakuterrarium/
│       ├── __init__.py                 # Package root, version info, convenience imports
│       │
│       ├── core/                       # Core runtime and orchestration
│       │   ├── __init__.py             # Export core classes
│       │   ├── agent.py                # Agent class - wires all modules together, main entry point
│       │   ├── controller.py           # Controller - LLM conversation loop, event queue, orchestration
│       │   ├── conversation.py         # Conversation class - message history, context compaction
│       │   ├── executor.py             # Background job executor - runs tools/subagents async
│       │   ├── job.py                  # Job/JobStatus - tracks running tasks, status, output stats
│       │   ├── events.py               # TriggerEvent and related event types - universal message
│       │   ├── config.py               # AgentConfig - load/validate YAML/JSON/TOML configs
│       │   └── registry.py             # Module registry - decorator + config-driven registration
│       │
│       ├── modules/                    # Pluggable module implementations
│       │   ├── __init__.py             # Export base protocols
│       │   │
│       │   ├── input/                  # Input system - produces TriggerEvent(type="user_input")
│       │   │   ├── __init__.py         # Export InputModule protocol + implementations
│       │   │   ├── base.py             # InputModule protocol definition
│       │   │   ├── cli.py              # CLI/terminal input implementation
│       │   │   ├── api.py              # Webhook/REST API input
│       │   │   ├── asr.py              # ASR (speech recognition) input
│       │   │   └── discord.py          # Discord bot input
│       │   │
│       │   ├── trigger/                # Trigger system - automatic event generation
│       │   │   ├── __init__.py         # Export TriggerModule protocol + implementations
│       │   │   ├── base.py             # TriggerModule protocol definition
│       │   │   ├── timer.py            # Time-based triggers (interval, cron, idle)
│       │   │   ├── event.py            # Event-based triggers (file watch, webhooks)
│       │   │   ├── condition.py        # Condition-based triggers (internal state checks)
│       │   │   └── composite.py        # Composite triggers (AND/OR combinations)
│       │   │
│       │   ├── tool/                   # Tool system - executable functions
│       │   │   ├── __init__.py         # Export Tool protocol + implementations
│       │   │   ├── base.py             # Tool protocol, execution modes (direct/background/stateful)
│       │   │   ├── bash.py             # Bash/shell command execution
│       │   │   ├── web.py              # Web search and fetch tools
│       │   │   ├── file.py             # File read/write tools
│       │   │   └── memory.py           # Memory read/write/search tools
│       │   │
│       │   ├── output/                 # Output system - routes controller output
│       │   │   ├── __init__.py         # Export OutputModule protocol + implementations
│       │   │   ├── base.py             # OutputModule protocol definition
│       │   │   ├── router.py           # State machine router - detects patterns, routes to modules
│       │   │   ├── stdout.py           # Standard output (terminal)
│       │   │   ├── file.py             # File output (diff format with mtime guard)
│       │   │   ├── parallel.py         # ParallelOutput wrapper - fan out to multiple outputs
│       │   │   ├── tts.py              # TTS streaming output
│       │   │   └── discord.py          # Discord bot output
│       │   │
│       │   └── subagent/               # Sub-agent system - nested agents
│       │       ├── __init__.py         # Export SubAgent classes
│       │       ├── base.py             # SubAgent protocol and base class
│       │       ├── manager.py          # SubAgentManager - lifecycle, spawn, cleanup
│       │       └── protocol.py         # Parent-child communication, context updates
│       │
│       ├── parsing/                    # Stream parsing - detect tool calls in output
│       │   ├── __init__.py             # Export parser classes
│       │   ├── state_machine.py        # Core state machine for streaming parse
│       │   ├── patterns.py             # Pattern definitions (##tool##, ##subagent##, etc.)
│       │   └── events.py               # ParseEvent types (ToolCallEvent, TextEvent, etc.)
│       │
│       ├── commands/                   # Framework commands (##read##, ##info##)
│       │   ├── __init__.py             # Export command registry
│       │   ├── base.py                 # Command protocol, registration decorator
│       │   ├── read.py                 # ##read job_id## - read job output
│       │   └── info.py                 # ##info tool_name## - get tool/subagent documentation
│       │
│       ├── llm/                        # LLM abstraction layer
│       │   ├── __init__.py             # Export LLM classes
│       │   ├── base.py                 # LLMProvider protocol (OpenAI-oriented)
│       │   ├── openai.py               # OpenAI/compatible API implementation
│       │   └── message.py              # Message types (system, user, assistant)
│       │
│       ├── prompt/                     # Prompt management
│       │   ├── __init__.py             # Export prompt classes
│       │   ├── loader.py               # Load markdown files from agent folder
│       │   ├── template.py             # Jinja-like templating for prompts
│       │   └── aggregator.py           # Aggregate system prompt from config + tools + hints
│       │
│       └── utils/                      # Shared utilities
│           ├── __init__.py             # Export utilities
│           ├── async_utils.py          # Async helpers, to_thread wrappers for sync code
│           ├── logging.py              # Structured logging setup (terminal + optional file)
│           └── errors.py               # Error types, retry logic, error reporting
│
├── agents/                             # Example agent configurations
│   ├── swe_agent/                      # Claude Code-like SWE agent
│   │   ├── config.yaml                 # Agent configuration
│   │   ├── prompts/
│   │   │   ├── system.md               # Main system prompt
│   │   │   └── tools/                  # Tool documentation
│   │   └── memory/                     # First-citizen memory folder
│   │
│   ├── groupchat_agent/                # Group chat bot with memory
│   │   ├── config.yaml
│   │   ├── prompts/
│   │   └── memory/
│   │
│   └── conversation_agent/             # Neuro-sama style conversation bot
│       ├── config.yaml
│       ├── prompts/
│       └── memory/
│
├── tests/
│   ├── __init__.py
│   ├── unit/                           # Unit tests per module
│   │   ├── __init__.py
│   │   ├── test_events.py              # Test TriggerEvent
│   │   ├── test_conversation.py        # Test context management
│   │   ├── test_parsing.py             # Test state machine parser
│   │   └── test_llm.py                 # Test LLM abstraction
│   │
│   └── integration/                    # Integration tests
│       ├── __init__.py
│       ├── test_controller_loop.py     # Test full controller conversation loop
│       └── test_agent_flow.py          # Test complete agent flow
│
├── examples/                           # Example scripts for each phase
│   ├── phase1_basic_llm.py             # Phase 1: Basic LLM + streaming
│   ├── phase2_parsing.py               # Phase 2: Parse tool calls from stream
│   ├── phase3_controller.py            # Phase 3: Controller conversation loop
│   ├── phase4_tools.py                 # Phase 4: Background tool execution
│   └── phase5_full_agent.py            # Phase 5: Full agent with config
│
├── docs/
│   ├── SPECIFICATION.md                # Full framework specification
│   ├── STRUCTURE.md                    # This file - project structure
│   └── IMPLEMENTATION_PLAN.md          # Multi-phase implementation plan
│
├── ideas/
│   └── initial_discussion.md           # Original design discussion
│
├── claude.md                           # Project conventions for Claude
├── pyproject.toml                      # Project metadata and dependencies
└── README.md                           # Project readme
```

## Module Dependencies

```
                         ┌──────────────┐
                         │    config    │
                         └──────┬───────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
   ┌─────────┐            ┌──────────┐            ┌─────────┐
   │  prompt │            │   core   │            │   llm   │
   │         │───────────►│          │◄───────────│         │
   └─────────┘            │  agent   │            └─────────┘
                          │controller│
                          │ executor │
                          │   job    │
                          │  events  │
                          └────┬─────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ modules/ │    │ parsing  │    │ commands │
        │  input   │    │          │    │          │
        │ trigger  │    └────┬─────┘    └──────────┘
        │  tool    │         │
        │ subagent │         │
        └────┬─────┘         │
             │               │
             └───────┬───────┘
                     ▼
              ┌──────────┐
              │ modules/ │
              │  output  │
              │ (router) │
              └──────────┘
```

## Key File Responsibilities

| File | Primary Responsibility |
|------|----------------------|
| `core/agent.py` | Top-level orchestration, wires modules together |
| `core/controller.py` | LLM conversation loop, event queue, dispatching |
| `core/events.py` | TriggerEvent - the universal message type |
| `core/executor.py` | Background task execution for tools/subagents |
| `core/conversation.py` | Message history, context compaction, sliding window |
| `parsing/state_machine.py` | Stream parser for detecting tool/subagent calls |
| `modules/output/router.py` | Routes parsed output to appropriate output modules |
| `llm/base.py` | LLM provider protocol (OpenAI-oriented) |
| `llm/openai.py` | OpenAI API implementation with streaming |

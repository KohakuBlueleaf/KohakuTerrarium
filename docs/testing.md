# Testing Infrastructure & Behavior Documentation

## Overview

KohakuTerrarium has a two-tier test suite:
- **Unit tests** (`tests/unit/`): Component-level tests, 8 files organized by architectural phase
- **Integration tests** (`tests/integration/`): Cross-component tests for channels, output routing, and full pipeline

### Current Test Results

```
284 passed, 14 failed (pre-existing XML syntax tests)

Unit tests:      243 passed, 14 failed
Integration tests: 41 passed, 0 failed
```

The 14 failures are all in `test_phase2.py` (9) and `test_phase6.py` (5) — they test the old XML-style `<bash>` parser syntax, but the parser was rewritten to use `[/bash]...[bash/]` syntax. These tests need updating to the new format.

---

## Test Infrastructure (`src/kohakuterrarium/testing/`)

A reusable module providing fake/mock primitives for testing the agent framework without real LLMs.

### `ScriptedLLM` — Deterministic LLM Mock

Implements `LLMProvider` protocol with scripted responses.

```python
from kohakuterrarium.testing import ScriptedLLM, ScriptEntry

# Simple: list of strings
llm = ScriptedLLM(["Hello!", "I'll use a tool.", "Done."])

# Advanced: match-based entries with streaming control
llm = ScriptedLLM([
    ScriptEntry("I'll search for it.", match="find"),     # only if input contains "find"
    ScriptEntry("I don't understand."),                    # fallback
    ScriptEntry("[/bash]echo hi[bash/]", chunk_size=5),   # tool call, 5 chars/chunk
])

# After running:
assert llm.call_count == 2
assert llm.last_user_message == "find the bug"
assert len(llm.call_log) == 2  # all messages received per call
```

**Key features:**
- Accepts `list[str]` or `list[ScriptEntry]`
- Match-based entry selection (checks last user message)
- Configurable chunk size and streaming delay
- Records all received messages for assertions
- `chat_complete()` for non-streaming use

### `OutputRecorder` — Output Capture

Extends `BaseOutputModule` to capture all output.

```python
from kohakuterrarium.testing import OutputRecorder

recorder = OutputRecorder()
await recorder.write("complete text")
await recorder.write_stream("chunk1")
await recorder.write_stream("chunk2")
recorder.on_activity("tool_start", "[bash] job_123")

# Assertions
assert recorder.all_text == "chunk1chunk2complete text"
assert recorder.stream_text == "chunk1chunk2"
assert recorder.writes == ["complete text"]
assert recorder.activities[0].activity_type == "tool_start"
assert recorder.processing_starts == 0  # on_processing_start() not called

# Convenience assertions
recorder.assert_text_contains("chunk1")
recorder.assert_activity_count("tool_start", 1)
```

**Captures separately:**
- `writes` — complete `write()` calls
- `streams` — streaming `write_stream()` chunks
- `activities` — `on_activity()` notifications (activity_type + detail)
- `processing_starts` / `processing_ends` — lifecycle event counts

### `EventRecorder` — Event Flow Tracking

Records events with timing for ordering assertions.

```python
from kohakuterrarium.testing import EventRecorder

recorder = EventRecorder()
recorder.record("tool_complete", "bash result", source="tool")
recorder.record("channel_message", "hello", source="channel")

assert recorder.count == 2
assert recorder.types_in_order() == ["tool_complete", "channel_message"]
recorder.assert_order("tool_complete", "channel_message")
recorder.assert_before("tool_complete", "channel_message")
```

### `TestAgentBuilder` — Agent Assembly

Builder pattern for wiring `ScriptedLLM` + `OutputRecorder` + real `Controller` + real `Executor` into a test harness.

```python
from kohakuterrarium.testing import TestAgentBuilder

env = (
    TestAgentBuilder()
    .with_llm_script(["Hello!", "[/bash]echo hi[bash/]", "Done."])
    .with_builtin_tools(["bash", "read"])
    .with_system_prompt("You are a test agent.")
    .with_session("test_session")
    .with_named_output("discord", discord_recorder)
    .build()
)

# Simulate a user turn
await env.inject("Please help me")

# Access all components
env.llm          # ScriptedLLM
env.output       # OutputRecorder (default output)
env.controller   # real Controller
env.executor     # real Executor
env.registry     # real Registry
env.router       # real OutputRouter
env.session      # Session with channels
```

`env.inject(text)` simulates one full controller turn: push event → run LLM → parse → route to output. Tool calls are submitted to the executor. Command results are routed to activity.

---

## Unit Test Coverage by Phase

### Phase 1 (`test_phase1.py`) — Core Foundation
- **Logging**: Custom logger formatting, color codes, structured kwargs
- **TriggerEvent**: Creation, text extraction, multimodal detection, `with_context()`, event type constants, helper functions (`create_user_input_event`, `create_tool_complete_event`, `create_error_event`)
- **Message types**: Message creation, role validation, multimodal ContentParts
- **Conversation**: Append, truncation, serialization, metadata tracking

### Phase 2 (`test_phase2.py`) — Stream Parsing
- **ParseEvent types**: TextEvent, ToolCallEvent, CommandEvent dataclasses
- **Tag parsing functions**: `parse_opening_tag`, `parse_closing_tag`, `parse_attributes`
- **Extraction helpers**: `extract_tool_calls`, `extract_subagent_calls`, `extract_text`
- **StreamParser**: ⚠️ 9 tests failing — use old XML `<bash>` syntax instead of current `[/bash]` format

### Phase 3-4 (`test_phase3_4.py`) — Controller & Tool Execution
- **JobStatus/JobResult**: Creation, state transitions, preview truncation
- **JobStore**: Registration, status tracking, result storage, cleanup
- **Registry**: Tool registration, listing, prompt generation
- **BashTool**: Real execution (`echo` commands), async patterns
- **Executor**: Submit, wait, result collection, timeout handling

### Phase 5 (`test_phase5.py`) — Agent Assembly
- **Config loading**: YAML parsing, env var interpolation, default values
- **Prompt templating**: Jinja2 rendering, safe variable handling
- **Input modules**: CLIInput, NoneInput protocol compliance
- **Output modules**: StdoutOutput, PrefixedStdoutOutput
- **Agent initialization**: Full Agent.from_path() assembly

### Phase 6 (`test_phase6.py`) — Sub-Agent System
- **SubAgentConfig**: Creation, tool lists, interactive mode, context modes
- **SubAgentManager**: Registration, listing, config retrieval
- **Builtin sub-agents**: Explore, plan, memory_read, memory_write configs
- **Agent tag parsing**: ⚠️ 5 tests failing — use old XML syntax

### Phase 7 (`test_phase7.py`) — Custom Modules & Triggers
- **ModuleLoader**: Load tools/agents from Python files
- **TimerTrigger**: Interval firing, immediate mode, context updates
- **ContextUpdateTrigger**: Fire on context changes
- **Interactive sub-agents**: Context update modes (interrupt_restart, queue_append, flush_replace)
- **InteractiveOutput**: Output callback mechanism, buffer management

### Phase 8 (`test_phase8.py`) — Advanced Coverage
- **SkillDoc/frontmatter**: Parsing YAML frontmatter from skill documentation
- **SubAgent with MockLLM**: Task execution, tool calling, timeout handling
- **SubAgentJob**: Job lifecycle, status/result conversion
- **Controller**: Config, context, event pushing, run_once, tool registration
- **InteractiveSubAgent**: Lifecycle, buffered output, context formatting
- **Commands**: JobsCommand, WaitCommand (no store, no jobs, already complete)
- **Aggregator**: Dynamic/static hints, tool list building, full docs building

---

## Integration Test Coverage

### Channel Communication (`test_channels.py`) — 23 Tests

**SubAgentChannel (queue):**
- Basic send/receive with field verification (sender, content, message_id, channel)
- Single consumer semantics (message consumed after receive)
- FIFO ordering (5 messages received in send order)
- Timeout on empty channel (asyncio.TimeoutError)
- Non-blocking try_receive (returns None on empty)
- Unique message IDs (two messages get different IDs)
- Reply-to threading (reply_to field preserved through send/receive)
- Metadata preservation (dict survives roundtrip)

**AgentChannel (broadcast):**
- All subscribers receive (3 subscribers all get the same message with same message_id)
- Sender receives own message (if subscribed)
- Late subscriber misses old messages (no replay by default)
- Unsubscribe stops delivery (subscriber count drops, no more messages)
- Subscriber count tracking
- Resubscribe returns same subscription handle

**ChannelRegistry:**
- Default creation is queue type
- Explicit broadcast creation
- Existing channel ignores type parameter on second call
- List and remove operations

**ChannelTrigger:**
- Fires TriggerEvent on queue message (correct type, sender, channel, message_id in context)
- Fires on broadcast message
- Sender filtering (only fires for matching sender)
- Prompt template content substitution (`{content}` replaced)
- Subscription cleanup on stop (subscriber count → 0)

### Output Isolation (`test_output_isolation.py`) — 10 Tests

**Router State Machine:**
- Normal text → default output
- Tool block suppresses text (TOOL_BLOCK state)
- Subagent block suppresses text (SUBAGENT_BLOCK state)
- Text before/after tool block reaches output (state transitions correctly)
- Named output routes to correct module (discord recorder gets it, default doesn't)
- Unknown target falls back to default
- Completed outputs tracked for feedback
- Activity notifications don't produce write() calls

**Router Lifecycle:**
- Processing start/end notifications propagate to output modules
- Reset clears pending but preserves completed outputs; clear_all removes everything

### Full Pipeline (`test_pipeline.py`) — 8 Tests

**Basic Pipeline:**
- Simple text response reaches output through Controller → Parser → Router
- Multiple turns (inject twice, get two different responses)
- System prompt reaches LLM (verified in call_log)
- Ephemeral mode configuration

**Script Matching:**
- Sequential responses (entries used in order)
- Match-based responses (entry selected by input content)

**Named Outputs:**
- `[/output_discord]...[output_discord/]` in LLM response routes to discord recorder
- Mixed text + named output in same response (both reach correct destinations)

---

## Behavior Documentation

### Background Tool Execution

Tools have two execution modes:

**Direct (blocking)**: Agent waits for completion before next LLM turn.

```
LLM response: "I'll read the file [/read]@@path=main.py[read/]"
                                    ↓
              Tool started immediately during streaming (asyncio.create_task)
              LLM continues generating
                                    ↓
              After LLM finishes, agent waits for direct tools (asyncio.gather)
                                    ↓
              Results batched into feedback event → next LLM turn
```

**Background (non-blocking)**: Tool runs independently, status reported in subsequent turns.

```
LLM response: "[/wait_channel]@@channel=results[wait_channel/]"
                                    ↓
              Tool started as background task
              NOT waited for at end of LLM turn
                                    ↓
              Agent checks background status each loop iteration
              Reports "RUNNING" or "DONE" to LLM
                                    ↓
              LLM can use [/wait]job_id[wait/] to explicitly block
```

**Key behaviors:**
1. Tools are started **immediately when parsed** during LLM streaming, not queued until response ends
2. Multiple tools run in **parallel** via `asyncio.gather()`
3. Direct tool results are batched into a single feedback event
4. Background tools are checked each iteration; completed results reported and removed from tracking
5. The agent loop continues while any background jobs are pending
6. The `[/wait]job_id[wait/]` command blocks inline during LLM response generation

### Sub-Agent Execution

Sub-agents are always background jobs:

```
LLM response: "[/explore]find authentication code[explore/]"
                                    ↓
              SubAgentManager.spawn() → creates SubAgent with limited registry
              SubAgent gets its own Controller, Executor, Conversation
              Runs in background as asyncio.Task
                                    ↓
              Parent agent loop reports "RUNNING" status
                                    ↓
              Sub-agent completes → SubAgentResult stored
              Next iteration: parent sees "DONE" + result output
              (or LLM uses [/wait]job_id[wait/] to get result sooner)
```

**Sub-agent isolation:**
- Sub-agent has its own Registry with only the tools listed in its config
- `can_modify=False` filters out write/edit/bash tools
- Sub-agent output goes to `SubAgentResult.output` only — **never** to parent's OutputRouter
- Sub-agent has no OutputRouter at all (text collected in internal `output_parts[]`)
- Max nesting depth configurable (default 3)

**Interactive sub-agents** are different:
- Stay alive across turns via `start_interactive()` / `push_context()`
- Have `on_output` callback for streaming output to parent
- Support context update modes: interrupt_restart, queue_append, flush_replace

### Channel Communication

**SubAgentChannel (queue) behavior:**

```
Agent A:  send_message(channel="tasks", content="do X")
              ↓
          ChannelMessage placed in asyncio.Queue
              ↓
Agent B:  ChannelTrigger.wait_for_trigger() receives message (≤1s polling)
              ↓
          TriggerEvent(type=CHANNEL_MESSAGE) created
              ↓
          Agent B's _process_event() runs → LLM generates response
```

- Messages are FIFO, consumed by exactly one receiver
- If no receiver is listening, messages accumulate in queue
- Timeout: `asyncio.TimeoutError` after configured duration
- Message consumed on receive (removed from queue)

**AgentChannel (broadcast) behavior:**

```
Agent A:  send_message(channel="discussion", channel_type="broadcast", content="hello")
              ↓
          ChannelMessage copied to ALL subscriber queues
              ↓
Agent B:  ChannelTrigger (subscriber_id="agent_b") receives copy
Agent C:  ChannelTrigger (subscriber_id="agent_c") receives copy
Agent D:  ChannelTrigger (subscriber_id="agent_d") receives copy
              ↓
          Each agent processes independently (parallel TriggerEvents)
```

- Each subscriber has its own queue (independent consumption)
- Late subscribers miss messages sent before their subscription
- Unsubscribe removes the queue (cleaned up on trigger stop)
- Same message_id delivered to all subscribers (can detect duplicates)
- `filter_sender` on ChannelTrigger prevents self-triggering on own messages

**Message lifecycle:**

1. `ChannelMessage` created with auto-generated `message_id` and `timestamp`
2. `channel.send()` sets `message.channel = channel.name`
3. For queue: message placed in single queue
4. For broadcast: message copied to each subscriber's queue
5. Receiver gets message via `receive()` or trigger
6. `TriggerEvent.context` contains: `sender`, `channel`, `message_id`, `raw_content`, plus all metadata

### Output Router State Machine

The OutputRouter uses a state machine to control what reaches the output module:

```
State: NORMAL
├── TextEvent → write_stream() to default output
├── BlockStartEvent("tool") → transition to TOOL_BLOCK
├── BlockStartEvent("subagent") → transition to SUBAGENT_BLOCK
├── BlockStartEvent("output_*") → transition to OUTPUT_BLOCK
├── OutputEvent → route to named output module
└── ToolCallEvent/SubAgentCallEvent → queue for agent handler

State: TOOL_BLOCK
├── TextEvent → SUPPRESSED (unless suppress_tool_blocks=False)
└── BlockEndEvent("tool") → transition to NORMAL

State: SUBAGENT_BLOCK
├── TextEvent → SUPPRESSED (unless suppress_subagent_blocks=False)
└── BlockEndEvent("subagent") → transition to NORMAL

State: OUTPUT_BLOCK
├── TextEvent → SUPPRESSED (content comes via OutputEvent)
└── BlockEndEvent("output_*") → transition to NORMAL
```

**Named output routing:**
- `OutputEvent(target="discord", content="...")` → `named_outputs["discord"].write(content)`
- Unknown target → fallback to `default_output.write()` with `[target]` prefix
- All routed outputs tracked in `_completed_outputs` for feedback to controller

**Activity notifications** (`on_activity()`):
- Separate from text output — never produces `write()` calls
- Used for: tool_start, tool_done, tool_error, subagent_start, subagent_done, subagent_error, command_done, command_error
- TUI routes these to Status tab; other outputs can use or ignore

### Agent Processing Loop

The full event processing loop in `agent_handlers.py`:

```
Phase 1: Reset router state for new iteration
Phase 2: Run controller.run_once()
         ├── ToolCallEvent → start_tool_async() (direct or background)
         ├── SubAgentCallEvent → start_subagent_async() (always background)
         ├── CommandResultEvent → on_activity()
         └── Other → output_router.route()
Phase 3: Termination check (max_turns, keywords, duration)
Phase 4: Flush output, update job tracking
Phase 5: Collect feedback
         ├── Output feedback (what was sent to named outputs)
         ├── Direct tool results (waited for)
         └── Background job status (RUNNING or DONE)
Phase 6: Push feedback to controller → loop back to Phase 1

Exit condition: no new jobs AND no pending jobs AND no feedback
```

---

## Coverage Gaps & Needs

### Not Yet Tested

| Area | What's Missing | Priority |
|------|---------------|----------|
| **Multi-agent channel flow** | Two agents exchanging messages through channels end-to-end | High |
| **Background tool + direct tool parallel** | Background wait_channel running while direct tools complete | High |
| **Event ordering under concurrency** | Multiple events arriving simultaneously, batching behavior | Medium |
| **Agent._process_event_with_controller** | Full 6-phase loop with tool execution and feedback | Medium |
| **Termination conditions** | max_turns, keywords, idle_timeout, max_duration | Medium |
| **Conversation compaction** | Context truncation under max_context_chars / max_messages | Low |
| **Module loader** | Loading custom tools from external Python files | Low |
| **TUI output correctness** | Verify TUI only receives correct agent's output | Low |

### Pre-Existing Test Debt

14 failing tests use old XML parser syntax (`<bash>command</bash>` instead of `[/bash]command[bash/]`). These need rewriting to the current `[/tag]...[tag/]` format:
- `test_phase2.py`: 9 StreamParser tests
- `test_phase6.py`: 5 AgentTagParsing tests

### Recommended Next Tests

1. **Multi-agent pipeline test**: ScriptedLLM Agent A sends to channel → Agent B receives via trigger → Agent B processes → sends result back. Verifies the full creature-to-creature communication path.

2. **Background tool non-blocking test**: Start `wait_channel` (background) and a direct tool simultaneously. Verify direct tool results come back while background is still running.

3. **Feedback loop test**: ScriptedLLM makes tool call → tool returns result → verify result appears in next LLM call's messages → LLM responds based on result.

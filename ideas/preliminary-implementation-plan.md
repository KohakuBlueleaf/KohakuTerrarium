# KohakuTerrarium Implementation Plan

## Overview

This document outlines the multi-phase implementation plan for KohakuTerrarium. Each phase builds on the previous one and includes test/example scripts to verify functionality.

---

## Development Principles

### 1. Test Scripts in Every Phase

**Every phase MUST have test/validation/example scripts** that can be run immediately after implementation. This enables:
- Instant debugging before moving to next phase
- Prevent "bug of bug of bug" cascading problems
- Clear visibility of what's working

Scripts go in `examples/` folder:
- `phase1_basic_llm.py` - Phase 1 validation
- `phase2_parsing.py` - Phase 2 validation
- etc.

### 2. Structured Logging (No print())

**Avoid naive `print()` everywhere.** Use structured logging with:
- Custom logger based on `logging` module (NOT loguru)
- Comprehensive format: `[TIME] [MODULE] [LEVEL] message`
- Color coding for different levels (DEBUG, INFO, WARNING, ERROR)
- Easy to filter by module or level

```python
# Good - use logger
from kohakuterrarium.utils.logging import get_logger
logger = get_logger(__name__)
logger.info("Processing event", event_type=event.type)

# Bad - avoid print
print(f"Processing event {event.type}")  # Don't do this
```

**Exception**: Test suites (`tests/`) can use simpler output for pytest compatibility.

### 3. Validate Before Proceeding

Before moving to Phase N+1:
1. Run Phase N test script
2. All assertions pass
3. Manual inspection of output looks correct

---

## Phase 1: Core Foundation (LLM + Events + Conversation + Logging)

**Goal**: Basic LLM streaming + event types + conversation management + structured logging

### Files to Implement

| File | Description |
|------|-------------|
| `utils/logging.py` | Custom logger with colors, comprehensive format |
| `core/events.py` | TriggerEvent dataclass and event types |
| `llm/message.py` | Message types (system, user, assistant) |
| `llm/base.py` | LLMProvider protocol |
| `llm/openai.py` | OpenAI implementation with streaming |
| `core/conversation.py` | Conversation class with message management |
| `utils/async_utils.py` | Basic async utilities |

### Key Interfaces

```python
# utils/logging.py
def get_logger(name: str) -> Logger:
    """Get a colored, formatted logger for a module."""
    ...

# Format: [HH:MM:SS] [module.name] [LEVEL] message
# Colors: DEBUG=gray, INFO=green, WARNING=yellow, ERROR=red

# core/events.py
@dataclass
class TriggerEvent:
    type: str
    content: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    job_id: str | None = None
    prompt_override: str | None = None
    stackable: bool = True

# llm/base.py
class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[Message],
        *,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        ...

# core/conversation.py
class Conversation:
    def append(self, role: str, content: str) -> None: ...
    def to_messages(self) -> list[Message]: ...
    def get_context_length(self) -> int: ...
```

### Test Script: `examples/phase1_basic_llm.py`

```python
"""
Phase 1 Test: Basic LLM streaming with conversation

Run: python examples/phase1_basic_llm.py

Expected:
- Connect to OpenAI API
- Send a simple message
- Stream response tokens to terminal
- Verify conversation history works
"""
import asyncio
import os

from kohakuterrarium.llm.openai import OpenAIProvider
from kohakuterrarium.core.conversation import Conversation
from kohakuterrarium.core.events import TriggerEvent


async def main():
    # Setup
    provider = OpenAIProvider(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-4o-mini",  # Use cheap model for testing
    )
    conv = Conversation()

    # Add system message
    conv.append("system", "You are a helpful assistant. Keep responses brief.")

    # Simulate user input as TriggerEvent
    event = TriggerEvent(type="user_input", content="Hello! What is 2+2?")
    conv.append("user", event.content)

    # Stream response
    print("Assistant: ", end="", flush=True)
    full_response = ""
    async for chunk in provider.chat(conv.to_messages(), stream=True):
        print(chunk, end="", flush=True)
        full_response += chunk
    print()  # newline

    # Add to conversation
    conv.append("assistant", full_response)

    # Verify conversation has 3 messages
    messages = conv.to_messages()
    assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"
    print(f"\n✓ Conversation has {len(messages)} messages")
    print(f"✓ Context length: {conv.get_context_length()} chars")


if __name__ == "__main__":
    asyncio.run(main())
```

### Success Criteria

- [ ] Logger produces colored, formatted output
- [ ] TriggerEvent can be created with all fields
- [ ] OpenAI streaming works with async iterator
- [ ] Conversation tracks messages correctly
- [ ] Can serialize conversation to message list
- [ ] All output uses logger (no raw print in library code)

---

## Phase 2: Stream Parsing

**Goal**: Parse tool calls from streaming LLM output

### Files to Implement

| File | Description |
|------|-------------|
| `parsing/events.py` | ParseEvent types (TextEvent, ToolCallEvent, etc.) |
| `parsing/patterns.py` | Pattern definitions, configurable formats |
| `parsing/state_machine.py` | Core streaming state machine parser |

### Key Interfaces

```python
# parsing/events.py
@dataclass
class TextEvent:
    text: str

@dataclass
class ToolCallEvent:
    name: str
    args: dict[str, Any]
    raw: str

@dataclass
class SubAgentCallEvent:
    name: str
    args: dict[str, Any]
    raw: str

ParseEvent = TextEvent | ToolCallEvent | SubAgentCallEvent | CommandEvent

# parsing/state_machine.py
class StreamParser:
    def __init__(self, config: ParserConfig): ...
    def feed(self, chunk: str) -> list[ParseEvent]: ...
    def flush(self) -> list[ParseEvent]: ...
```

### Test Script: `examples/phase2_parsing.py`

```python
"""
Phase 2 Test: Stream parsing for tool calls

Run: python examples/phase2_parsing.py

Expected:
- Parser detects ##tool## blocks while streaming
- Text outside blocks emitted as TextEvent
- Complete tool blocks emitted as ToolCallEvent
- Handles partial chunks correctly
"""
import asyncio

from kohakuterrarium.parsing.state_machine import StreamParser
from kohakuterrarium.parsing.patterns import ParserConfig
from kohakuterrarium.parsing.events import TextEvent, ToolCallEvent


def test_basic_parsing():
    """Test parsing a complete response with tool call."""
    config = ParserConfig()  # Default ##tool## format
    parser = StreamParser(config)

    # Simulate streaming chunks
    chunks = [
        "Let me check ",
        "that for you.\n\n",
        "##tool##\n",
        "name: bash\n",
        "args:\n",
        "  command: ls -la\n",
        "##tool##\n\n",
        "I'll run that command.",
    ]

    all_events = []
    for chunk in chunks:
        events = parser.feed(chunk)
        all_events.extend(events)
    all_events.extend(parser.flush())

    # Verify events
    text_events = [e for e in all_events if isinstance(e, TextEvent)]
    tool_events = [e for e in all_events if isinstance(e, ToolCallEvent)]

    assert len(tool_events) == 1, f"Expected 1 tool call, got {len(tool_events)}"
    assert tool_events[0].name == "bash"
    assert tool_events[0].args["command"] == "ls -la"

    print("✓ Detected tool call: bash")
    print(f"✓ Text events: {len(text_events)}")
    print(f"✓ Tool events: {len(tool_events)}")


def test_partial_chunks():
    """Test that partial tool markers are handled correctly."""
    config = ParserConfig()
    parser = StreamParser(config)

    # Split marker across chunks
    chunks = ["Some text #", "#too", "l##\nname: test\n##tool##"]

    all_events = []
    for chunk in chunks:
        events = parser.feed(chunk)
        all_events.extend(events)
    all_events.extend(parser.flush())

    tool_events = [e for e in all_events if isinstance(e, ToolCallEvent)]
    assert len(tool_events) == 1
    print("✓ Handles split markers correctly")


def test_multiple_tools():
    """Test multiple tool calls in one response."""
    config = ParserConfig()
    parser = StreamParser(config)

    response = """I'll search and then fetch.

##tool##
name: web_search
args:
  query: python async
##tool##

##tool##
name: web_fetch
args:
  url: https://example.com
##tool##

Done!"""

    events = parser.feed(response)
    events.extend(parser.flush())

    tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(tool_events) == 2
    print(f"✓ Detected {len(tool_events)} tool calls")


if __name__ == "__main__":
    test_basic_parsing()
    test_partial_chunks()
    test_multiple_tools()
    print("\n✓ All parsing tests passed!")
```

### Success Criteria

- [ ] State machine correctly identifies tool block start/end
- [ ] Partial chunks don't break parsing
- [ ] Multiple tool calls detected in single response
- [ ] Text between tool calls preserved

---

## Phase 3: Controller Loop

**Goal**: Controller conversation loop with event queue and context management

### Files to Implement

| File | Description |
|------|-------------|
| `core/job.py` | Job and JobStatus for tracking background tasks |
| `core/controller.py` | Controller class with event queue and LLM loop |
| `commands/base.py` | Command protocol and registry |
| `commands/read.py` | ##read job_id## command |

### Key Interfaces

```python
# core/job.py
@dataclass
class JobStatus:
    job_id: str
    job_type: str  # "tool" or "subagent"
    name: str
    status: str  # "running", "done", "error"
    start_time: datetime
    output_lines: int = 0
    output_bytes: int = 0
    preview: str = ""

# core/controller.py
class Controller:
    def __init__(self, llm: LLMProvider, config: ControllerConfig): ...
    async def push_event(self, event: TriggerEvent) -> None: ...
    async def run_once(self) -> AsyncIterator[ParseEvent]: ...
    def get_job_status(self, job_id: str) -> JobStatus | None: ...
    def register_job(self, job: JobStatus) -> None: ...
```

### Test Script: `examples/phase3_controller.py`

```python
"""
Phase 3 Test: Controller conversation loop

Run: python examples/phase3_controller.py

Expected:
- Controller receives TriggerEvent
- Batches stackable events
- Runs LLM and parses output
- Tracks jobs (dummy jobs for now)
- Handles ##read## command
"""
import asyncio
import os

from kohakuterrarium.llm.openai import OpenAIProvider
from kohakuterrarium.core.controller import Controller, ControllerConfig
from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.core.job import JobStatus
from kohakuterrarium.parsing.events import TextEvent, ToolCallEvent


async def main():
    # Setup
    llm = OpenAIProvider(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )
    config = ControllerConfig(
        system_prompt="""You are a test assistant.
When asked to run a command, output it in this format:
##tool##
name: bash
args:
  command: <the command>
##tool##

Keep responses brief."""
    )
    controller = Controller(llm, config)

    # Register a dummy completed job
    dummy_job = JobStatus(
        job_id="test_123",
        job_type="tool",
        name="bash",
        status="done",
        start_time=datetime.now(),
        output_lines=3,
        output_bytes=50,
        preview="file1.txt\nfile2.txt\nfile3.txt",
    )
    controller.register_job(dummy_job)

    # Test 1: Basic conversation
    print("=== Test 1: Basic conversation ===")
    event = TriggerEvent(type="user_input", content="Please run 'ls' command")
    await controller.push_event(event)

    tool_detected = False
    async for parse_event in controller.run_once():
        if isinstance(parse_event, TextEvent):
            print(parse_event.text, end="", flush=True)
        elif isinstance(parse_event, ToolCallEvent):
            print(f"\n[TOOL CALL: {parse_event.name}]")
            tool_detected = True
    print()

    assert tool_detected, "Expected tool call to be detected"
    print("✓ Tool call detected in response\n")

    # Test 2: Read command
    print("=== Test 2: Job status in context ===")
    event = TriggerEvent(
        type="user_input",
        content="What jobs are running? (hint: check test_123)"
    )
    await controller.push_event(event)

    async for parse_event in controller.run_once():
        if isinstance(parse_event, TextEvent):
            print(parse_event.text, end="", flush=True)
    print()

    print("\n✓ Controller loop working!")


if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(main())
```

### Success Criteria

- [ ] Controller maintains conversation state
- [ ] Events queued and batched correctly
- [ ] LLM output parsed in real-time
- [ ] Job status tracked and accessible
- [ ] Context includes job status information

---

## Phase 4: Tool Execution

**Goal**: Background tool execution with real bash commands

### Files to Implement

| File | Description |
|------|-------------|
| `core/executor.py` | Background executor for tools |
| `modules/tool/base.py` | Tool protocol |
| `modules/tool/bash.py` | Bash command tool |
| `core/registry.py` | Tool registration |

### Key Interfaces

```python
# modules/tool/base.py
class Tool(Protocol):
    name: str
    execution_mode: str  # "direct", "background", "stateful"

    async def execute(self, args: dict[str, Any]) -> str: ...

# core/executor.py
class Executor:
    async def submit(self, tool: Tool, args: dict, job_id: str) -> None: ...
    async def get_result(self, job_id: str, timeout: float = None) -> str | None: ...
    def get_status(self, job_id: str) -> JobStatus: ...
```

### Test Script: `examples/phase4_tools.py`

```python
"""
Phase 4 Test: Background tool execution

Run: python examples/phase4_tools.py

Expected:
- Tool calls from parser trigger executor
- Bash commands run in background
- Results returned via TriggerEvent
- Controller receives tool completion
"""
import asyncio
import os

from kohakuterrarium.llm.openai import OpenAIProvider
from kohakuterrarium.core.controller import Controller, ControllerConfig
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.modules.tool.bash import BashTool
from kohakuterrarium.parsing.events import TextEvent, ToolCallEvent


async def main():
    # Setup
    llm = OpenAIProvider(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )
    executor = Executor()
    executor.register_tool(BashTool())

    config = ControllerConfig(
        system_prompt="""You are a coding assistant.
When you need to run a command, use:
##tool##
name: bash
args:
  command: <command here>
##tool##

After running commands, summarize what you found."""
    )
    controller = Controller(llm, config, executor=executor)

    # User request
    print("=== Running tool execution test ===\n")
    event = TriggerEvent(
        type="user_input",
        content="List the files in the current directory"
    )
    await controller.push_event(event)

    # First run - should output tool call
    print("Controller output:")
    tool_call = None
    async for parse_event in controller.run_once():
        if isinstance(parse_event, TextEvent):
            print(parse_event.text, end="", flush=True)
        elif isinstance(parse_event, ToolCallEvent):
            print(f"\n[Detected tool: {parse_event.name}]")
            tool_call = parse_event
    print()

    if tool_call:
        # Execute tool in background
        job_id = await executor.submit_from_event(tool_call)
        print(f"[Submitted job: {job_id}]")

        # Wait for completion
        result = await executor.wait_for(job_id, timeout=10.0)
        print(f"[Tool output: {len(result)} chars]")

        # Push completion event
        completion = TriggerEvent(
            type="tool_complete",
            job_id=job_id,
            content=result[:500],  # Truncate for context
        )
        await controller.push_event(completion)

        # Second run - controller sees result
        print("\nController with result:")
        async for parse_event in controller.run_once():
            if isinstance(parse_event, TextEvent):
                print(parse_event.text, end="", flush=True)
        print()

    print("\n✓ Tool execution flow working!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Success Criteria

- [ ] Tools registered and discoverable
- [ ] Bash tool executes commands safely
- [ ] Executor runs tools in background
- [ ] Completion triggers controller continuation
- [ ] Job output accessible via ##read##

---

## Phase 5: Full Agent Assembly

**Goal**: Complete agent with config loading, input module, output routing

### Files to Implement

| File | Description |
|------|-------------|
| `core/config.py` | Load agent config from YAML |
| `core/agent.py` | Agent class wiring everything |
| `modules/input/base.py` | Input protocol |
| `modules/input/cli.py` | CLI input |
| `modules/output/base.py` | Output protocol |
| `modules/output/stdout.py` | Stdout output |
| `modules/output/router.py` | Output router |
| `prompt/loader.py` | Load prompts from files |
| `prompt/aggregator.py` | Build system prompt |

### Test Script: `examples/phase5_full_agent.py`

```python
"""
Phase 5 Test: Full agent from config

Run: python examples/phase5_full_agent.py agents/swe_agent

Expected:
- Load agent from config folder
- CLI input working
- Controller orchestrates
- Tools execute
- Output routed correctly
"""
import asyncio
import sys

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import load_agent_config


async def main():
    if len(sys.argv) < 2:
        print("Usage: python phase5_full_agent.py <agent_folder>")
        sys.exit(1)

    agent_path = sys.argv[1]
    print(f"Loading agent from: {agent_path}")

    # Load config
    config = load_agent_config(agent_path)
    print(f"✓ Loaded config: {config.name}")

    # Create agent
    agent = Agent(config)
    print(f"✓ Agent created with {len(config.tools)} tools")

    # Run agent
    print("\n=== Starting Agent (Ctrl+C to exit) ===\n")
    try:
        await agent.run()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await agent.shutdown()

    print("✓ Agent terminated cleanly")


if __name__ == "__main__":
    asyncio.run(main())
```

### Success Criteria

- [ ] Config loads from YAML + MD files
- [ ] Agent initializes all modules
- [ ] Input → Controller → Output flow works
- [ ] Tools execute and results return
- [ ] Clean shutdown

---

## Phase 6: Sub-Agents

**Goal**: Nested sub-agents with parent-child communication

### Files to Implement

| File | Description |
|------|-------------|
| `modules/subagent/base.py` | SubAgent class |
| `modules/subagent/manager.py` | Lifecycle management |
| `modules/subagent/protocol.py` | Parent-child protocol |

### Test Focus

- Sub-agent spawned from controller
- Sub-agent runs with own context
- Results returned to parent
- Interactive sub-agent receives updates

---

## Phase 7: Advanced Features

**Goal**: Output sub-agents, triggers, memory tools

### Files to Implement

- `modules/trigger/timer.py` - Timer triggers
- `modules/output/parallel.py` - Parallel output
- `modules/tool/memory.py` - Memory tools
- Output sub-agent pattern

---

## Phase 8: Example Agents

**Goal**: Complete example agents

### Agents to Build

1. **SWE Agent** - Full Claude Code-like agent
2. **Group Chat Agent** - Discord bot with memory
3. **Conversation Agent** - Streaming TTS bot

---

## Quick Reference: What to Build First

For Phase 1 (after /compact):

```
src/kohakuterrarium/
├── core/
│   ├── events.py        ← TriggerEvent
│   └── conversation.py  ← Conversation class
├── llm/
│   ├── message.py       ← Message types
│   ├── base.py          ← LLMProvider protocol
│   └── openai.py        ← OpenAI implementation
└── utils/
    └── async_utils.py   ← Basic helpers
```

Then run: `python examples/phase1_basic_llm.py`

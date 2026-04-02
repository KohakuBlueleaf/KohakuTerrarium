# Getting Started

This guide walks you through setting up KohakuTerrarium and creating your first agent.

## Installation

### Prerequisites

- Python 3.10 or higher
- An LLM provider: ChatGPT subscription (via Codex OAuth), OpenRouter, OpenAI, or any OpenAI-compatible API

### Install from Source

```bash
git clone https://github.com/Kohaku-Lab/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e .
```

### Authentication

**Option A: Codex OAuth (recommended, uses ChatGPT Plus/Pro subscription)**

```bash
kt login codex
```

This opens a browser for ChatGPT OAuth. No API key needed after login.

**Option B: API key**

```bash
# For OpenRouter (model variety)
export OPENROUTER_API_KEY="sk-or-..."

# For OpenAI direct
export OPENAI_API_KEY="sk-..."
```

## Running an Example Agent

The fastest way to get started is running one of the included example agents:

```bash
# Authenticate (if using ChatGPT subscription)
kt login codex

# Run the SWE agent (coding assistant, CLI input)
kt run examples/agent-apps/swe_agent

# Run with TUI for a richer terminal experience
kt run examples/agent-apps/swe_agent_tui

# Run with session recording (saves to .kohakutr file)
kt run examples/agent-apps/swe_agent --session

# Resume a previous session
kt resume .kohaku/sessions/swe_agent_*.kohakutr
```

You'll see output like:
```
[12:00:00] [agent] [INFO] Loading agent from examples/agent-apps/swe_agent
[12:00:00] [agent] [INFO] Agent started
>
```

Type a request at the prompt:
```
> List the files in the current directory
```

## Creating Your First Agent

Let's create a simple coding assistant from scratch.

### 1. Create Agent Folder Structure

```bash
mkdir -p examples/agent-apps/my_agent/prompts
mkdir -p examples/agent-apps/my_agent/memory
```

### 2. Create Configuration File

Create `examples/agent-apps/my_agent/config.yaml`:

```yaml
name: my_agent
version: "1.0"

# LLM Configuration (Codex OAuth - uses ChatGPT subscription)
controller:
  model: gpt-5.4
  auth_mode: codex-oauth
  tool_format: native

# System prompt file
system_prompt_file: prompts/system.md

# Input - CLI prompts (options: cli, tui, whisper, none, custom)
input:
  type: cli
  prompt: "> "

# Output - stdout (options: stdout, tui, tts, custom)
output:
  type: stdout

# Available tools
tools:
  - name: bash
    type: builtin
  - name: read
    type: builtin
  - name: write
    type: builtin
  - name: glob
    type: builtin
  - name: grep
    type: builtin
```

### 3. Create System Prompt

Create `examples/agent-apps/my_agent/prompts/system.md`:

```markdown
# My Coding Assistant

You are a helpful coding assistant. You help users with:
- Reading and understanding code
- Finding files and patterns
- Running commands
- Writing and editing files

## Guidelines

1. Always search before editing - understand the codebase first
2. Explain what you're doing before using tools
3. Verify changes after making them
4. Keep responses concise and focused
```

### 4. Run Your Agent

```bash
kt run examples/agent-apps/my_agent
```

## Understanding Tool Calls

When the agent needs to use a tool, it outputs a special format. See [Tool Formats](../concept/tool-formats.md) for all supported formats. The default bracket format:

```
[/tool_name]
@@arg=value
content here
[tool_name/]
```

For example, to read a file:
```
[/read]@@path=src/main.py[read/]
```

To run a command:
```
[/bash]ls -la[bash/]
```

## Framework Commands

The agent can use special commands for framework interaction:

### `[/info]` - Get Tool Documentation
```
[/info]bash[info/]
```
Returns full documentation for the bash tool.

### `[/jobs]` - List Running Jobs
```
[/jobs][jobs/]
```
Shows all running background jobs.

### `[/wait]` - Wait for Job Completion
```
[/wait]agent_explore_abc123[wait/]
```
Blocks until the specified job completes.

## Adding Sub-Agents

Sub-agents are specialized nested agents. Add them to your config:

```yaml
subagents:
  - name: explore
    type: builtin

  - name: plan
    type: builtin
```

The agent can now call:
```
[/explore]find authentication code[explore/]
```

Sub-agents run in the background. Use `[/wait]` to get results:
```
[/wait]agent_explore_abc123[wait/]
```

## Adding Memory

Create a memory folder with context files:

```yaml
memory:
  path: ./memory
  init_files:
    - character.md    # Read-only
  writable_files:
    - context.md      # Read-write
    - notes.md        # Read-write
```

Use builtin memory sub-agents:
```yaml
subagents:
  - name: memory_read
    type: builtin
  - name: memory_write
    type: builtin
```

## Adding Triggers

Triggers enable autonomous behavior. Example idle trigger:

```yaml
triggers:
  - type: custom
    module: ./custom/idle_trigger.py
    class: IdleTrigger
    min_idle_seconds: 300     # 5 minutes
    prompt: "Check if there's anything to follow up on."
```

## Trigger-Only Agents (No User Input)

For agents driven entirely by triggers (timers, channel events), use `none` input:

```yaml
input:
  type: none    # NoneInput - blocks forever, never produces input events

triggers:
  - type: timer
    interval: 60
    prompt: "Run health check."
```

## Named Outputs

Route output to specific destinations:

```yaml
output:
  type: stdout

  named_outputs:
    discord:
      type: custom
      module: ./custom/discord_output.py
      class: DiscordOutput
```

The model uses explicit output blocks:
```
[/output_discord]Hello everyone![output_discord/]
```

Without the wrapper, text goes to stdout (internal thinking).

## Custom Tools

Create a custom tool in `examples/agent-apps/my_agent/custom/my_tool.py`:

```python
from kohakuterrarium.modules.tool.base import BaseTool, ToolResult, ExecutionMode

class MyTool(BaseTool):
    @property
    def tool_name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something useful"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.BACKGROUND

    async def _execute(self, args: dict) -> ToolResult:
        content = args.get("content", "")
        return ToolResult(output=f"Processed: {content}")
```

Register in config:
```yaml
tools:
  - name: my_tool
    type: custom
    module: ./custom/my_tool.py
    class: MyTool
```

## Programmatic Usage

```python
import asyncio
from kohakuterrarium.core.agent import Agent

async def main():
    agent = Agent.from_path("examples/agent-apps/my_agent")
    await agent.start()

    try:
        await agent.inject_input("Hello, what can you do?")
        # Or run the full event loop
        await agent.run()
    finally:
        await agent.stop()

asyncio.run(main())
```

## Running a Terrarium

To run a multi-agent terrarium:

```bash
# Run with a root agent (user talks to root, root orchestrates the team)
kt terrarium run terrariums/swe_team/

# Run with session recording
kt terrarium run terrariums/swe_team/ --session

# Run with channel observation (specific channels)
kt terrarium run examples/terrariums/novel_terrarium/ --observe ideas outline
```

See [Terrarium](../concept/terrarium.md) for the concepts and [Configuration Reference](configuration.md) for the terrarium YAML format.

## Session Persistence and Resume

Every session can be saved to a `.kohakutr` file (SQLite via KohakuVault) and resumed later.

```bash
# Start with session recording
kt run examples/agent-apps/swe_agent --session

# Resume right where you left off
kt resume .kohaku/sessions/swe_agent_*.kohakutr

# Inspect a session
python scripts/inspect_session.py session.kohakutr --all
python scripts/inspect_session.py session.kohakutr --search "auth bug"
```

What gets saved: conversation history (with full tool_calls metadata), event log, scratchpad state, token usage, sub-agent conversations, channel messages.

## Web Dashboard

A Vue 3 web frontend for managing agents and terrariums in real-time.

```bash
# Start API server
cd KohakuTerrarium && python -m apps.api.main

# Start frontend dev server
cd apps/web && npm install && npm run dev
```

Features: terrarium topology graph, multi-tab chat (root + creatures + channels), real-time streaming, sub-agent tool activity, channel message feed, token usage tracking, dark/light mode with gemstone color theme.

## Next Steps

1. Explore the [Example Agents](example-agents.md) for more patterns
2. Read the [Configuration Reference](configuration.md) for all options
3. Check the [Architecture Overview](../architecture/README.md) to understand the system
4. See the [Python API Reference](../api-reference/python.md) for detailed APIs

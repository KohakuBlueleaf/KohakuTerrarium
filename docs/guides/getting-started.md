# Getting Started

This guide walks you through setting up KohakuTerrarium and creating your first agent.

## Installation

### Prerequisites

- Python 3.10 or higher
- An LLM API key (OpenAI, OpenRouter, or compatible service)

### Install from Source

```bash
# Clone the repository
git clone https://github.com/your-org/kohakuterrarium.git
cd kohakuterrarium

# Install in editable mode (recommended for development)
uv pip install -e .
# or
pip install -e .
```

### Set Environment Variables

```bash
# For OpenRouter (recommended for model variety)
export OPENROUTER_API_KEY="sk-or-..."

# For OpenAI
export OPENAI_API_KEY="sk-..."
```

## Running an Example Agent

The fastest way to get started is running one of the included example agents:

```bash
# Run the SWE agent (coding assistant)
python -m kohakuterrarium.run agents/swe_agent
```

You'll see output like:
```
[12:00:00] [agent] [INFO] Loading agent from agents/swe_agent
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
mkdir -p agents/my_agent/prompts
mkdir -p agents/my_agent/memory
```

### 2. Create Configuration File

Create `agents/my_agent/config.yaml`:

```yaml
name: my_agent
version: "1.0"

# LLM Configuration
controller:
  model: "gpt-4o-mini"           # or "anthropic/claude-3-haiku" for OpenRouter
  temperature: 0.7
  max_tokens: 4096
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1

# System prompt file
system_prompt_file: prompts/system.md

# Input - CLI prompts
input:
  type: cli
  prompt: "> "

# Output - stdout
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

Create `agents/my_agent/prompts/system.md`:

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
python -m kohakuterrarium.run agents/my_agent
```

## Understanding Tool Calls

When the agent needs to use a tool, it outputs a special format:

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

Create `agents/my_agent/memory/context.md`:
```markdown
# Current Context

No context saved yet.
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

## Ephemeral Mode

For group chats where each interaction should be independent:

```yaml
controller:
  ephemeral: true    # Clear conversation after each interaction
```

## Custom Tools

Create a custom tool in `agents/my_agent/custom/my_tool.py`:

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
        # Do something with content
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

## Custom Input Module

Create `agents/my_agent/custom/my_input.py`:

```python
from kohakuterrarium.modules.input.base import BaseInputModule
from kohakuterrarium.core.events import TriggerEvent, EventType

class MyInput(BaseInputModule):
    async def get_input(self) -> TriggerEvent | None:
        # Get input from your source
        text = await get_from_somewhere()

        return TriggerEvent(
            type=EventType.USER_INPUT,
            content=text,
            context={"source": "my_source"},
        )
```

## Programmatic Usage

You can also use the framework programmatically:

```python
import asyncio
from kohakuterrarium.core.agent import Agent

async def main():
    # Load agent
    agent = Agent.from_path("agents/my_agent")

    # Start all modules
    await agent.start()

    try:
        # Inject an input event
        await agent.inject_input("Hello, what can you do?")

        # Or run the full event loop
        await agent.run()

    finally:
        await agent.stop()

asyncio.run(main())
```

## Next Steps

1. Explore the [Example Agents](example-agents.md) for more patterns
2. Read the [Configuration Reference](configuration.md) for all options
3. Check the [Architecture Overview](../architecture.md) to understand the system
4. See the [API Reference](../api/core.md) for detailed APIs

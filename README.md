# KohakuTerrarium

**A universal agent framework for building fully autonomous systems.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)

---

KohakuTerrarium is a Python framework for building any kind of agent -- coding assistants, conversational AI, monitoring drones, multi-agent swarms. Define your agent in YAML, pick tools and sub-agents, and let the framework handle orchestration, streaming, and coordination.

## Key Features

- **Any agent type** -- SWE agents, chatbots, autonomous monitors, multi-agent coordinators
- **Async-first execution** -- tools start during LLM streaming, run in parallel via `asyncio`
- **Nested sub-agents** -- full agents with their own LLM, tools, and lifecycle
- **Channel-based coordination** -- async named message queues for cross-agent communication
- **YAML-driven config** -- define agents declaratively, minimal code required
- **16 built-in tools** -- bash, read, write, edit, glob, grep, http, think, scratchpad, and more
- **10 built-in sub-agents** -- explore, plan, worker, critic, summarize, research, coordinator, and more
- **Trigger system** -- timers, channel events for autonomous operation
- **On-demand docs** -- tool documentation loaded only when the LLM requests it

## Quick Start

### CLI

```bash
git clone https://github.com/KohakuBlueLeaf/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e .

export OPENROUTER_API_KEY=your_key_here

# Run the SWE agent
python -m kohakuterrarium.run agents/swe_agent

# Run the planner agent
python -m kohakuterrarium.run agents/planner_agent
```

### Programmatic Usage

```python
import asyncio
from kohakuterrarium.core.agent import Agent

async def main():
    agent = Agent.from_path("agents/swe_agent")
    await agent.run()  # Interactive CLI loop

asyncio.run(main())
```

### Inject Input Programmatically

```python
async def main():
    agent = Agent.from_path("agents/swe_agent")
    await agent.start()

    # Send input without CLI
    await agent.inject_input("Create a hello world script")

    # Check state
    print(agent.tools)       # ['bash', 'read', 'write', ...]
    print(agent.subagents)   # ['explore', 'plan', 'worker', ...]

    await agent.stop()
```

### Custom Output Handler

```python
async def main():
    agent = Agent.from_path("agents/swe_agent")

    # Capture output with a callback
    agent.set_output_handler(lambda text: print(f"AI: {text}"))

    await agent.start()
    await agent.inject_input("What files are in src/?")
    await agent.stop()
```

### Wrap with FastAPI

```python
from fastapi import FastAPI, WebSocket
from kohakuterrarium.core.agent import Agent

app = FastAPI()
agents: dict[str, Agent] = {}

@app.post("/agents")
async def create_agent(config_path: str = "agents/swe_agent"):
    agent = Agent.from_path(config_path)
    await agent.start()
    agents[agent.config.name] = agent
    return {"name": agent.config.name, "tools": agent.tools}

@app.websocket("/agents/{name}/chat")
async def chat(websocket: WebSocket, name: str):
    await websocket.accept()
    agent = agents[name]

    # Capture streaming output
    agent.set_output_handler(
        lambda text: asyncio.ensure_future(websocket.send_text(text))
    )

    while True:
        user_input = await websocket.receive_text()
        await agent.inject_input(user_input)

@app.on_event("shutdown")
async def shutdown():
    for agent in agents.values():
        await agent.stop()
```

### Build Agent from Dict (No YAML File)

```python
from kohakuterrarium.core.config import AgentConfig, ToolConfigItem, SubAgentConfigItem
from kohakuterrarium.core.agent import Agent

config = AgentConfig(
    name="my_agent",
    model="google/gemini-3-flash-preview",
    api_key_env="OPENROUTER_API_KEY",
    base_url="https://openrouter.ai/api/v1",
    system_prompt="You are a helpful coding assistant.",
    tools=[
        ToolConfigItem(name="bash"),
        ToolConfigItem(name="read"),
        ToolConfigItem(name="write"),
        ToolConfigItem(name="think"),
    ],
    subagents=[
        SubAgentConfigItem(name="explore"),
        SubAgentConfigItem(name="worker"),
    ],
)

async def main():
    agent = Agent(config)
    await agent.run()
```

## How It Works

```
Input ──────┐
            +----> Controller (LLM) <----> Tools (parallel, non-blocking)
Trigger ────┘           |            <----> Sub-Agents (nested LLMs)
                        |
                  +-----+------+
                  |            |
               Output      Channels ----> Other Agents
```

| System | Role |
|--------|------|
| **Input** | User requests, chat messages, ASR streams |
| **Trigger** | Timers, channel events -- for autonomous operation |
| **Controller** | LLM orchestrator -- dispatches tasks, makes decisions |
| **Tool Calling** | Background parallel execution of tools and sub-agents |
| **Output** | Streaming to stdout, files, TTS, APIs, webhooks |

The controller dispatches, not executes. Long outputs come from sub-agents. This keeps the controller lightweight and context small.

## Built-in Tools (16)

| Tool | Description | Tool | Description |
|------|-------------|------|-------------|
| `bash` | Execute shell commands | `think` | Extended reasoning step |
| `python` | Run Python scripts | `scratchpad` | Session key-value memory |
| `read` | Read file contents | `send_message` | Send to named channel |
| `write` | Create/overwrite files | `wait_channel` | Wait for channel message |
| `edit` | Search-replace in files | `http` | Make HTTP requests |
| `glob` | Find files by pattern | `ask_user` | Prompt user for input |
| `grep` | Regex search in files | `json_read` | Query JSON files |
| `tree` | Directory structure | `json_write` | Modify JSON files |

## Built-in Sub-Agents (10)

| Sub-Agent | Purpose | Sub-Agent | Purpose |
|-----------|---------|-----------|---------|
| `explore` | Search codebase (read-only) | `coordinator` | Multi-agent via channels |
| `plan` | Create implementation plans | `memory_read` | Retrieve from memory |
| `worker` | Implement changes (read-write) | `memory_write` | Store to memory |
| `critic` | Review and critique | `response` | Generate user responses |
| `summarize` | Condense long content | `research` | Web + file research |

## Example Agents

7 example agents included. See [agents/README.md](agents/README.md) for details.

| Agent | Pattern | Key Feature |
|-------|---------|-------------|
| [swe_agent](agents/swe_agent/) | SWE coding assistant | think + scratchpad + worker/critic |
| [multi_agent](agents/multi_agent/) | Multi-agent coordination | Parallel sub-agent dispatch |
| [planner_agent](agents/planner_agent/) | Plan-execute-reflect loop | Scratchpad-driven planning |
| [monitor_agent](agents/monitor_agent/) | Trigger-driven autonomous | Timer + channel triggers, no input |
| [conversational](agents/conversational/) | Streaming ASR/TTS chat | Interactive output sub-agent |
| [discord_bot](agents/discord_bot/) | Group chat bot | Custom I/O, ephemeral mode |
| [rp_agent](agents/rp_agent/) | Character roleplay | Memory-first personality |

## Configuration

Minimal agent config:

```yaml
name: my_agent
controller:
  model: "google/gemini-3-flash-preview"
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1

system_prompt_file: prompts/system.md

tools:
  - name: bash
    type: builtin
  - name: read
    type: builtin

subagents:
  - name: explore
    type: builtin
    extra_prompt: "Focus on Python files."
```

Full config reference: [docs/guides/configuration.md](docs/guides/configuration.md)

## Project Structure

```
src/kohakuterrarium/
  core/        # Runtime: agent, controller, executor, events, channels
  modules/     # Protocols: input, trigger, tool, output, subagent
  builtins/    # 16 tools, 10 sub-agents, CLI/Whisper, stdout/TTS
  parsing/     # Stream parser for [/tool]...[tool/] detection
  prompt/      # System prompt aggregation + Jinja2 templating
  llm/         # LLM abstraction (OpenAI/OpenRouter)
  utils/       # Structured colored logging

agents/        # 7 example agent configurations
docs/          # Architecture, API reference, guides
```

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Getting Started Guide](docs/guides/getting-started.md)
- [Configuration Reference](docs/guides/configuration.md)
- [Example Agents Guide](docs/guides/example-agents.md)
- [API Reference](docs/api/)
- [Code Conventions](CLAUDE.md)
- [Contributing](CONTRIBUTING.md)

## License

Apache-2.0

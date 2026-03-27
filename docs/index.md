# KohakuTerrarium Documentation

A universal agent framework for building any type of fully self-driven agent system.

## What is KohakuTerrarium?

KohakuTerrarium is a Python framework that enables building diverse agent systems - from SWE agents like Claude Code to conversational bots like Neuro-sama to autonomous monitoring systems. The name "Terrarium" reflects how the framework allows you to build different self-contained agent ecosystems.

## Key Features

- **Unified Event Model**: All components communicate through `TriggerEvent` - inputs, triggers, tool completions, and sub-agent outputs all flow through a single event type
- **Non-Blocking Architecture**: Tools execute asynchronously in the background while the LLM continues streaming
- **Configuration-Driven**: Build complete agents with YAML/JSON/TOML configs and minimal code
- **Extensible Modules**: Custom inputs, tools, triggers, and outputs through simple protocol interfaces
- **Nested Intelligence**: Full sub-agents with their own controllers for specialized tasks
- **Memory First**: Folder-based memory system with read/write protection
- **Multimodal Support**: Text and images throughout the pipeline
- **Streaming-First**: All operations support async streaming

## Quick Start

```python
from kohakuterrarium.core.agent import Agent

# Load agent from config folder
agent = Agent.from_path("agents/my_agent")

# Run the main loop
await agent.run()
```

Or programmatically:

```python
agent = Agent.from_path("agents/my_agent")
await agent.start()

# Inject events
await agent.inject_input("Hello!")

# Monitor state
print(f"Running: {agent.is_running}")
print(f"Tools: {agent.tools}")

await agent.stop()
```

## Documentation Overview

### Guides
- [Getting Started](guides/getting-started.md) - Installation and first agent
- [Configuration Reference](guides/configuration.md) - Complete config options
- [Example Agents](guides/example-agents.md) - Walkthrough of included examples

### Architecture
- [Architecture Overview](architecture.md) - System design and data flow

### API Reference
- [Core Module](api/core.md) - Agent, Controller, Executor, Job system
- [Modules](api/modules.md) - Input, Output, Tool, Trigger, SubAgent
- [Builtins](api/builtins.md) - Built-in tools and sub-agents

### Preliminary Documentation
- [Specification](preliminary/SPECIFICATION.md) - Original design specification
- [Structure](preliminary/STRUCTURE.md) - Project structure guide
- [Sub-Agent Design](preliminary/SUBAGENT_DESIGN.md) - Sub-agent system design

## Five Major Systems

KohakuTerrarium is built around five major systems that work together:

### 1. Input System
Receives external input (CLI, API, ASR, Discord messages) and converts to `TriggerEvent`:
```
External Input → InputModule → TriggerEvent(type="user_input")
```

### 2. Trigger System
Autonomous event generation (timers, idle detection, conditions):
```
Condition Met → TriggerModule → TriggerEvent(type="idle"|"timer"|...)
```

### 3. Controller System
Main LLM orchestrator that makes decisions and dispatches work:
```
TriggerEvent → Controller → LLM Response → ParseEvents
```

### 4. Tool/SubAgent Execution
Background execution of tools and sub-agents:
```
ToolCallEvent → Executor → asyncio.Task → JobResult
SubAgentCallEvent → SubAgentManager → SubAgentResult
```

### 5. Output System
Routes output to appropriate destinations:
```
TextEvent → OutputRouter → default_output (stdout)
OutputEvent → OutputRouter → named_output (discord, tts, etc.)
```

## Agent Types You Can Build

| Type | Description | Example |
|------|-------------|---------|
| SWE Agent | Coding assistant with file operations | Like Claude Code |
| Group Chat Bot | Discord/Slack bot with memory | Multi-user conversations |
| Conversational AI | Streaming voice bot | Like Neuro-sama |
| Monitoring Agent | Autonomous system watcher | Drone controller |
| Research Agent | Information gathering | Web search + analysis |

## Requirements

- Python 3.10+
- Modern type hints (`list`, `dict`, `X | None`)
- Async throughout (`asyncio`)
- Dependencies: httpx, pydantic (optional), PyYAML

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/kohakuterrarium.git
cd kohakuterrarium

# Install in editable mode
uv pip install -e .
# or
pip install -e .
```

## Running an Agent

```bash
# Run an example agent
python -m kohakuterrarium.run agents/swe_agent

# Or specify config path
python -m kohakuterrarium.run /path/to/agent/folder
```

## Next Steps

1. Read the [Getting Started Guide](guides/getting-started.md)
2. Explore the [Example Agents](guides/example-agents.md)
3. Review the [Architecture Overview](architecture.md)
4. Check the [Configuration Reference](guides/configuration.md)

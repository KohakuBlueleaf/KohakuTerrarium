# Contributing to KohakuTerrarium

Thanks for your interest in contributing! This document covers how to get started.

## Setup

```bash
git clone https://github.com/KohakuBlueleaf/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e ".[dev]"
```

## Code Conventions

All code conventions, architecture guidelines, and design principles are in **[CLAUDE.md](CLAUDE.md)**. Please read it before submitting changes. Key points:

- **Python 3.10+** with modern type hints (`list`, `dict`, `X | None`)
- **Import ordering**: built-in, third-party, kohakuterrarium (alphabetical within groups)
- **No `print()`** in library code - use structured logging
- **No imports inside functions** unless avoiding circular imports
- **Max 600 lines per file** (hard max: 1000)
- **Controller as orchestrator** - dispatch tasks, don't do heavy work
- **Full asyncio** throughout

## Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes following [CLAUDE.md](CLAUDE.md) conventions
4. Format with black: `python -m black src/`
5. Run tests: `python -m pytest tests/ -q`
6. Verify imports: `python -c "from kohakuterrarium.core.agent import Agent; print('OK')"`
7. Commit with descriptive message
8. Open a pull request

## Project Structure

```
src/kohakuterrarium/
  core/        # Runtime engine (agent, controller, executor, events)
  modules/     # Plugin protocols (tool, trigger, subagent, input, output)
  builtins/    # Built-in implementations (16 tools, 10 sub-agents)
  parsing/     # Stream parser (state machine for tool call detection)
  prompt/      # Prompt aggregation and templating
  llm/         # LLM provider abstraction (OpenAI/OpenRouter)
  utils/       # Shared utilities (logging)
creatures/     # Pre-built creature templates (general, swe, reviewer, ops, researcher, root)
terrariums/    # Pre-built terrarium templates
examples/      # Example agent apps, terrariums, and code samples
docs/          # Documentation
```

Each directory has its own README.md with module-specific details.

## Adding a Built-in Tool

1. Create `src/kohakuterrarium/builtins/tools/my_tool.py`:

```python
from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode, ToolResult


@register_builtin("my_tool")
class MyTool(BaseTool):
    @property
    def tool_name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "One-line description"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        # Implementation
        return ToolResult(output="result", exit_code=0)
```

2. Add import to `builtins/tools/__init__.py`
3. Create skill doc at `builtin_skills/tools/my_tool.md`

## Adding a Built-in Sub-Agent

1. Create `src/kohakuterrarium/builtins/subagents/my_agent.py`:

```python
from kohakuterrarium.modules.subagent.config import SubAgentConfig

MY_AGENT_CONFIG = SubAgentConfig(
    name="my_agent",
    description="What it does",
    tools=["read", "grep"],
    system_prompt="You are a specialist in...",
    can_modify=False,
    max_turns=5,
    timeout=60.0,
)
```

2. Add import to `builtins/subagents/__init__.py`
3. Create skill doc at `builtin_skills/subagents/my_agent.md`

## Adding an Example Agent

1. Create `examples/agent-apps/my_agent/config.yaml` with tool and sub-agent configuration
2. Create `examples/agent-apps/my_agent/prompts/system.md` with system prompt
3. Update `examples/README.md`

## Key Architecture Rules

Read CLAUDE.md "Core Architecture Concepts" section. The critical rules:

- **Creature**: self-contained agent. Works standalone. Does NOT know it is in a terrarium.
- **Terrarium**: pure wiring. NO intelligence. Loads creatures, creates channels, manages lifecycle.
- **Root Agent**: sits OUTSIDE the terrarium, manages it via tools. NEVER a peer of creatures inside.
- **Sub-agents** are INSIDE a creature (vertical). Terrarium wires BETWEEN creatures (horizontal). Never mix these.
- Root agent is ALWAYS force-given all terrarium tools when bound to a terrarium.

## Reporting Issues

- Search existing issues first
- Include: Python version, OS, steps to reproduce, expected vs actual behavior
- For agent behavior issues: include the agent config and relevant logs

## License

By contributing, you agree that your contributions will be licensed under the project's Apache-2.0 License.

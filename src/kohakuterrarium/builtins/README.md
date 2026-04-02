# builtins/ (Built-in Components)

Ready-to-use tools, sub-agents, inputs, and outputs that ship with the framework.
Agents reference these by name in their `config.yaml`.

## Tools (20)

| Name | Description |
|------|-------------|
| `bash` | Execute shell commands (auto-detects platform shell) |
| `python` | Execute Python code via subprocess |
| `read` | Read file contents with optional line range |
| `write` | Create or overwrite files |
| `edit` | Edit files using unified diff format |
| `glob` | Find files by glob pattern |
| `grep` | Search file contents with regex and type filtering |
| `tree` | List directory structure with frontmatter summaries |
| `think` | No-op tool for explicit LLM reasoning |
| `scratchpad` | Read/write session-scoped key-value working memory |
| `ask_user` | Request human input mid-execution (CLI) |
| `http` | Make HTTP requests to APIs and web services |
| `json_read` | Read and query JSON files with path expressions |
| `json_write` | Modify JSON files with path expressions |
| `send_message` | Send a message to a named channel |
| `wait_channel` | Wait for a message on a named channel |
| `info` | Load full documentation for a tool or sub-agent on demand |
| `list_triggers` | Introspect active triggers on the agent |
| `stop_task` | Cancel a running background tool or sub-agent |
| `terrarium_tools` | Terrarium management tools for the root agent (lazily registered) |

## Sub-agents (10)

| Name | Description |
|------|-------------|
| `explore` | Search and explore codebase (read-only) |
| `plan` | Create implementation plans (read-only) |
| `worker` | Implement code changes, fix bugs, refactor (read-write) |
| `critic` | Review and critique code, plans, or outputs |
| `summarize` | Summarize long content into concise summaries |
| `research` | Research topics using files and web access |
| `coordinator` | Coordinate multiple agents via channels |
| `memory_read` | Search and retrieve from memory |
| `memory_write` | Store information to memory (can create files) |
| `response` | Generate user-facing responses (output sub-agent) |

## Inputs and Outputs

**Inputs:** `cli` (blocking and non-blocking), `tui` (shared TUI session), `whisper` (Silero VAD + Whisper ASR), `none` (trigger-only, no input)

**Outputs:** `stdout` (plain and prefixed), `tui` (shared TUI session), `tts` (console TTS with config)

## TUI System (`tui/`)

Shared terminal UI with coordinated input and output via the session registry.

| Module | Purpose |
|--------|---------|
| `TUISession` | Shared state (input queue, output buffer, stop signal) stored in `Session.tui` |
| `TUIInput` | Input module reading from `TUISession`. Config: `input: {type: tui}` |
| `TUIOutput` | Output module writing to `TUISession`. Config: `output: {type: tui}` |

Both modules attach to the same `TUISession` instance via `get_session()`, enabling coordinated terminal access.

## Catalogs

Tool and sub-agent registration logic lives in catalog modules at the
builtins root, separate from the implementation subdirectories:

| File | Purpose |
|------|---------|
| `tool_catalog.py` | Tool registry: `register_builtin`, `get_builtin_tool`, `list_builtin_tools`, `is_builtin_tool` |
| `subagent_catalog.py` | Sub-agent registry: `get_builtin_subagent_config`, `list_builtin_subagents` |

## Usage

```python
from kohakuterrarium.builtins.tool_catalog import get_builtin_tool
from kohakuterrarium.builtins.subagent_catalog import get_builtin_subagent_config

tool = get_builtin_tool("bash")           # Returns BaseTool instance
config = get_builtin_subagent_config("explore")  # Returns SubAgentConfig
```

## Adding Custom Builtins

Register new tools with `@register_builtin("name")`:

```python
from kohakuterrarium.builtins.tool_catalog import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ToolResult

@register_builtin("my_tool")
class MyTool(BaseTool):
    @property
    def tool_name(self) -> str: return "my_tool"
    @property
    def description(self) -> str: return "Does something useful"
    async def execute(self, args: dict) -> ToolResult:
        return ToolResult(output="done")
```

## File Layout

```
builtins/
├── tool_catalog.py      # Tool registry (canonical location)
├── subagent_catalog.py  # Sub-agent registry (canonical location)
├── tools/       # 20 tool implementations
├── subagents/   # 10 sub-agent configs
├── inputs/      # CLI, Whisper, and None input modules
├── outputs/     # Stdout and TTS output modules
└── tui/         # TUI session, input, and output modules
```

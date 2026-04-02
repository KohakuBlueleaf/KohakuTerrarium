# builtins/tools/

Built-in tool implementations. Each tool extends `BaseTool` and uses the
`@register_builtin` decorator for automatic registration in the tool catalog.
The `__init__.py` imports every tool class to trigger registration and
re-exports the public API from `builtins.tool_catalog`.

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Imports all tools (triggers registration), re-exports catalog API |
| `registry.py` | Backward-compatible re-exports from `builtins.tool_catalog` |
| `bash.py` | `BashTool` (shell commands) and `PythonTool` (Python subprocess) |
| `read.py` | `ReadTool`: read file contents with optional line range |
| `write.py` | `WriteTool`: create or overwrite files |
| `edit.py` | `EditTool`: edit files using unified diff format |
| `glob.py` | `GlobTool`: find files by glob pattern |
| `grep.py` | `GrepTool`: search file contents with regex and type filtering |
| `tree.py` | `TreeTool`: list directory structure with frontmatter summaries |
| `think.py` | `ThinkTool`: no-op tool for explicit LLM reasoning |
| `scratchpad_tool.py` | `ScratchpadTool`: session-scoped key-value working memory |
| `ask_user.py` | `AskUserTool`: request human input mid-execution |
| `http_tool.py` | `HttpTool`: make HTTP requests to APIs and web services |
| `json_read.py` | `JsonReadTool`: read and query JSON files with path expressions |
| `json_write.py` | `JsonWriteTool`: modify JSON files with path expressions |
| `send_message.py` | `SendMessageTool`: send a message to a named channel |
| `wait_channel.py` | `WaitChannelTool`: wait for a message on a named channel |
| `info.py` | `InfoTool`: load full documentation for a tool or sub-agent on demand |
| `list_triggers.py` | `ListTriggersTool`: introspect active triggers on the agent |
| `stop_task.py` | `StopTaskTool`: cancel a running background tool or sub-agent |
| `terrarium_tools.py` | Terrarium management tools for the root agent (lazily registered) |

## Dependencies

- `kohakuterrarium.builtins.tool_catalog` (register_builtin, catalog API)
- `kohakuterrarium.builtin_skills` (documentation lookup for info tool)
- `kohakuterrarium.modules.tool.base` (BaseTool, ToolResult, ToolContext, ExecutionMode)
- `kohakuterrarium.core.channel` (for send_message and wait_channel)
- `kohakuterrarium.core.session` (for scratchpad access)
- `kohakuterrarium.terrarium` (for terrarium_tools)
- `kohakuterrarium.utils.logging`

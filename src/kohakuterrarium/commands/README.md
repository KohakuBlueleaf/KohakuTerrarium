# commands/

Framework commands that the controller can invoke during LLM output processing.
Commands are inline directives (e.g., `##read job_id##`, `##info tool_name##`)
that return content to be injected into the controller's conversation context.
Unlike tools, commands are synchronous, lightweight, and do not create
background jobs.

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Re-exports protocol, base class, and all command implementations |
| `base.py` | `Command` protocol, `BaseCommand` ABC with error handling, `CommandResult`, `parse_command_args` |
| `read.py` | `ReadCommand` (read job output), `InfoCommand` (tool/sub-agent docs), `JobsCommand` (list running jobs), `WaitCommand` (block until job completes) |

## Dependencies

- `kohakuterrarium.builtin_skills` (documentation lookup for InfoCommand)
- `kohakuterrarium.core.job` (job store access for ReadCommand, WaitCommand)

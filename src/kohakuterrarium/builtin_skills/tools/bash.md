---
name: bash
description: Execute shell commands (prefer dedicated tools for file ops)
category: builtin
tags: [shell, command, system]
---

# bash

Execute shell commands and return output.

## IMPORTANT: Prefer Dedicated Tools

Do NOT use bash for operations that have dedicated tools:
- File reading: use `read` (NOT `cat`, `head`, `tail`)
- File editing: use `edit` (NOT `sed`, `awk`)
- File writing: use `write` (NOT `echo >`, `cat <<EOF`)
- File finding: use `glob` (NOT `find`, `ls`)
- Content search: use `grep` (NOT `grep`, `rg` via bash)

Using dedicated tools gives structured output and enables safety guards.

## Git Safety

- Prefer new commits over amending existing ones
- Never skip hooks (--no-verify) unless explicitly asked
- Before destructive operations (reset --hard, push --force), confirm with the user
- Never force push to main/master

## Multiple Commands

- Independent commands: run them separately (parallel execution)
- Dependent commands: chain with `&&`
- Sequential (failure OK): chain with `;`

## WHEN TO USE

- Running system commands (git, npm, pip, cargo, etc.)
- Checking system state (pwd, whoami, env)
- Running build/test commands
- Package management operations

## HOW TO USE

```
tool call: bash(
command here
)
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| command | body | Shell command to execute (required) |

## Examples

```
tool call: bash(
git status
)
```

```
tool call: bash(
pytest tests/ -v
)
```

## Output Format

Returns stdout and stderr combined. Exit code is included in result.

## LIMITATIONS

- Commands have timeout (default: 30 seconds)
- Large outputs may be truncated
- Platform-dependent (PowerShell on Windows, bash on Unix)

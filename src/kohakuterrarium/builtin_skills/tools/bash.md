---
name: bash
description: Execute shell commands and return output
category: builtin
tags: [shell, command, system]
---

# bash

Execute shell commands and return output.

## WHEN TO USE

- Running system commands (git, npm, pip, cargo, etc.)
- Checking system state (ls, pwd, whoami)
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
ls -la
)
```

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

```
tool call: bash(
cd /tmp
ls -la
pwd
)
```

## Output Format

Returns stdout and stderr combined. Exit code is included in result.

## LIMITATIONS

- Commands have timeout (default: 30 seconds)
- Large outputs may be truncated
- Platform-dependent (PowerShell on Windows, bash on Unix)

## TIPS

- For file reading, prefer `read` tool (more structured output)
- For file searching, prefer `glob` and `grep` tools
- Use full paths when possible
- Chain commands with `&&` for dependent operations

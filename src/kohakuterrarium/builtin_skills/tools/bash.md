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
##tool##
name: bash
args:
  command: <shell command>
##tool##
```

## Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `command` | Yes | Shell command to execute |

## Examples

```yaml
# List files
##tool##
name: bash
args:
  command: ls -la
##tool##

# Git status
##tool##
name: bash
args:
  command: git status
##tool##

# Run tests
##tool##
name: bash
args:
  command: pytest tests/ -v
##tool##
```

## LIMITATIONS

- Commands have timeout (default: 30 seconds)
- Large outputs may be truncated
- Platform-dependent (PowerShell on Windows, bash on Unix)

## TIPS

- For file reading, prefer `read` tool (more structured output)
- For file searching, prefer `glob` and `grep` tools
- Use full paths when possible
- Chain commands with `&&` for dependent operations

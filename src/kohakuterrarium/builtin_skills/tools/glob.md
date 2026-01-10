---
name: glob
description: Find files matching a glob pattern
category: builtin
tags: [file, search]
---

# glob

Find files matching a glob pattern.

## WHEN TO USE

- Finding files by name or extension
- Exploring project structure
- Locating specific file types

## HOW TO USE

```
##tool##
name: glob
args:
  pattern: <glob pattern>
  path: <base directory, optional>
  limit: <max results, optional>
##tool##
```

## Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `pattern` | Yes | Glob pattern (e.g., `**/*.py`) |
| `path` | No | Base directory (default: cwd) |
| `limit` | No | Max results (default: 100) |

## Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `*` | Any chars except `/` |
| `**` | Any chars including `/` (recursive) |
| `?` | Single character |
| `[abc]` | a, b, or c |

## Examples

```yaml
# All Python files
##tool##
name: glob
args:
  pattern: "**/*.py"
##tool##

# Files in specific dir
##tool##
name: glob
args:
  pattern: "*.ts"
  path: src/components
##tool##

# Config files
##tool##
name: glob
args:
  pattern: "**/*.{json,yaml,toml}"
##tool##
```

## Output Format

```
src/main.py
src/utils/helpers.py
tests/test_main.py
```

## LIMITATIONS

- Returns file paths only (not contents)
- Results sorted by modification time (newest first)

## TIPS

- Use `**/*.ext` for recursive search
- Combine with `read` to examine found files
- Use specific patterns to narrow results

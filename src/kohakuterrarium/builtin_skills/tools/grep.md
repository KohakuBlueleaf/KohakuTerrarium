---
name: grep
description: Search file contents for a pattern (regex)
category: builtin
tags: [search, content]
---

# grep

Search file contents for a pattern using regex.

## WHEN TO USE

- Finding where something is defined/used
- Searching for specific code patterns
- Locating TODOs, FIXMEs, or comments
- Finding function/class definitions

## HOW TO USE

```
##tool##
name: grep
args:
  pattern: <regex pattern>
  path: <directory, optional>
  glob: <file filter, optional>
  limit: <max matches, optional>
  ignore_case: <true/false, optional>
##tool##
```

## Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `pattern` | Yes | Regex pattern to search |
| `path` | No | Directory to search (default: cwd) |
| `glob` | No | File pattern filter (default: `**/*`) |
| `limit` | No | Max matches (default: 50) |
| `ignore_case` | No | Case-insensitive (default: false) |

## Examples

```yaml
# Find function definitions
##tool##
name: grep
args:
  pattern: "def \\w+\\("
  glob: "**/*.py"
##tool##

# Case-insensitive search
##tool##
name: grep
args:
  pattern: "todo|fixme"
  ignore_case: true
##tool##

# Search specific directory
##tool##
name: grep
args:
  pattern: "import.*react"
  path: src/components
  glob: "*.tsx"
##tool##
```

## Output Format

```
src/main.py:10: def main():
src/utils.py:25: def helper(x):
```

## LIMITATIONS

- Regex syntax (escape special chars with `\\`)
- Large codebases may need file filter

## TIPS

- Use `glob` arg to narrow file types
- Escape regex special chars: `\\(`, `\\[`, `\\.`
- Use `read` after grep to examine context
- For simple text, `ignore_case: true` helps

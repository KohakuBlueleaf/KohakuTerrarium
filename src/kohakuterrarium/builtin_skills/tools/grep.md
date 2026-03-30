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
tool call: grep(
pattern
)
```

With optional parameters:

```
tool call: grep(
  path: src/
  glob: **/*.py
  limit: 50
  ignore_case: true
pattern
)
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| pattern | body | Regex pattern to search (required) |
| path | @@arg | Directory to search (default: cwd) |
| glob | @@arg | File pattern filter (default: `**/*`) |
| limit | @@arg | Max matches (default: 50) |
| ignore_case | @@arg | Case-insensitive (default: false) |

## Examples

```
tool call: grep(
  glob: **/*.py
def \w+\(
)
```

```
tool call: grep(
  ignore_case: true
todo|fixme
)
```

```
tool call: grep(
  path: src/components
  glob: *.tsx
import.*react
)
```

```
tool call: grep(
  path: src/main.py
import
)
```

## Output Format

```
src/main.py:10: def main():
src/utils.py:25: def helper(x):

(2 matches in 15 files)
```

## LIMITATIONS

- Regex syntax (escape special chars with `\`)
- Large codebases may need file filter

## TIPS

- Use `glob` arg to narrow file types
- Escape regex special chars: `\(`, `\[`, `\.`
- Use `read` after grep to examine context
- For simple text, `ignore_case="true"` helps

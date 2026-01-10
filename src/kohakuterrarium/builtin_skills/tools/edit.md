---
name: edit
description: Edit file by replacing text (string replacement)
category: builtin
tags: [file, io, edit]
---

# edit

Edit file by finding and replacing text. Requires unique match.

## WHEN TO USE

- Modifying existing code (functions, classes, etc.)
- Fixing bugs in existing files
- Adding/removing lines in specific locations
- Updating config values

## HOW TO USE

```
##tool##
name: edit
args:
  path: <file path>
  old_string: |
    <exact text to find>
  new_string: |
    <replacement text>
##tool##
```

## Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `path` | Yes | Path to file |
| `old_string` | Yes | Exact text to find (must be unique) |
| `new_string` | Yes | Text to replace with |

## Examples

```yaml
# Replace a function
##tool##
name: edit
args:
  path: src/main.py
  old_string: |
    def hello():
        print("Hi")
  new_string: |
    def hello():
        print("Hello, World!")
##tool##

# Add an import
##tool##
name: edit
args:
  path: src/utils.py
  old_string: |
    import os
  new_string: |
    import os
    import sys
##tool##

# Fix a bug
##tool##
name: edit
args:
  path: src/calc.py
  old_string: |
    return a + b
  new_string: |
    return a * b
##tool##
```

## Output Format

```
Edited /path/to/file.py: replaced 3 lines with 5 lines (+2 lines)
```

## LIMITATIONS

- `old_string` must exist exactly ONCE in file
- If multiple matches found, add more context lines
- Whitespace and indentation must match exactly

## TIPS

- Use `read` first to see exact file content
- Include surrounding lines if match isn't unique
- Preserve original indentation exactly
- Use YAML multiline (`|`) for multi-line content
- For new files, use `write` tool instead

---
name: write
description: Write content to a file (creates or overwrites)
category: builtin
tags: [file, io]
---

# write

Write content to a file. Creates if doesn't exist, overwrites if it does.

## WHEN TO USE

- Creating new files
- Replacing entire file contents
- Writing generated code or configs

## HOW TO USE

```
##tool##
name: write
args:
  path: <file path>
  content: |
    <file content>
##tool##
```

## Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `path` | Yes | Path to file |
| `content` | Yes | Content to write |

## Examples

```yaml
# Create Python file
##tool##
name: write
args:
  path: src/hello.py
  content: |
    def hello():
        print("Hello, World!")

    if __name__ == "__main__":
        hello()
##tool##

# Create config
##tool##
name: write
args:
  path: config.json
  content: |
    {
      "name": "my-app",
      "version": "1.0.0"
    }
##tool##
```

## Output Format

```
Created /path/to/file.py (15 lines, 342 bytes)
```

## LIMITATIONS

- Overwrites entire file (no partial edit)
- Creates parent directories automatically

## TIPS

- Use `read` first to understand existing content
- Use YAML multiline syntax (`|`) for content
- For partial edits, use `edit` tool (when available)

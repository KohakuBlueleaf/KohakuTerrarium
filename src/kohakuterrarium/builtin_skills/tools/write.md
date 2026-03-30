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
tool call: write(
  path: file_path
content here
)
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | @@arg | Path to file (required) |
| content | body | Content to write |

## Examples

```
tool call: write(
  path: src/hello.py
def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
)
```

```
tool call: write(
  path: config.json
{
  "name": "my-app",
  "version": "1.0.0"
}
)
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
- For partial edits, use `edit` tool
- Content is written exactly as provided

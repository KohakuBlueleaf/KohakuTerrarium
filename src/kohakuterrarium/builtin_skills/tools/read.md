---
name: read
description: Read file contents (required before write/edit)
category: builtin
tags: [file, io]
---

# read

Read file contents with optional line range.

## SAFETY

- **You MUST read files before writing or editing them.** The write and edit tools will error if you haven't read the file first.
- Binary files (images, PDFs, compiled files) are detected and rejected with a helpful message.
- Lines longer than 2000 characters are truncated.
- Total output is capped at 200KB. Use offset/limit for large files.

## WHEN TO USE

- Examining source code or config files
- Checking file contents before editing
- Reading logs or text data
- Understanding existing code

## HOW TO USE

```
tool call: read(
  path: file_path
)
```

Or with optional parameters:

```
tool call: read(
  path: file_path
  offset: 10
  limit: 20
)
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | @@arg | Path to file (required) |
| offset | @@arg | Starting line (0-based, default: 0) |
| limit | @@arg | Max lines to read (default: all) |

## Examples

```
tool call: read(
  path: src/main.py
)
```

```
tool call: read(
  path: src/main.py
  offset: 10
  limit: 20
)
```

## Output Format

```
     1→first line content
     2→second line content
     3→...
```

## LIMITATIONS

- UTF-8 encoding (binary files are rejected)
- Very large files should use offset/limit

## TIPS

- Use `glob` first to find files by pattern, then `read` to examine them
- Use `grep` to locate relevant lines, then `read` with offset/limit to examine context
- For large files, read in chunks with offset/limit

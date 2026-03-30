---
name: memory_read
description: Search and retrieve information from memory
category: subagent
tags: [memory, retrieval, context]
---

# memory_read

Sub-agent for searching the memory folder using natural language queries.

## Syntax

```
tool call: memory_read(
natural language query
)
```

## What It Does

- Searches memory files for relevant information
- Uses tree, read, grep to find matching content
- Returns found information

## When It Helps

- If you want more context about a user or topic
- If you're unsure whether you've encountered something before
- If you need to recall stored preferences or facts

## Query Examples

```
tool call: memory_read(
what do I know about User1
)
```

```
tool call: memory_read(
user preferences
)
```

```
tool call: memory_read(
recent conversation topics
)
```

## Notes

- Query is natural language, NOT a file path
- Read-only (cannot modify memory)
- Only searches configured memory path

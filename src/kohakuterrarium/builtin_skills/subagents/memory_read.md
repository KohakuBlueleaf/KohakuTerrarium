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
[/memory_read]
natural language query
[memory_read/]
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
[/memory_read]
what do I know about User1
[memory_read/]
```

```
[/memory_read]
user preferences
[memory_read/]
```

```
[/memory_read]
recent conversation topics
[memory_read/]
```

## Notes

- Query is natural language, NOT a file path
- Read-only (cannot modify memory)
- Only searches configured memory path

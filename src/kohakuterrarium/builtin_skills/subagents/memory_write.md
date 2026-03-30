---
name: memory_write
description: Store information to memory
category: subagent
tags: [memory, storage, persistence]
---

# memory_write

Sub-agent for storing information in the memory folder.

## Syntax

```
tool call: memory_write(
description of what to store
)
```

## What It Does

- Determines appropriate file based on content
- Creates or updates memory files
- Respects protected file rules

## When It Helps

- If you learn something noteworthy about a user
- If there's context worth remembering for later
- If you want to update your working memory

## Content Examples

```
tool call: memory_write(
User1 mentioned they're learning piano in #general
)
```

```
tool call: memory_write(
User prefers concise responses
)
```

```
tool call: memory_write(
Current project context: working on agent framework
)
```

## Notes

- Describe what to store in natural language
- System auto-decides which file to update
- Include context: who, what, where
- Cannot modify protected files (character.md, rules.md)

---
name: think
description: Explicit reasoning step preserved in context
category: builtin
tags: [reasoning, planning]
---

# think

Record a reasoning step. The tool does nothing - its value is that
your thought is preserved in context and won't be lost to compaction.

## WHEN TO USE

- Before complex multi-step tasks
- When you need to plan your approach
- To record analysis or decisions
- When reasoning through tradeoffs

## HOW TO USE

```
[/think]
your reasoning here
[think/]
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| thought | content | Your reasoning text |

## Examples

```
[/think]
The user wants to refactor the auth module.
Steps:
1. Find all auth-related files
2. Identify the current pattern
3. Design the new pattern
4. Implement changes
[think/]
```

## Output Format

Returns "Noted." (fixed response).

## LIMITATIONS

- No side effects (the tool does nothing except preserve the thought in context)
- Subject to context compaction like all other messages (but prioritized for retention)

## TIPS

- Use before starting complex tasks
- Structure your thoughts with numbered steps
- Record key decisions and their reasoning

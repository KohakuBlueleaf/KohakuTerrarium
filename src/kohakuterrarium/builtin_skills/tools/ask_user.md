---
name: ask_user
description: Ask the user a question and wait for response
category: builtin
tags: [interaction, human-in-the-loop]
---

# ask_user

Ask the user a question and wait for their response. Enables human-in-the-loop
patterns where the agent needs clarification, approval, or additional input.

## WHEN TO USE

- Requesting clarification before taking an ambiguous action
- Approval workflows before destructive or irreversible operations
- Gathering additional input mid-execution
- Confirming choices when multiple valid approaches exist
- Interactive decision-making with the user

## HOW TO USE

```
tool call: ask_user(
Your question here
)
```

The question text is passed as the content body.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| question | content | The question to present to the user (required) |

## Examples

Ask for clarification:

```
tool call: ask_user(
I found 3 potential approaches. Which should I use?
1. Refactor the existing module
2. Create a new module
3. Use a third-party library
)
```

Ask for approval:

```
tool call: ask_user(
Should I proceed with deleting the deprecated files? (yes/no)
)
```

Gather missing information:

```
tool call: ask_user(
What database host should I use for the staging environment?
)
```

## Output Format

Returns the user's raw text response as a string.

If the user provides an empty response, returns `(no response)`.

## LIMITATIONS

- CLI-only: reads from stdin, writes the question to stderr
- Will hang indefinitely if stdin is not available (non-interactive environments)
- Not suitable for agents running in headless/daemon mode
- One question at a time; cannot present interactive menus

## TIPS

- Keep questions clear and concise
- Offer numbered options when presenting choices
- Use yes/no format for simple confirmations
- Provide context so the user can make an informed decision
- Avoid asking unnecessary questions; prefer sensible defaults when possible

# Software Engineering

## Workflow
Understand -> Search (glob/grep) -> Read -> Plan -> Implement -> Validate.
Use git log/blame for historical context when needed.
Run tests after changes: start specific, then broader.
Don't add test frameworks to codebases without tests.
Don't add formatters to codebases without formatters.
Don't fix unrelated bugs or broken tests.
Mention unrelated issues in your final message without fixing them.

## Code Editing
The best changes are the smallest correct changes.
Read the file before editing. Understand the context.
Keep things in one function unless composable or reusable.
Match surrounding style (naming, indentation, idioms).
Update docs when changing behavior.
No copyright/license headers unless asked.

## Git
Never commit, push, or branch unless asked.
Never amend commits unless asked.
Never use reset --hard, checkout --, force push.
Never skip hooks (--no-verify).
Prefer non-interactive git commands.
When committing: summarize the "why" not the "what".

## Validation
Start with the most specific test for your change.
Run the test, check the output. Don't claim success without verification.
Iterate up to 3 times on formatting issues.
If you can't fix formatting, present correct code and note the issue.
If you can't run tests, say so explicitly rather than implying success.

## Team Workflow (when in a terrarium)
You automatically listen to channels assigned to you. Messages arrive as
trigger events showing [Channel 'name' from sender].

When triggered by a channel message:
1. Read the task from the trigger message (note which channel it came from)
2. Do the implementation work using your tools and sub-agents
3. Send your results to the appropriate output channel using `send_message`
4. Do NOT just output text. Other creatures cannot see your text output
5. Broadcast messages are informational. Only act if directly relevant to you

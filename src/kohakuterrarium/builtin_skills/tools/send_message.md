---
name: send_message
description: Send a message to a named channel for agent-to-agent communication
category: builtin
tags: [communication, multi-agent]
---

# send_message

Send a message to a named channel. Used for agent-to-agent communication, allowing agents to coordinate and exchange information through named channels.

## WHEN TO USE

- Sending a message to another agent
- Coordinating work between multiple agents
- Delivering results from a sub-agent to a parent agent
- Broadcasting status updates or notifications to a channel

## HOW TO USE

```
[/send_message]
@@channel=channel_name
Message content here.
[send_message/]
```

Or with optional metadata:

```
[/send_message]
@@channel=channel_name
@@metadata={"priority": "high"}
Message content here.
[send_message/]
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| channel | @@arg | Channel name to send to (required) |
| message | content | Message body (required) |
| metadata | @@arg | Optional JSON object with extra info |

## Examples

Send a task to another agent:
```
[/send_message]
@@channel=inbox_agent_b
Please research the authentication module and report your findings.
[send_message/]
```

Send results with metadata:
```
[/send_message]
@@channel=results
@@metadata={"priority": "high", "source": "code_review"}
Analysis complete. Found 3 issues in the auth module.
[send_message/]
```

Notify a monitoring channel:
```
[/send_message]
@@channel=alerts
@@metadata={"severity": "warning"}
Memory usage exceeded 80% threshold.
[send_message/]
```

## Output Format

```
Message sent to channel 'channel_name'
```

## LIMITATIONS

- Fire-and-forget: no delivery confirmation beyond "message sent"
- No message persistence across restarts (in-memory queues)
- Metadata must be valid JSON if provided

## TIPS

- Channel names are arbitrary strings; both sender and receiver must agree on the name
- Channels are created automatically on first use (no setup needed)
- Messages are queued; the receiver picks them up at its own pace
- Use metadata to attach structured info (priority, source, tags) without polluting the message body
- The sender identity is set automatically from the agent context

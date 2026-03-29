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
- Broadcasting status updates or notifications to all subscribers
- Replying to a specific message in a conversation thread

## HOW TO USE

```
[/send_message]
@@channel=channel_name
Message content here.
[send_message/]
```

Or with optional metadata and threading:

```
[/send_message]
@@channel=channel_name
@@metadata={"priority": "high"}
@@reply_to=msg_abc123def456
Message content here.
[send_message/]
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| channel | @@arg | Channel name to send to (required) |
| message | content | Message body (required) |
| metadata | @@arg | Optional JSON object with extra info |
| channel_type | @@arg | Channel type: "queue" (default) or "broadcast" |
| reply_to | @@arg | Optional message ID to reply to (for threading) |

## Channel Types

- **queue** (default): Point-to-point. One consumer receives each message. Use for direct agent-to-agent communication via SubAgentChannel.
- **broadcast**: All subscribers receive every message. Use for status updates, events, or notifications via AgentChannel.

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

Broadcast to all listeners:
```
[/send_message]
@@channel=status_updates
@@channel_type=broadcast
Build completed successfully. All tests passing.
[send_message/]
```

Reply to a previous message:
```
[/send_message]
@@channel=inbox_agent_b
@@reply_to=msg_abc123def456
Here are the results you requested.
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
Message sent to channel 'channel_name' (id: msg_abc123def456)
```

## LIMITATIONS

- Fire-and-forget: no delivery confirmation beyond "message sent"
- No message persistence across restarts (in-memory queues)
- Metadata must be valid JSON if provided
- Broadcast channels require subscribers to be listening before the message is sent

## TIPS

- Channel names are arbitrary strings; both sender and receiver must agree on the name
- Channels are created automatically on first use (no setup needed)
- Messages are queued; the receiver picks them up at its own pace
- Use metadata to attach structured info (priority, source, tags) without polluting the message body
- The sender identity is set automatically from the agent context
- Each message gets a unique message_id that can be used for reply_to threading
- Use broadcast channels when multiple agents need to observe the same events
- Use queue channels for direct point-to-point communication

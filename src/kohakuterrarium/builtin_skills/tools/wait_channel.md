---
name: wait_channel
description: Wait for a message on a named channel
category: builtin
tags: [channel, async, communication]
---

# wait_channel

Wait for a message to arrive on a named channel.

## WHEN TO USE

- Waiting for a response from another agent or sub-agent
- Implementing request-response patterns across channels
- Listening for events or notifications from other components
- Coordinating multi-agent workflows where one agent depends on another's output

## HOW TO USE

```
[/wait_channel]
@@channel=channel_name
[wait_channel/]
```

Or with a custom timeout:

```
[/wait_channel]
@@channel=channel_name
@@timeout=60
[wait_channel/]
```

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| channel | @@arg | Channel name to listen on (required) |
| timeout | @@arg | Seconds to wait before timing out (default: 30) |

## Channel Type Handling

- **Queue channels (SubAgentChannel)**: Receives the next message from the queue. The message is consumed and removed.
- **Broadcast channels (AgentChannel)**: Automatically subscribes using the agent name, receives one message, then unsubscribes. Each wait_channel call creates a fresh subscription.

## Examples

Wait for a result on the default timeout:

```
[/wait_channel]
@@channel=results_inbox
[wait_channel/]
```

Wait up to 2 minutes for a long-running task:

```
[/wait_channel]
@@channel=processing_done
@@timeout=120
[wait_channel/]
```

Request-response pattern (send then wait):

```
[/send_message]
@@channel=worker_queue
Process this data
[send_message/]

[/wait_channel]
@@channel=results_inbox
@@timeout=60
[wait_channel/]
```

## Output Format

```
From: sender_name
Message-ID: msg_abc123def456
Content: message content here
Reply-To: msg_xyz789abc012
Metadata: {"key": "value"}
```

Reply-To line only appears when the message is a reply.
Metadata line only appears when the message includes metadata.

## LIMITATIONS

- Only receives one message per call
- Channel is created automatically if it does not exist yet
- On timeout, returns exit code 1 with a timeout notification
- Queue channels: messages are consumed (once received, removed from the queue)
- Broadcast channels: subscription is temporary (created and destroyed per call)

## TIPS

- Pair with `send_message` for request-response patterns
- Use descriptive channel names to avoid collisions (e.g., `agent_x_replies`)
- Set timeout based on expected response time; the default 30s is good for quick tasks
- For long-running sub-agents, increase timeout to avoid premature timeouts
- This tool runs in BACKGROUND mode so it does not block other parallel tools
- Use the Message-ID from responses to thread replies with the `reply_to` parameter in send_message

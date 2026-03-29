# Channel System

Channels are the communication primitive in a terrarium. They connect creatures through named async message conduits. There are two channel types with different delivery semantics, plus tools and triggers that integrate channels into the agent framework.

## Channel Types

### SubAgentChannel (queue)

Point-to-point delivery. Each message is consumed by exactly one receiver. Backed by `asyncio.Queue`.

**Semantics:**
- FIFO ordering
- Message is removed from the queue on receive
- If no receiver is listening, messages accumulate
- Timeout support on receive

**Use cases:** task dispatch, request-response, pipelines, any 1:1 communication.

**Config:**

```yaml
channels:
  tasks: { type: queue, description: "Task assignments" }
```

**Auto-creation:** Queue channels are created on-the-fly if a creature sends to a channel name that does not exist. This is handled by `ChannelRegistry.get_or_create()`, which defaults to queue type.

### AgentChannel (broadcast)

All subscribers receive every message. Each subscriber has an independent queue, so one slow consumer does not block others.

**Semantics:**
- Every subscriber gets a copy of each message (same `message_id`)
- Late subscribers miss messages sent before their subscription
- Unsubscribe removes the subscriber's queue
- Subscriber count is tracked

**Use cases:** group chat, shared awareness, status updates, event notification.

**Config:**

```yaml
channels:
  team_chat: { type: broadcast, description: "Team-wide updates" }
```

**Pre-existence required:** Broadcast channels must be pre-declared in the terrarium config or explicitly created before sending. If a creature tries to send to a non-existent broadcast channel, `send_message` returns an error listing all available channels. This prevents accidental creation of orphaned broadcast channels.

### Comparison

| Aspect | Queue (`SubAgentChannel`) | Broadcast (`AgentChannel`) |
|--------|--------------------------|---------------------------|
| Delivery | One consumer per message | All subscribers get copy |
| Backing | Single `asyncio.Queue` | Per-subscriber queues |
| Creation | Auto-created on send | Must pre-exist |
| Discovery | Pre-defined in config | Pre-defined in config |
| Ordering | FIFO per queue | FIFO per subscriber |
| Missed messages | Accumulate in queue | Lost if not subscribed |
| Scope | Typically between two creatures | Shared across many creatures |

## ChannelMessage

Every message flowing through a channel is a `ChannelMessage`:

```python
@dataclass
class ChannelMessage:
    sender: str                    # Creature name that sent the message
    content: str | dict            # Message payload (text or structured data)
    metadata: dict[str, Any]       # Arbitrary key-value pairs
    timestamp: datetime            # Auto-set on creation
    message_id: str                # Auto-generated unique ID (msg_xxxxxxxxxxxx)
    reply_to: str | None = None    # Optional message ID for threading
    channel: str | None = None     # Set automatically by the channel's send()
```

### Fields

| Field | Set by | Description |
|-------|--------|-------------|
| `sender` | Creator | Which creature sent the message. Set from `ToolContext.agent_name`. |
| `content` | Creator | The message body. String for text, dict for structured data. |
| `metadata` | Creator | Arbitrary metadata. Preserved through send/receive. |
| `timestamp` | Auto | Set to `datetime.now()` on creation. |
| `message_id` | Auto | Unique ID in format `msg_<12-char-hex>`. Used for `reply_to` threading. |
| `reply_to` | Creator | Optional. References another message's `message_id` for threading. |
| `channel` | Channel | Set by `channel.send()` to the channel name. |

## Channel Tools

Two built-in tools provide channel access to creatures.

### send_message

Send a message to a named channel. Direct execution mode (completes before returning).

**Arguments:**

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `channel` | `@@arg` | Yes | Target channel name |
| `message` | content | Yes | Message content (body of the tool block) |
| `channel_type` | `@@arg` | No | `"queue"` (default) or `"broadcast"` |
| `reply_to` | `@@arg` | No | Message ID to reply to |
| `metadata` | `@@arg` | No | JSON string of key-value metadata |

**Example - send to queue:**

```
[/send_message]
@@channel=ideas
Here is my story concept: A lighthouse keeper discovers
that the light attracts memories instead of ships.
[send_message/]
```

**Example - send to broadcast with metadata:**

```
[/send_message]
@@channel=team_chat
@@channel_type=broadcast
@@metadata={"phase": "brainstorming", "status": "complete"}
Brainstorming phase is done. Moving to planning.
[send_message/]
```

**Example - reply to a previous message:**

```
[/send_message]
@@channel=feedback
@@reply_to=msg_abc123def456
I've revised the outline based on your feedback.
[send_message/]
```

**Output:** Confirmation with the generated message ID.

**Error handling:** If sending to a non-existent broadcast channel, the tool returns an error listing all available channels.

### wait_channel

Wait for a message on a named channel. Background execution mode (does not block other tools).

**Arguments:**

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `channel` | `@@arg` | Yes | Channel name to listen on |
| `timeout` | `@@arg` | No | Seconds to wait (default: 30) |

**Example:**

```
[/wait_channel]
@@channel=results
@@timeout=60
[wait_channel/]
```

**Output:** Formatted message with sender, message ID, content, reply-to (if present), and metadata (if present).

**On timeout:** Returns a timeout notification with exit code 1.

**Broadcast behavior:** For broadcast channels, `wait_channel` automatically subscribes using the agent name, receives one message, and unsubscribes. For persistent listening, use `ChannelTrigger` (which the terrarium sets up automatically for listen channels).

## Channel Triggers

### ChannelTrigger

A `TriggerModule` that fires when a message arrives on a named channel. The terrarium runtime injects one `ChannelTrigger` per listen channel into each creature.

```python
trigger = ChannelTrigger(
    channel_name="ideas",
    subscriber_id="planner",      # Used for broadcast subscriptions
    session=shared_session,       # Shared session with channel registry
)
```

**Configuration fields:**

| Field | Description |
|-------|-------------|
| `channel_name` | Channel to listen on |
| `subscriber_id` | ID for broadcast subscriptions (auto-generated if not set) |
| `prompt` | Optional prompt template. Supports `{content}` substitution. |
| `filter_sender` | Only fire for messages from this sender (prevents self-triggering) |
| `session` | Session whose channel registry to use |

**Event produced:**

When a message arrives, the trigger creates:

```python
TriggerEvent(
    type=EventType.CHANNEL_MESSAGE,
    content=<message content or prompt-substituted text>,
    context={
        "sender": "brainstorm",
        "channel": "ideas",
        "message_id": "msg_abc123def456",
        "raw_content": <original message content>,
        # plus any metadata from the message
    },
)
```

**Queue vs broadcast behavior:**

- **Queue channels:** The trigger calls `channel.receive(timeout=1.0)` in a polling loop. The message is consumed on receive.
- **Broadcast channels:** The trigger subscribes using `subscriber_id` and calls `subscription.receive(timeout=1.0)`. On stop, the subscription is cleaned up.

**Sender filtering:** If `filter_sender` is set, the trigger only fires for messages from that specific sender. This is useful on broadcast channels to prevent a creature from triggering on its own messages.

## Prompt Awareness

When a terrarium wires channels to a creature, the runtime injects a "Terrarium Channels" section into the creature's system prompt. This section lists the channels relevant to that creature with their types, roles, and descriptions. See [Architecture - System Prompt Injection](architecture.md#system-prompt-injection) for the full format.

Creatures learn about their channels through this prompt section and use `send_message` / `wait_channel` tools to interact. They do not need any special configuration to understand channels - the prompt injection handles awareness.

## ChannelRegistry

The `ChannelRegistry` manages all channels within a session. In a terrarium, all creatures share one registry through a shared `Session`.

**Key methods:**

| Method | Description |
|--------|-------------|
| `get_or_create(name, channel_type, description)` | Get existing or create new channel. Type ignored on second call. |
| `get(name)` | Get channel by name, or `None` |
| `list_channels()` | List all channel names |
| `get_channel_info()` | Get name/type/description for all channels (used for prompt injection) |
| `remove(name)` | Remove a channel |

## Channel Topologies

Channels support flexible wiring. Multiple senders can write to the same channel, and a single sender can write to multiple channels.

**Many-to-one:** Multiple creatures send to a single queue channel. Messages are interleaved FIFO. Only one consumer receives each message.

```
creature_a --+
creature_b --+--> [results queue] --> aggregator
creature_c --+
```

**One-to-many:** A single creature sends to multiple channels, dispatching different content to different destinations.

```
                +--> [tasks queue] --> worker
coordinator --> +--> [status broadcast] --> all
                +--> [logs queue] --> monitor
```

**Many-to-many (broadcast):** All senders and receivers share a broadcast channel. Every subscriber receives every message (except their own).

```
creature_a <--+
creature_b <--+--> [team_chat broadcast]
creature_c <--+
```

These patterns compose freely. A creature can listen on some channels and send on others, enabling pipelines, fan-out, fan-in, and mesh topologies.

## Broadcast Channel Best Practices

Broadcast channels deliver messages to all subscribers except the sender.
When creatures listen on broadcast channels, be aware of these patterns:

**The cascade pattern**: If creature A sends to a broadcast channel, creatures B and C receive it. If B then sends to the same channel, A and C receive that. This can create rapid message exchanges. Mitigation:
- Use broadcast for one-way announcements, not conversations
- Prompt creatures to send to broadcast exactly once per task, not on every LLM turn
- Consider making broadcast channels send-only (in `can_send` but not `listen`) if creatures don't need to react to announcements

**The feedback loop**: Each message a creature sends generates tool feedback ("Delivered to..."), which triggers another LLM turn. If the model keeps sending broadcast messages, it creates an internal loop. The `send_message` feedback includes "no further action needed" to signal completion.

**Recommended patterns**:
- Queue channels for task dispatch and results (point-to-point, reliable)
- Broadcast for shared context (e.g., style decisions, language preferences)
- Broadcast listeners should absorb information without necessarily responding

## Error Handling

### Non-existent broadcast channel

When `send_message` targets a broadcast channel that does not exist, it returns an error with a listing of all available channels:

```
Error: Broadcast channel 'nonexistent' does not exist.
Available channels: `ideas` (queue), `team_chat` (broadcast)
```

This guides the LLM to use valid channel names.

### Non-existent queue channel

Queue channels auto-create silently via `get_or_create()`. This enables dynamic channel creation at runtime.

### Timeout

Both `receive()` and `wait_channel` support timeouts. On timeout:
- `receive()` raises `asyncio.TimeoutError`
- `wait_channel` tool returns a timeout message with exit code 1
- `ChannelTrigger` catches the timeout and retries (polling loop)

# Terrarium Design Decisions

Technical design choices for the Terrarium system. Companion to [creature-terrarium.md](./creature-terrarium.md).

Status legend: **Decided** = agreed upon, **Open** = needs further discussion.

---

## 1. Channel System Design — Decided

### Two Channel Types

**`SubAgentChannel`** (queue): `asyncio.Queue`-based. One consumer per message. `channel_type = "queue"`.

**`AgentChannel`** (broadcast): Each subscriber gets their own queue. `send()` copies to all. `channel_type = "broadcast"`. Subscribers get a `ChannelSubscription` handle with `receive()`/`try_receive()`/`unsubscribe()`.

**`BaseChannel`** ABC: Shared interface (`send()`, `channel_type`, `empty`, `qsize`).

**`ChannelRegistry`**: `get_or_create(name, channel_type="queue"|"broadcast")`. Returns existing channel if name already exists (ignores type on second call).

### ChannelMessage Fields

```python
@dataclass
class ChannelMessage:
    sender: str                    # creature/agent name
    content: str | dict            # message payload
    metadata: dict[str, Any]       # arbitrary key-value
    timestamp: datetime            # auto-set
    message_id: str                # auto-generated unique ID
    reply_to: str | None = None    # message threading
    channel: str | None = None     # set by channel's send()
```

### Implementation Status

All implemented and tested:
- `src/kohakuterrarium/core/channel.py` — full channel system
- `src/kohakuterrarium/modules/trigger/channel.py` — ChannelTrigger for both types
- `src/kohakuterrarium/builtins/tools/send_message.py` — with `channel_type`, `reply_to`
- `src/kohakuterrarium/builtins/tools/wait_channel.py` — broadcast subscription support
- `tests/integration/test_channels.py` — 23 tests, all passing

---

## 2. Communication Model — Decided

### No I/O Swap

The terrarium does **not** replace creature InputModule/OutputModule. Instead:

- **Receiving**: Terrarium appends `ChannelTrigger`(s) to the creature's triggers list. Messages arrive as `TriggerEvent(type=CHANNEL_MESSAGE)` through the standard event system. **No explicit `wait_channel` needed.**
- **Sending**: Creature explicitly calls `send_message` tool. The LLM decides what to share.

**Rationale**: Preserves creature opacity. The creature's internal reasoning stays private. Communication is intentional, not automatic. No new adapter modules needed.

### Trigger-Based Receiving (No Polling) — Decided

Creatures do NOT use `wait_channel` to receive messages. Instead:
- The terrarium injects `ChannelTrigger`(s) → messages arrive automatically as events
- Creatures without startup triggers simply idle until a channel message arrives
- Background tool/sub-agent results arrive via the feedback loop (no `[/wait]` needed)

This eliminates the "poll and wait" anti-pattern. The agent model is **reactive**: do work when triggered, idle otherwise. The `wait_channel` tool and `[/wait]` command still exist in the framework for edge cases but are not promoted in terrarium-managed creatures.

### System Prompt Injection — Implemented

The aggregator auto-generates a "Channel Communication" section when `send_message` or `wait_channel` tools are registered. Channel info (name, type, description) is passed via the `channels` parameter to `aggregate_system_prompt()`.

**SubAgentChannel vs AgentChannel prompt paths:**

| Aspect | SubAgentChannel (queue) | AgentChannel (broadcast) |
|--------|------------------------|-------------------------|
| Discovery | Pre-defined, static in prompt | Dynamic, can change at runtime |
| Prompt | Listed with descriptions | Listed with descriptions + seed explanation |
| Creation | Auto-created on-the-fly by `send_message` | Must already exist (error if not) |
| Error handling | N/A (auto-creates) | Returns available channel listing |
| Scope | Sessional, internal to creature | Cross-creature, terrarium-level |

**Every AgentChannel requires a name and description** — they're shared resources that all creatures need to understand.

When a creature tries to send to a non-existent broadcast channel, `send_message` returns an error listing all available channels. Queue channels auto-create silently.

For dynamic channel changes (channels created/removed at runtime), the terrarium can refresh the system prompt. If a creature tries to access a stale channel, the error message provides the current listing.

---

## 3. Dynamic Channel Creation — Decided: Hybrid

- **Pre-declared channels**: Typed in terrarium config (queue or broadcast). Created before creatures start.
- **Runtime channels**: Creatures can create channels on-the-fly via `send_message` with a new channel name. Defaults to queue. Terrarium logs creation but doesn't block it.

This works naturally with `ChannelRegistry.get_or_create()` — the default is already queue.

---

## 4. Terrarium Runtime Architecture — Decided

### Single Process

All creatures are `Agent` instances sharing one Python event loop. Channels are `asyncio.Queue`-based (in-process). Multi-process/distributed can come later if needed.

### Runtime Responsibilities

```python
class TerrariumRuntime:
    """Pure wiring — no intelligence."""

    # 1. Load creature configs (unchanged)
    # 2. Pre-create declared channels with correct types
    # 3. For each creature:
    #    a. Append ChannelTrigger(s) for listen channels
    #    b. Ensure send_message/wait_channel tools registered
    #    c. Inject channel topology into system prompt
    #    d. Optionally attach output log capture
    # 4. Start all creatures
    # 5. Monitor lifecycle (restart on crash, budget enforcement)
    # 6. Expose interface API
```

### Terrarium Config Schema

```yaml
terrarium:
  name: string

  creatures:
    - name: string
      config: path              # path to standalone creature config
      channels:
        listen: [channel_names]  # → ChannelTriggers added
        can_send: [channel_names] # → documented in prompt
      output_log: bool           # optional transcript capture
      output_log_size: int       # ring buffer size

  channels:
    channel_name:
      type: queue | broadcast
      # future: schema, history_size

  interface:
    type: cli | web | mcp | none
    observe: [channel_names]
    inject_to: [channel_names]
```

---

## 5. Output Log System — Decided: Opt-In

Creature LLM output can be captured into a read-only ring buffer. Other creatures or the interface can query it for observability.

- Wraps the creature's existing OutputModule as a "tee" — everything still goes to the original output, plus gets logged.
- Accessed via `read_agent_log` tool or interface API.
- Opt-in per creature via `output_log: true` in terrarium config.
- Ring buffer with configurable size (`output_log_size`).

**Note**: This relaxes the "opaque" principle. Acceptable because it's opt-in and read-only.

**Implementation needed**: `OutputLogCapture` wrapper, `read_agent_log` tool.

---

## 6. Interface Design — Decided: Multi-Target API

### Core API

All interfaces (CLI, Web, MCP) share one `TerrariumAPI`:

```python
class TerrariumAPI:
    # Channels
    async def list_channels(self) -> list[ChannelInfo]
    async def read_channel(self, name, last_n=20) -> list[ChannelMessage]
    async def send_to_channel(self, name, content, sender="human") -> str

    # Creatures
    async def list_creatures(self) -> list[CreatureStatus]
    async def start_creature(self, name) -> None
    async def stop_creature(self, name) -> None
    async def get_creature_log(self, name, last_n=10) -> list[LogEntry]

    # Terrarium
    async def get_status(self) -> TerrariumStatus
    async def pause_all(self) -> None
    async def resume_all(self) -> None
```

### Interface Targets

| Target | Priority | Notes |
|--------|----------|-------|
| **CLI** | High | `terrarium status`, `terrarium send tasks "..."`. Human-friendly + `--json` for machines |
| **MCP Server** | High | Expose as MCP tools so Claude Code / Codex / OpenCode can manage terrarium natively |
| **Web UI** | Medium | Real-time dashboard, WebSocket for live channel stream |
| **None** | Built-in | Fully autonomous mode, no human interface |

### Agent CLI Compatibility

The CLI/MCP interface should feel natural for modern coding agents:
- Structured input/output (JSON mode)
- Tool-like API (MCP tools)
- Commands that map to what agents need: observe, inject, lifecycle control
- A human using Claude Code can say "check the terrarium status" and Claude Code calls MCP tools

---

## 7. Creature Failure & Restart — Open (Details TBD)

High-level decisions:
- **SubAgentChannel (queue)**: Messages persist in queue. Creature picks up on restart.
- **AgentChannel (broadcast)**: Subscription cleaned up on stop. Messages between crash and restart are missed.

### Open Questions

- **Replay buffer on AgentChannel**: Optional `history_size` parameter? Replay last N messages on resubscribe? (Useful for restarts, but adds complexity.)
- **Automatic restart**: Should the terrarium auto-restart crashed creatures? How many retries?
- **Conversation persistence**: Should creature conversation history survive restarts? (Currently lost.)
- **Graceful degradation**: If a creature in a pipeline crashes, how do upstream/downstream creatures handle it?

---

## 8. Cascade Control — Open (Details TBD)

On broadcast channels, one message can trigger all subscribers to respond, which triggers more messages, etc.

### Proposed Mechanisms

- **Per-creature cooldown**: After responding to a broadcast message, wait N seconds before processing the next. Configurable, default 0.
- **Global token budget**: Terrarium tracks total LLM calls/tokens. Pause when exceeded.
- **Self-message filtering**: Creature doesn't process its own broadcast messages. (`filter_sender` on ChannelTrigger already supports this.)

### Open Questions

- What are good defaults?
- Should budget be per-creature, per-terrarium, or both?
- Should the terrarium notify creatures when budget is low?

---

## 9. Channel Schema Validation — Open

Optional JSON schema validation on channel messages before delivery.

```yaml
channels:
  results:
    type: queue
    schema: ./schemas/completion_report.json
```

Messages failing validation could be: rejected (error back to sender), logged and delivered anyway, or held for review.

**Decision needed**: Is this worth the complexity? It adds safety but also friction.

---

## 10. Build Order

| Phase | What | Depends On |
|-------|------|-----------|
| **0** (done) | Channel redesign + testing module + integration tests | — |
| **1** | Terrarium runtime (config, lifecycle, trigger wiring, prompt injection) | Phase 0 |
| **2** | TerrariumAPI + CLI interface | Phase 1 |
| **3** | Output log system + `read_agent_log` tool | Phase 1 |
| **4** | MCP server interface | Phase 2 |
| **5** | Web UI | Phase 2 |
| **6** | Cascade control, replay buffer, schema validation | Phase 1 |

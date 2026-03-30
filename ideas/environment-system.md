# Environment-Session System Design

## The Real Problem

The terrarium currently forces all creatures to share ONE Session (same session_key). This means:

1. **Shared scratchpad** - Creature A's working notes are visible to Creature B
2. **Shared sub-agent channels** - If Creature A's sub-agent creates channel "temp", Creature B's sub-agent sees it
3. **No isolation between user requests** - Two terrariums with same name collide

The correct hierarchy is:

```
Environment (per user request)
  ├── Shared state (inter-creature channels, env config)
  │
  ├── Creature A → Session A (private scratchpad, private channels)
  ├── Creature B → Session B (private scratchpad, private channels)
  └── Creature C → Session C (private scratchpad, private channels)
```

### Concrete Conflict Examples

**Scratchpad collision:**
```python
# Creature A (planner) writes to scratchpad
scratchpad.set("plan", "5 chapters about time travel")

# Creature B (writer) reads scratchpad - sees planner's data!
plan = scratchpad.get("plan")  # Returns planner's plan, not writer's
```

**Sub-agent channel collision:**
```python
# Creature A's sub-agent creates channel "explore_results"
send_message(channel="explore_results", message="found auth.py")

# Creature B's sub-agent also uses "explore_results" - same channel!
# B's sub-agent receives A's results
```

## The Design: Environment + Session

### Environment

One Environment per user request (or per terrarium instance). Holds shared resources that all creatures in the terrarium can access.

```python
@dataclass
class Environment:
    """Isolated execution context. One per terrarium/user request."""

    env_id: str
    shared_channels: ChannelRegistry  # inter-creature channels
    _sessions: dict[str, Session] = field(default_factory=dict)
    _context: dict[str, Any] = field(default_factory=dict)

    def get_session(self, key: str) -> Session:
        """Get or create a creature-private session."""
        if key not in self._sessions:
            self._sessions[key] = Session(key=key)
        return self._sessions[key]

    def register(self, key: str, value: Any) -> None:
        """Modules register env-level shared state."""
        self._context[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Modules retrieve env-level shared state."""
        return self._context.get(key, default)
```

### Session

One Session per creature/agent. Holds private resources.

```python
@dataclass
class Session:
    """Private state for one creature/agent."""

    key: str
    channels: ChannelRegistry = field(default_factory=ChannelRegistry)  # sub-agent channels
    scratchpad: Scratchpad = field(default_factory=Scratchpad)
    extra: dict[str, Any] = field(default_factory=dict)
```

Note: Session already exists and has this shape. The change is that it's now explicitly creature-private, not shared across the terrarium.

### How They Connect

```
Environment (shared)
  ├── shared_channels: ChannelRegistry
  │     ├── "ideas" (queue)
  │     ├── "outline" (queue)
  │     └── "team_chat" (broadcast)
  │
  ├── Session "brainstorm" (private)
  │     ├── channels: ChannelRegistry (sub-agent channels only)
  │     └── scratchpad: Scratchpad
  │
  ├── Session "planner" (private)
  │     ├── channels: ChannelRegistry
  │     └── scratchpad: Scratchpad
  │
  └── Session "writer" (private)
        ├── channels: ChannelRegistry
        └── scratchpad: Scratchpad
```

### Channel Resolution

When a creature calls `send_message(channel="ideas")`:
1. Check creature's private session channels first (sub-agent channels)
2. If not found, check environment's shared channels (inter-creature channels)
3. If not found, error with listing of both

This gives natural namespacing:
- Private channels (created by sub-agents) stay private
- Shared channels (declared in terrarium config) are accessible to all
- No naming collision between private and shared

### How Tools Access Both Levels

The `ToolContext` needs to carry both:

```python
@dataclass
class ToolContext:
    agent_name: str
    session: Session         # creature-private (scratchpad, sub-agent channels)
    environment: Environment | None = None  # shared (inter-creature channels)
    working_dir: Path
    memory_path: Path | None = None
```

The `send_message` tool resolves channels from both:
```python
async def _execute(self, args, context):
    channel_name = args["channel"]

    # Try private channels first
    channel = context.session.channels.get(channel_name)

    # Fall back to shared environment channels
    if channel is None and context.environment:
        channel = context.environment.shared_channels.get(channel_name)

    # Auto-create in private (for sub-agent use)
    if channel is None:
        channel = context.session.channels.get_or_create(channel_name)

    await channel.send(msg)
```

### Registration Pattern

Modules register their own context at the appropriate level:

```python
# At environment level (shared across creatures):
env.register("terrarium_config", config)
env.register("budget_tracker", BudgetTracker())

# At session level (per creature):
session.extra["custom_state"] = MyState()
```

The Environment doesn't define what's in it. Modules register what they need. This keeps Environment generic and extensible.

## What Changes

### In Agent

```python
class Agent:
    def __init__(self, config, *, session=None, environment=None):
        # If session provided, use it (creature-private)
        # If not, create one (standalone agent)
        self.session = session or Session(key=config.name)
        self.environment = environment  # None for standalone agents
```

### In TerrariumRuntime

```python
class TerrariumRuntime:
    def __init__(self, config):
        self.environment = Environment(env_id=f"terrarium_{config.name}_{uuid}")

    def _build_creature(self, creature_cfg):
        # Each creature gets its OWN session (private)
        session = self.environment.get_session(creature_cfg.name)

        # Shared channels live in environment
        # Private channels live in session

        agent = Agent(config, session=session, environment=self.environment)
```

### In Executor / ToolContext

```python
def _build_tool_context(self):
    return ToolContext(
        agent_name=self._agent_name,
        session=self._session,         # creature-private
        environment=self._environment, # shared (may be None for standalone)
        working_dir=self._working_dir,
    )
```

### In send_message / wait_channel

Channel resolution: private first, then shared, then auto-create in private.

### In ChannelTrigger

Terrarium-level triggers listen on `environment.shared_channels`. Sub-agent triggers listen on `session.channels`.

## Standalone Agents (No Terrarium)

A standalone agent has a Session but no Environment:
```python
agent = Agent.from_path("agents/swe_agent")
# agent.session = Session(key="swe_agent")
# agent.environment = None
# All channels are in session.channels (private to this agent)
```

Everything works the same. The Environment layer is optional.

## Multi-User in KohakuManager

```python
class KohakuManager:
    async def create_terrarium(self, config_path, user_id=None):
        config = load_terrarium_config(config_path)
        # Each call gets a unique environment
        env_id = f"{config.name}_{user_id or uuid4().hex[:8]}"
        env = Environment(env_id=env_id)
        runtime = TerrariumRuntime(config, environment=env)
        ...
```

Two users creating the same terrarium get different environments, so no collision.

## Implementation Scope

| Change | Where | Size |
|--------|-------|------|
| `Environment` dataclass | New file: `core/environment.py` | ~50 lines |
| Agent accepts session + environment | `core/agent.py`, `core/agent_init.py` | ~20 lines |
| TerrariumRuntime creates Environment | `terrarium/runtime.py` | ~15 lines |
| ToolContext gets environment field | `modules/tool/base.py` | ~5 lines |
| Executor passes environment | `core/executor.py` | ~5 lines |
| send_message resolves from both levels | `builtins/tools/send_message.py` | ~15 lines |
| wait_channel resolves from both levels | `builtins/tools/wait_channel.py` | ~15 lines |
| ChannelTrigger uses correct registry | `modules/trigger/channel.py` | ~10 lines |
| KohakuManager creates unique envs | `serving/manager.py` | ~10 lines |

Total: ~150 lines of changes + 1 new file (~50 lines).

## Key Principles

1. **Environment = shared** - inter-creature channels, terrarium config, budget
2. **Session = private** - scratchpad, sub-agent channels, creature-local state
3. **Standalone agents** - Session only, no Environment (backward compatible)
4. **Registration pattern** - modules register their own context, Environment is generic
5. **Channel resolution** - private first, shared second, auto-create in private
6. **No global state** - Environment and Session are explicit parameters, not global lookups

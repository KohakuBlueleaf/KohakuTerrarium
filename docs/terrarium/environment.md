# Environment-Session System

Two-level isolation for running multiple agents and terrariums safely in one process.

## The Problem

Without isolation, two agents sharing the same session key would collide on channels and scratchpad. Two creatures in the same terrarium would see each other's sub-agent channels and working memory.

## Two Levels

| Level | Scope | Holds | Example |
|-------|-------|-------|---------|
| **Environment** | Per terrarium / per user request | Shared channels (inter-creature) | `ideas`, `outline`, `team_chat` |
| **Session** | Per creature / per agent | Private channels (sub-agent), scratchpad | `explore_results`, working notes |

```
Environment (shared)
  ├── shared_channels: ChannelRegistry
  │     ├── "ideas" (queue) - brainstorm -> planner
  │     ├── "outline" (queue) - planner -> writer
  │     └── "team_chat" (broadcast) - all
  │
  ├── Session "brainstorm" (private)
  │     ├── channels: ChannelRegistry (sub-agent only)
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

## Programmatic Usage

### Standalone Agent (No Environment)

Standalone agents have a Session but no Environment. All channels are private.

```python
from kohakuterrarium.core.agent import Agent

# Session is auto-created from config name
agent = Agent.from_path("agents/swe_agent")
# agent.session = Session(key="swe_agent")
# agent.environment = None
```

### Standalone Agent with Explicit Session

```python
from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.session import Session

# Create a session with a unique key (for multi-user)
session = Session(key="user_123_swe_agent")
agent = Agent.from_path("agents/swe_agent", session=session)

# Agent uses this session's scratchpad and channels
agent.session.scratchpad.set("task", "fix auth bug")
```

### Terrarium with Environment

The terrarium runtime creates an Environment automatically. Each creature gets its own Session.

```python
from kohakuterrarium.terrarium import TerrariumRuntime, load_terrarium_config

config = load_terrarium_config("agents/novel_terrarium")
runtime = TerrariumRuntime(config)
await runtime.start()

# Environment was created
env = runtime.environment

# Shared channels (inter-creature)
shared = env.shared_channels.list_channels()
# ['ideas', 'outline', 'draft', 'feedback', 'team_chat']

# Each creature has a private session
brainstorm_session = env.get_session("brainstorm")
planner_session = env.get_session("planner")

# Private scratchpads are isolated
brainstorm_session.scratchpad.set("notes", "brainstorm's private notes")
assert planner_session.scratchpad.get("notes") is None  # not visible
```

### Custom Environment (Advanced)

Create an Environment explicitly for full control:

```python
from kohakuterrarium.core.environment import Environment

env = Environment(env_id="my_custom_env")

# Pre-create shared channels
env.shared_channels.get_or_create("tasks", channel_type="queue", description="Work items")
env.shared_channels.get_or_create("events", channel_type="broadcast", description="Status")

# Register custom shared state
env.register("budget", {"max_calls": 100, "used": 0})

# Pass to terrarium
runtime = TerrariumRuntime(config, environment=env)
await runtime.start()

# Or pass to standalone agent
agent = Agent.from_path("agents/swe_agent", environment=env, session=env.get_session("my_agent"))
```

### Multi-User Isolation

Two users in the same process get separate environments:

```python
from kohakuterrarium.serving import KohakuManager

manager = KohakuManager()

# User A creates a terrarium - gets unique environment
tid_a = await manager.create_terrarium("agents/novel_terrarium")

# User B creates the same terrarium - gets a DIFFERENT environment
tid_b = await manager.create_terrarium("agents/novel_terrarium")

# No collision: different shared channels, different creature sessions
```

### Accessing Environment from Tools

Tools receive both session (private) and environment (shared) via `ToolContext`:

```python
class MyTool(BaseTool):
    needs_context = True

    async def _execute(self, args, context=None):
        # Private scratchpad
        context.session.scratchpad.set("key", "private value")

        # Shared channels (if in a terrarium)
        if context.environment:
            shared = context.environment.shared_channels.get("ideas")
            budget = context.environment.get("budget")
```

## Channel Resolution

When a tool like `send_message` resolves a channel name:

1. **Private session channels** - checked first (sub-agent internal channels)
2. **Shared environment channels** - checked second (inter-creature channels)
3. **Auto-create in private** - if not found anywhere, creates a queue in the session
4. **Conflict validation** - if a shared channel has the same name, auto-create is blocked with an error

This means:
- Sub-agent channels stay private automatically
- Terrarium channels are accessible to all creatures
- No accidental shadowing of shared channels by private ones

## Registration Pattern

Modules can register their own state at the environment level:

```python
# Budget tracker registers itself
env.register("budget_tracker", BudgetTracker(max_calls=100))

# Later, any tool or module in the environment can access it
tracker = env.get("budget_tracker")
tracker.record_call()
```

The Environment doesn't define what state it holds. Modules register what they need. This keeps Environment generic and extensible without modifying its class definition.

# Environment System Design

## The Problem

Running multiple independent agent/terrarium sessions in one process requires state isolation. Without it, two users creating agents would share channels, scratchpad, and logging state.

## Investigation Results

Comprehensive code analysis found **3 critical globals** and **many safe per-instance components**.

### Critical Global State (Must Fix)

| Global | File | Problem |
|--------|------|---------|
| `_sessions` dict | `core/session.py:51` | Two agents with same key share channels/scratchpad |
| `_global_registry` singleton | `core/registry.py:106` | Shared tool registry (but agents already bypass it - they create per-agent Registry) |
| `_handler` / `set_level()` | `utils/logging.py:153` | Log level and handler are process-global |

### Already Safe (Per-Instance)

| Component | Why It's Safe |
|-----------|--------------|
| Agent.registry | Created fresh per agent in `_init_registry()` |
| Agent.executor / JobStore | Per-agent instance |
| Agent.controller / Conversation | Per-agent instance |
| LLM provider / httpx client | Per-agent instance |
| Builtin tool registry | Read-only post-import, returns new instances per call |
| Builtin input/output registries | Read-only post-import |
| Jinja2 Environment | Stateless, thread-safe |
| Parsing constants | Never modified |
| KohakuManager dicts | Per-manager instance |

### The Real Scope

Only `_sessions` is a true blocker. The global registry is bypassed by agents. Logging is a UX issue (mixed output) but not a correctness issue.

## Do We Need a Full Environment System?

**No.** The investigation shows most state is already per-instance. The only real problem is the session registry.

Two options:

### Option A: Fix Session Only (Minimal, Recommended)

Pass session explicitly instead of relying on the global `_sessions` dict:

```python
# Current (global lookup):
session = get_session("my_key")  # reads from module-level _sessions dict

# Fixed (explicit):
agent = Agent(config, session=Session(key="unique_per_user"))
# Agent passes session to executor, tools, etc.
```

This is already almost how it works. Agents get their session via `session_key` in config. The terrarium creates a session and shares it. The only issue is that `get_session()` is a global function that two callers with the same key would collide on.

Fix: make session an explicit parameter rather than a global lookup. The `_sessions` dict becomes a convenience for simple single-user cases, not the source of truth.

**Changes needed:**
- `Agent.__init__` accepts optional `session` parameter
- If provided, use it directly instead of calling `get_session(session_key)`
- `TerrariumRuntime` creates a `Session()` directly and passes it to agents
- Tools get session via `ToolContext.session` (already works)
- Remove `get_channel_registry()` global function (use `context.session.channels`)

~50 lines of changes. No new abstractions.

### Option B: Full Environment System (Comprehensive)

A new `Environment` class that holds all per-session state:

```python
class Environment:
    """Isolated execution context for one user session."""

    def __init__(self, name: str):
        self.name = name
        self.sessions: dict[str, Session] = {}
        self._context: dict[str, Any] = {}

    def get_session(self, key: str | None = None) -> Session:
        k = key or "__default__"
        if k not in self.sessions:
            self.sessions[k] = Session(key=k)
        return self.sessions[k]

    def register(self, key: str, value: Any) -> None:
        """Modules register their own context."""
        self._context[key] = value

    def get(self, key: str) -> Any:
        return self._context.get(key)
```

Usage:
```python
env = Environment("user_123")
agent = Agent(config, environment=env)
terrarium = TerrariumRuntime(config, environment=env)
```

**This adds complexity but gains:**
- Clean isolation boundary
- Extensible (modules register their own state)
- Multiple users per process without collision
- Environment can be serialized/restored for persistence

**The registration pattern** means we don't define what goes in the environment. Modules register what they need:
```python
# In channel module:
env.register("channel_registry", ChannelRegistry())

# In scratchpad module:
env.register("scratchpad", Scratchpad())

# Any module can access:
channels = env.get("channel_registry")
```

But this is over-engineered for the current problem. Session already IS the per-agent/per-terrarium context container. It has channels, scratchpad, tui, and an extras dict.

## Recommendation

**Go with Option A (fix Session) now.** The Session class already IS an environment - it has channels, scratchpad, and extras. The only problem is the global `_sessions` dict.

Fix:
1. Let Agent/TerrariumRuntime accept an explicit `Session` object
2. Stop relying on the global `get_session()` for multi-user scenarios
3. Keep `get_session()` as a convenience for single-user/CLI usage
4. Each KohakuManager user session creates its own Session and passes it through

If we later need more isolation (e.g., per-user logging, per-user config), we can wrap Session into an Environment class. But don't build that until we need it.

## Multi-Session in KohakuManager

The serving layer already handles this correctly IF we use unique session keys:

```python
class KohakuManager:
    async def create_agent(self, config_path, session_id=None):
        # Generate unique session key per user
        session_key = session_id or f"session_{uuid4().hex[:8]}"
        config = load_agent_config(config_path)
        config.session_key = session_key  # unique per call

        # Now this agent has its own session, channels, scratchpad
        session = await AgentSession.from_config(config)
        ...
```

Two users calling `create_agent("agents/swe_agent")` get different session keys, so different sessions, so no collision.

The terrarium already does this: `self._session_key = f"terrarium_{config.name}"`. Just make the name unique per call (add a UUID suffix).

## What About Logging?

Logging is process-global by design in Python. Options:
1. **Accept it** - all agents log to same stderr, differentiated by logger name (module path). This is the Python standard.
2. **Per-agent log files** - agents can set up their own file handlers. This is an application concern, not a framework concern.
3. **Structured logging** - already done. Each log message includes agent_name, creature name, etc. A log aggregator can filter by these.

Recommendation: keep logging as-is. It's a presentation concern for the application layer (web app can capture and route logs per session).

## Implementation Summary

| Change | Where | Lines |
|--------|-------|-------|
| Agent accepts optional `session` param | `core/agent_init.py` | ~10 |
| TerrariumRuntime creates Session directly | `terrarium/runtime.py` | ~5 |
| KohakuManager uses unique session keys | `serving/manager.py` | ~10 |
| Deprecate global `get_session()` for multi-user | `core/session.py` | ~5 |

Total: ~30 lines of changes. No new modules. No new abstractions.

The Session class IS the environment. We just need to pass it explicitly instead of looking it up globally.

# serving/

Core service API for hosting and managing agents and terrariums.
Transport-agnostic: used by any interface layer (CLI, TUI, Web API, Gradio).
`KohakuManager` is the single entry point for all runtime operations,
including agent lifecycle, terrarium lifecycle, creature hot-plug, and
channel interactions. `AgentSession` wraps a standalone agent with streaming
chat. Event types are plain dataclasses usable across transport boundaries.

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Re-exports `KohakuManager`, `AgentSession`, `OutputEvent`, `ChannelEvent` |
| `manager.py` | `KohakuManager`: unified service manager with `agent_*`, `terrarium_*`, `creature_*` method hierarchy |
| `agent_session.py` | `AgentSession`: wraps Agent with input injection and async output streaming |
| `events.py` | `OutputEvent` (text chunk, tool activity) and `ChannelEvent` (observed channel message) dataclasses |

## Dependencies

- `kohakuterrarium.core.agent` (Agent)
- `kohakuterrarium.core.channel` (AgentChannel, ChannelMessage)
- `kohakuterrarium.core.config` (AgentConfig)
- `kohakuterrarium.core.environment` (Environment)
- `kohakuterrarium.session.store` (SessionStore)
- `kohakuterrarium.terrarium` (TerrariumRuntime, TerrariumConfig, ChannelObserver)
- `kohakuterrarium.utils.logging`

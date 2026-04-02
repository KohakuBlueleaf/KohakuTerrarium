# terrarium/

Multi-agent orchestration runtime. The terrarium is a pure wiring layer with
no intelligence: it loads standalone creature configs, creates channels between
them, injects channel triggers, and manages lifecycle. The runtime is split
across focused modules for creature construction, hot-plug operations, channel
observation, session persistence, and a programmatic API facade.

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Re-exports runtime, config, hot-plug, observer, output log, and API classes |
| `runtime.py` | `TerrariumRuntime`: lifecycle orchestration (start, stop, channel wiring) with `HotPlugMixin` |
| `config.py` | `TerrariumConfig`, `CreatureConfig`, `ChannelConfig`, `load_terrarium_config`, `build_channel_topology_prompt` |
| `creature.py` | `CreatureHandle`: wrapper around an Agent with terrarium metadata (channels, config) |
| `factory.py` | `build_creature`, `build_root_agent`: construct Agent instances from config, wire triggers and topology prompts |
| `hotplug.py` | `HotPlugMixin`: add/remove creatures and channels at runtime without restart |
| `observer.py` | `ChannelObserver`, `ObservedMessage`: non-destructive channel message recording |
| `output_log.py` | `OutputLogCapture`, `LogEntry`: tee wrapper that captures creature output for observability |
| `persistence.py` | `attach_session_store`, `build_conversation_from_messages`: session store wiring and resume helpers |
| `tool_manager.py` | `TerrariumToolManager`: shared state for terrarium management tools (stored in environment) |
| `tool_registration.py` | `ensure_terrarium_tools_registered`: lazy import of terrarium tools to avoid circular imports |
| `api.py` | `TerrariumAPI`: programmatic facade for channel ops, creature lifecycle, and status queries |
| `cli.py` | CLI subcommands for terrarium management (`terrarium run`, `terrarium resume`) |

## Dependencies

- `kohakuterrarium.builtins.inputs` (NoneInput for trigger-only creatures)
- `kohakuterrarium.builtins.tool_catalog` (get_builtin_tool for root agent)
- `kohakuterrarium.core.agent` (Agent)
- `kohakuterrarium.core.channel` (AgentChannel, ChannelMessage, ChannelRegistry)
- `kohakuterrarium.core.config` (build_agent_config)
- `kohakuterrarium.core.conversation` (Conversation)
- `kohakuterrarium.core.environment` (Environment)
- `kohakuterrarium.core.session` (Session)
- `kohakuterrarium.modules.output.base` (OutputModule)
- `kohakuterrarium.modules.trigger.channel` (ChannelTrigger)
- `kohakuterrarium.session.store` (SessionStore)
- `kohakuterrarium.utils.logging`

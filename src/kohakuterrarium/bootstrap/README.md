# bootstrap/

Bootstrap factories for agent component initialization. Each module contains
a focused factory function that creates one agent subsystem from an `AgentConfig`,
reducing the import fan-out of `core/agent_init.py`. These factories handle
builtin, custom, and package module types with graceful fallbacks on failure.

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Package docstring |
| `io.py` | Input and output module factories with fallback to CLI/stdout |
| `llm.py` | LLM provider factory (Codex OAuth or standard OpenAI-compatible) |
| `subagents.py` | Sub-agent config creation and registration into manager and registry |
| `tools.py` | Tool instance creation and registration into the module registry |
| `triggers.py` | Trigger creation (timer, context, channel, custom) and registration |

## Dependencies

- `kohakuterrarium.builtins.inputs` (CLIInput, factory helpers)
- `kohakuterrarium.builtins.outputs` (StdoutOutput, factory helpers)
- `kohakuterrarium.builtins.tool_catalog` (get_builtin_tool)
- `kohakuterrarium.builtins.subagent_catalog` (get_builtin_subagent_config)
- `kohakuterrarium.core.config` (AgentConfig)
- `kohakuterrarium.core.loader` (ModuleLoader)
- `kohakuterrarium.core.registry` (Registry)
- `kohakuterrarium.core.session` (Session)
- `kohakuterrarium.core.trigger_manager` (TriggerManager)
- `kohakuterrarium.llm` (LLMProvider, OpenAIProvider, CodexOAuthProvider)
- `kohakuterrarium.modules.input.base` (InputModule)
- `kohakuterrarium.modules.output.base` (OutputModule)
- `kohakuterrarium.modules.subagent` (SubAgentManager, SubAgentConfig)
- `kohakuterrarium.modules.trigger` (BaseTrigger, TimerTrigger, ContextUpdateTrigger, ChannelTrigger)
- `kohakuterrarium.utils.logging`

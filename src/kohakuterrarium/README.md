# kohakuterrarium

Root package for the KohakuTerrarium agent framework.

## Top-Level Files

- `__init__.py` -- Package marker, version info
- `__main__.py` -- CLI entry point (`kt run`, `kt terrarium`, `kt resume`, `kt login`)

## Subpackages

| Package | Purpose |
|---------|---------|
| `core/` | Agent, Controller, Executor, events, config, session, registry |
| `bootstrap/` | Agent initialization factories (llm, tools, io, subagents, triggers) |
| `builtins/` | Built-in tool/subagent/input/output implementations + catalogs |
| `builtin_skills/` | On-demand markdown documentation for tools and sub-agents |
| `modules/` | Base classes and protocols (input, output, tool, trigger, subagent) |
| `terrarium/` | Multi-agent runtime: config, factory, persistence, hot-plug, observer |
| `serving/` | Transport-agnostic service layer (KohakuManager, AgentSession) |
| `session/` | Session persistence via KohakuVault (.kohakutr files) |
| `llm/` | LLM provider abstraction (OpenAI SDK, Codex OAuth) |
| `parsing/` | Streaming state machine for LLM output (bracket, XML, native) |
| `prompt/` | System prompt aggregation, Jinja2 templating, plugin system |
| `commands/` | Framework commands executed inline during LLM streaming (read, info, jobs, wait) |
| `testing/` | Test infrastructure (ScriptedLLM, TestAgentBuilder, output recorders) |
| `utils/` | Shared utilities (structured logging, async helpers, file safety guards) |

## Dependency Flow

```
             CLI (__main__)
                 |
            core/agent
           /    |     \
   bootstrap  controller  terrarium/runtime
      |          |              |
   builtins    parsing    terrarium/factory
      |          |              |
   modules     llm         core/agent
      |
    utils (leaf)
```

Key principles:
- `utils/` is a leaf: imported by everything, imports nothing from the framework
- `builtins/tool_catalog` and `builtins/subagent_catalog` are leaf modules for internal use
- `bootstrap/` reduces `core/agent_init` fan-out by encapsulating factory logic
- `terrarium/` imports `core/` but core never imports terrarium (one-way dependency)
- Zero runtime import cycles (verified via `scripts/dep_graph.py`)

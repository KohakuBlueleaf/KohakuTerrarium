# KohakuTerrarium Documentation

## Guide
Build agents and terrariums with the framework.
- [Getting Started](guide/getting-started.md): install, auth, first agent, session persistence, web dashboard
- [Configuration Reference](guide/configuration.md): agent YAML, terrarium YAML, all fields
- [Creatures](guide/creatures.md): pre-built creatures, inheritance, creating your own
- [Example Agents](guide/example-agents.md): walkthrough of included example agents and terrariums

## Concepts
Learn what the key abstractions are and how they relate.
- [Overview](concept/README.md)
- [Creatures and Agents](concept/creature.md)
- [Terrarium (Multi-Agent)](concept/terrarium.md)
- [Channels](concept/channels.md): queue/broadcast types, channel triggers, on_send callbacks
- [Environment-Session](concept/environment.md)
- [Tool Formats](concept/tool-formats.md)

## Architecture
Understand how the system works internally.
- [Overview](architecture/README.md): four layers (framework, session, terrarium, serving)
- [Framework Internals](architecture/framework.md): agent, controller, executor, session output, token tracking
- [Execution Model](architecture/execution-model.md): event sources, processing loop, tool modes
- [Terrarium Runtime](architecture/terrarium-runtime.md): config, lifecycle, hot-plug, session persistence
- [Serving Layer](architecture/serving.md): KohakuManager, unified WebSocket, session recording
- [Prompt System](architecture/prompt-system.md): system prompt aggregation, skill modes, terrarium topology injection

## API Reference
Look up specific methods, endpoints, and commands.
- [Python API](api-reference/python.md): Agent, SessionStore, TerrariumRuntime, all modules
- [HTTP API](api-reference/http.md): REST + unified WebSocket + config discovery
- [CLI Reference](api-reference/cli.md): kt run, kt resume, kt terrarium run, kt login

## Contributing
Work on the framework itself.
- [Testing](develop/testing.md)

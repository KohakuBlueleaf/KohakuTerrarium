# Creature - The Self-Contained Agent

## The Idea

A creature is a complete, self-contained agent. It has everything it needs to operate independently: an LLM brain, tools to interact with the world, sub-agents for delegation, and memory for persistence.

The name "creature" comes from the terrarium metaphor. You build a creature, test it standalone, then place it in a terrarium where it collaborates with others. The creature does not change - it does not know it is in a terrarium.

## Anatomy of a Creature

```
                    +---------------------------+
                    |        Creature            |
                    |                           |
Input ------+       |   +-------------------+   |
            +------>|   |   Controller      |   |
Trigger ----+       |   |   (LLM brain)     |   |
                    |   +--------+----------+   |
                    |            |               |
                    |   +--------v----------+   |
                    |   |  Dispatches to:    |   |
                    |   |  - Tools (parallel)|   |
                    |   |  - Sub-agents      |   |       +--------+
                    |   +--------+----------+   +------>| Output |
                    |            |               |       +--------+
                    |   +--------v----------+   |
                    |   | Results feed back  |   |
                    |   | to controller for  |   |
                    |   | next decision      |   |
                    |   +-------------------+   |
                    +---------------------------+
```

**Input** brings events from the outside: user typing, API calls, speech.

**Triggers** generate events automatically: timers, channel messages, conditions.

**Controller** is the LLM. It receives events, thinks, and dispatches work. It orchestrates but does not do heavy work itself.

**Tools** execute actions: read files, run shell commands, search code, send messages. They start immediately during LLM streaming and run in parallel.

**Sub-agents** are nested creatures with their own LLM and limited tools. The controller delegates complex subtasks to them.

**Output** routes the controller's text to the right destination: terminal, TTS, Discord, named API endpoints.

## The Controller Pattern

The controller is the brain, but its job is to **dispatch, not execute**.

```
Good:  Controller decides -> calls bash tool -> gets result -> decides next step
Bad:   Controller writes a 2000-word essay in one response
```

Long outputs (user-facing content, prose, detailed analysis) should come from **output sub-agents**, not from the controller directly. This keeps the controller lightweight and its context window small.

## Everything Is an Event

All inputs flow through the same `TriggerEvent` type:

```
User types "hello"        -> TriggerEvent(type="user_input")
Timer fires               -> TriggerEvent(type="timer")
Tool finishes             -> TriggerEvent(type="tool_complete")
Channel message arrives   -> TriggerEvent(type="channel_message")
Sub-agent returns         -> TriggerEvent(type="subagent_output")
```

This unified model keeps the controller loop simple: receive event, call LLM, dispatch results, repeat.

## Sub-Agents - Nested Hierarchy

A creature can delegate to sub-agents, which are smaller creatures with restricted capabilities:

```
Controller (full access)
  |
  +-- explore sub-agent (read-only tools: glob, grep, read)
  |
  +-- worker sub-agent (write tools: edit, write, bash)
  |
  +-- critic sub-agent (read-only, reviews worker's output)
```

Sub-agents have their own LLM conversation and tool registry. They return results to the parent controller. This is the **vertical hierarchy** - task decomposition within one creature.

## Defining a Creature

A creature is defined by a YAML config and a system prompt:

```yaml
name: swe_agent
controller:
  model: google/gemini-3-flash-preview
  tool_format: native
system_prompt_file: prompts/system.md
input: { type: cli }
tools:
  - name: bash
  - name: read
  - name: write
subagents:
  - name: explore
  - name: plan
```

The system prompt defines personality and workflow. The tool list and call syntax are auto-generated - never write them in the prompt manually.

See [Configuration Reference](../guide/configuration.md) for all fields. See [Example Agents](../guide/example-agents.md) for walkthroughs.

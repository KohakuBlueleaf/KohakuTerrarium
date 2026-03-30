# Example Agents

This guide walks through the example agents included in the `agents/` folder, explaining their architecture and patterns.

## SWE Agent (`agents/swe_agent/`)

A software engineering assistant similar to Claude Code or Cursor.

### Purpose
Help users with coding tasks: reading code, finding patterns, running commands, editing files.

### Architecture Pattern
**Direct Controller Output** - Controller's text output goes directly to stdout.

```
User -> Controller (LLM) -> Tools -> Result back to Controller -> stdout
```

### Key Configuration

```yaml
name: swe_agent

controller:
  model: "google/gemini-3-flash-preview"
  temperature: 0.7
  max_tokens: 512000

input:
  type: cli
  prompt: "You: "

tools:
  - name: bash
    type: builtin
  - name: python
    type: builtin
  - name: read
    type: builtin
  - name: write
    type: builtin
  - name: edit
    type: builtin
  - name: glob
    type: builtin
  - name: grep
    type: builtin

subagents:
  - name: explore
    type: builtin
  - name: plan
    type: builtin

output:
  type: stdout
  controller_direct: true
```

### Key Features

1. **Full tool suite**: All file operation tools for complete coding capability
2. **Sub-agents for complex tasks**: `explore` for codebase search, `plan` for implementation planning
3. **Direct output**: Controller's thinking goes to stdout (no output sub-agent needed)

---

## SWE Agent TUI (`agents/swe_agent_tui/`)

Same as the SWE Agent but uses TUI input/output for a richer terminal experience.

### Architecture Pattern
**TUI Input/Output** - Shared TUI session via the session registry.

```yaml
input:
  type: tui
  prompt: "You: "

output:
  type: tui
  controller_direct: true
```

TUI input and output share a `TUISession` instance via `Session.tui` for coordinated terminal access. Same tools and sub-agents as `swe_agent`.

---

## Discord Bot (`agents/discord_bot/`)

A group chat bot with memory, character, and autonomous triggers.

### Purpose
Participate in Discord group chats as a roleplay character with persistent memory.

### Architecture Pattern
**Ephemeral Mode with Named Output** - Conversation cleared after each interaction, output via explicit blocks.

```
Discord Message -> Controller (ephemeral) -> [/output_discord]response[output_discord/] -> Discord
                                          |
                                 (conversation cleared)
```

### Key Features

1. **Ephemeral mode**: Each interaction is independent, no conversation carryover
2. **Named output**: Must use `[/output_discord]...[output_discord/]` to send messages
3. **Context injection**: Character and rules injected via context_files (closer to generation)
4. **Multimodal**: Processes images in Discord messages
5. **Idle trigger**: Autonomous messages after chat inactivity
6. **Memory system**: Persistent character, rules, and facts across sessions
7. **Custom tools**: Guild emoji search

Plain text = internal thinking (not sent). To send to Discord:
```
[/output_discord]Hello everyone![output_discord/]
```

---

## RP Agent (`agents/rp_agent/`)

A roleplay chatbot with output sub-agent pattern.

### Purpose
Roleplay as a character with memory and in-character response generation.

### Architecture Pattern
**Output Sub-Agent** - Controller orchestrates, output sub-agent generates responses.

```
User -> Controller (orchestrator) -> memory_read -> context
                                  -> output sub-agent -> stdout (as character)
```

### Key Features

1. **Startup trigger**: Automatically loads character on start
2. **Interactive output sub-agent**: Stays alive, receives context updates
3. **Separation of concerns**: Controller orchestrates, output sub-agent speaks
4. **External output**: Sub-agent's output goes directly to user (not back to controller)
5. **Context mode**: `interrupt_restart` - stops current response when new context arrives

| Aspect | Controller | Output Sub-Agent |
|--------|------------|------------------|
| Role | Orchestrator | Response generator |
| Output | Internal | External (to user) |
| Tools | Full access | None |
| Persistence | Per-session | Interactive (long-lived) |

---

## Conversational Agent (`agents/conversational/`)

A streaming conversational AI with voice input/output.

### Architecture Pattern
**Voice Pipeline** - ASR input, streaming LLM, TTS output.

```
Audio -> Whisper ASR -> Controller -> TTS -> Audio Output
```

### Key Features

1. **Whisper ASR input**: Real-time speech-to-text with VAD
2. **Streaming TTS output**: Text-to-speech as response generates
3. **Interactive sub-agent**: Long-lived for natural conversation flow
4. **Memory integration**: Remembers conversation context

---

## Architectural Patterns Summary

### Pattern 1: Direct Output (SWE Agent)
```yaml
output:
  type: stdout
  controller_direct: true
```
Best for: CLI tools, coding assistants

### Pattern 2: Ephemeral + Named Output (Discord Bot)
```yaml
controller:
  ephemeral: true
output:
  named_outputs:
    discord:
      type: custom
```
Best for: Group chats, stateless interactions

### Pattern 3: Output Sub-Agent (RP Agent)
```yaml
subagents:
  - name: output
    interactive: true
    output_to: external
output:
  controller_direct: false
```
Best for: Character bots, streaming responses

### Pattern 4: Voice Pipeline (Conversational)
```yaml
input:
  type: whisper
output:
  type: tts
```
Best for: Voice assistants, real-time conversation

### Pattern 5: TUI Mode (SWE Agent TUI)
```yaml
input:
  type: tui
output:
  type: tui
  controller_direct: true
```
Best for: Interactive terminal agents with richer I/O control

### Pattern 6: Trigger-Only (Monitor Agent)
```yaml
input:
  type: none
triggers:
  - type: timer
    interval: 60
```
Best for: Autonomous monitoring, background processing, event-driven agents

---

## Creating Your Own Agent

1. **Choose a pattern** based on your use case
2. **Create folder structure**:
   ```
   agents/my_agent/
   +-- config.yaml
   +-- prompts/
   |   +-- system.md
   +-- memory/       (optional)
   +-- custom/       (optional)
   ```
3. **Start with builtin modules**, add custom as needed
4. **Test incrementally** - start with CLI input, add complexity

---

## Common Minimal Configurations

### Minimal SWE Agent
```yaml
name: minimal_swe
controller:
  model: "gpt-4o-mini"
  api_key_env: OPENAI_API_KEY
input:
  type: cli
output:
  type: stdout
tools:
  - name: bash
    type: builtin
  - name: read
    type: builtin
```

### Minimal Chat Bot
```yaml
name: minimal_chat
controller:
  model: "gpt-4o-mini"
  api_key_env: OPENAI_API_KEY
  ephemeral: true
input:
  type: cli
output:
  type: stdout
  named_outputs:
    chat:
      type: stdout
```

### With Memory
```yaml
memory:
  path: ./memory
  init_files:
    - character.md
  writable_files:
    - context.md
subagents:
  - name: memory_read
    type: builtin
  - name: memory_write
    type: builtin
```

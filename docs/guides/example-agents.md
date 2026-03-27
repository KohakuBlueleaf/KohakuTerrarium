# Example Agents

This guide walks through the example agents included in the `agents/` folder, explaining their architecture and patterns.

## SWE Agent (`agents/swe_agent/`)

A software engineering assistant similar to Claude Code or Cursor.

### Purpose
Help users with coding tasks: reading code, finding patterns, running commands, editing files.

### Architecture Pattern
**Direct Controller Output** - Controller's text output goes directly to stdout.

```
User → Controller (LLM) → Tools → Result back to Controller → stdout
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
  controller_direct: true  # Controller output goes to stdout
```

### Key Features

1. **Full Tool Suite**: All file operation tools for complete coding capability
2. **Sub-agents for Complex Tasks**: `explore` for codebase search, `plan` for implementation planning
3. **Direct Output**: Controller's thinking goes to stdout (no output sub-agent needed)

### Usage Example

```
You: Find all Python files that import asyncio

I'll search for Python files that import asyncio.

[/grep]@@pattern=import asyncio[grep/]

Found 15 files importing asyncio:
- src/core/agent.py
- src/core/executor.py
...
```

---

## Discord Bot (`agents/discord_bot/`)

A group chat bot with memory, character, and autonomous triggers.

### Purpose
Participate in Discord group chats as a roleplay character with persistent memory.

### Architecture Pattern
**Ephemeral Mode with Named Output** - Conversation cleared after each interaction, output via explicit blocks.

```
Discord Message → Controller (ephemeral) → [/output_discord]response[output_discord/] → Discord
                                        ↓
                              (conversation cleared)
```

### Key Configuration

```yaml
name: discord_bot

controller:
  model: "google/gemini-3-flash-preview"
  temperature: 1
  ephemeral: true              # Clear conversation after each interaction
  max_messages: 256
  max_context_chars: 2000000

input:
  type: custom
  module: ./custom/discord_io.py
  class: DiscordInputModule
  channel_ids: [775002061456408576]
  history_limit: 64            # Older messages for background
  recent_limit: 12             # Recent messages with numbering
  instant_memory_file: ./memory/context.md
  context_format_file: ./prompts/context_format.md
  context_files:
    character: ./memory/character.md
    rules: ./memory/rules.md
  include_images: true         # Multimodal support

output:
  type: stdout                 # Default for thinking

  named_outputs:
    discord:
      type: custom
      module: ./custom/discord_io.py
      class: DiscordOutputModule
      keywords_file: ./filtered_keywords.txt
      drop_base_chance: 0.25   # Drop outdated responses

triggers:
  - type: custom
    module: ./custom/discord_trigger.py
    class: DiscordIdleTrigger
    min_idle_seconds: 1800     # 30 minutes
    max_idle_seconds: 28800    # 8 hours
    prompt: "The chat has been quiet..."

tools:
  - name: tree
    type: builtin
  - name: read
    type: builtin
  - name: write
    type: builtin
  - name: emoji_search
    type: custom
    module: ./custom/emoji_search.py
    class: EmojiSearchTool

subagents:
  - name: memory_read
    type: builtin
  - name: memory_write
    type: builtin

memory:
  path: ./memory
  init_files:
    - character.md             # Read-only character definition
    - rules.md                 # Protected rules
  writable_files:
    - context.md               # Current context
    - facts.md                 # Remembered facts
```

### Key Features

1. **Ephemeral Mode**: Each interaction is independent - no conversation carryover
2. **Named Output**: Must use `[/output_discord]...[output_discord/]` to send messages
3. **Context Injection**: Character and rules injected via context_files (closer to generation)
4. **Multimodal**: Processes images in Discord messages
5. **Idle Trigger**: Autonomous messages after chat inactivity
6. **Memory System**: Persistent character, rules, and facts across sessions
7. **Custom Tools**: Guild emoji search

### Output Model

Plain text = internal thinking (not sent)

To send to Discord:
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
User → Controller (orchestrator) → memory_read → context
                                 → output sub-agent → stdout (as character)
```

### Key Configuration

```yaml
name: rp_agent

controller:
  model: "google/gemini-3-flash-preview"
  temperature: 0.7
  max_tokens: 65536

system_prompt_file: prompts/system.md

# Initialize character on startup
startup_trigger:
  prompt: "Agent starting. Use memory_read to get your character definition."

input:
  type: cli
  prompt: "User: "

tools:
  - name: tree
    type: builtin
  - name: read
    type: builtin
  - name: write
    type: builtin
  - name: edit
    type: builtin
  - name: grep
    type: builtin
  - name: glob
    type: builtin

subagents:
  - name: memory_read
    type: builtin
  - name: memory_write
    type: builtin

  # Interactive output sub-agent
  - name: output
    type: custom
    description: Generate in-character roleplay responses
    prompt_file: prompts/output.md
    interactive: true           # Long-lived, receives context updates
    context_mode: interrupt_restart
    output_to: external         # Streams directly to user
    tools: []                   # No tools - just generates text
    max_turns: 3

output:
  type: stdout
  controller_direct: false      # Output via sub-agent

memory:
  path: ./memory
  init_files:
    - character.md              # Character definition (read-only)
    - rules.md                  # Protected rules
  writable_files:
    - context.md
    - facts.md
    - preferences.md
```

### Key Features

1. **Startup Trigger**: Automatically loads character on start
2. **Interactive Output Sub-Agent**: Stays alive, receives context updates
3. **Separation of Concerns**: Controller orchestrates, output sub-agent speaks
4. **External Output**: Sub-agent's output goes directly to user (not back to controller)
5. **Context Mode**: `interrupt_restart` - stops current response when new context arrives

### Controller vs Output Sub-Agent

| Aspect | Controller | Output Sub-Agent |
|--------|------------|------------------|
| Role | Orchestrator | Response generator |
| Output | Internal | External (to user) |
| Tools | Full access | None |
| Persistence | Per-session | Interactive (long-lived) |

---

## Conversational Agent (`agents/conversational/`)

A streaming conversational AI with voice input/output.

### Purpose
Real-time voice conversation with streaming responses.

### Architecture Pattern
**Voice Pipeline** - ASR input, streaming LLM, TTS output.

```
Audio → Whisper ASR → Controller → TTS → Audio Output
```

### Key Features

1. **Whisper ASR Input**: Real-time speech-to-text with VAD
2. **Streaming TTS Output**: Text-to-speech as response generates
3. **Interactive Sub-Agent**: Long-lived for natural conversation flow
4. **Memory Integration**: Remembers conversation context

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

---

## Creating Your Own Agent

1. **Choose a pattern** based on your use case
2. **Create folder structure**:
   ```
   agents/my_agent/
   ├── config.yaml
   ├── prompts/
   │   └── system.md
   ├── memory/
   │   └── (optional files)
   └── custom/
       └── (optional modules)
   ```
3. **Start with builtin modules**, add custom as needed
4. **Test incrementally** - start with CLI input, add complexity

---

## Common Configurations

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

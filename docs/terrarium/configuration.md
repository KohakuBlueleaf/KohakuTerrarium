# Terrarium Configuration Reference

Terrarium configuration is a YAML file that defines the creatures, channels, and interface for a multi-agent system. The config loader resolves creature paths relative to the terrarium config directory, so all paths in the config are relative.

## File Location

The runtime looks for `terrarium.yaml` or `terrarium.yml` in the given path. You can also pass a direct file path.

```python
from kohakuterrarium.terrarium import load_terrarium_config

# From directory (looks for terrarium.yaml / terrarium.yml)
config = load_terrarium_config("agents/novel_terrarium/")

# From file directly
config = load_terrarium_config("agents/novel_terrarium/terrarium.yaml")
```

## Full YAML Format

```yaml
terrarium:
  name: <string>                    # Terrarium name (default: "terrarium")

  creatures:
    - name: <string>                # Required. Unique creature name.
      config: <path>                # Required. Path to agent config folder (relative to this file).
      channels:
        listen: [<channel_names>]   # Channels this creature receives messages from.
        can_send: [<channel_names>] # Channels this creature is allowed to send to.
      output_log: <bool>            # Capture LLM output to a ring buffer (default: false).
      output_log_size: <int>        # Ring buffer size when output_log is true (default: 100).

  channels:
    <channel_name>:
      type: queue | broadcast       # Channel type (default: queue).
      description: <string>         # Human-readable description, shown in system prompts.

  interface:
    type: cli | web | mcp | none    # Interface type for human interaction.
    observe: [<channel_names>]      # Channels the interface can read.
    inject_to: [<channel_names>]    # Channels the interface can write to.
```

## Creatures

Each creature entry maps to a standalone agent config folder. The creature name must be unique within the terrarium.

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Unique name for this creature instance |
| `config` | path | Yes | - | Path to agent config folder, relative to terrarium YAML |
| `channels.listen` | list[string] | No | `[]` | Channel names to receive messages from |
| `channels.can_send` | list[string] | No | `[]` | Channel names allowed for sending |
| `output_log` | bool | No | `false` | Enable output log capture |
| `output_log_size` | int | No | `100` | Number of log entries to retain |

### Config Path Resolution

Creature config paths are resolved relative to the directory containing the terrarium YAML file. Given:

```
agents/novel_terrarium/
  terrarium.yaml
  creatures/
    brainstorm/
      config.yaml
      prompts/system.md
```

The creature config `./creatures/brainstorm/` resolves to the absolute path of `agents/novel_terrarium/creatures/brainstorm/`.

### Reusing Agent Configs

Multiple creatures can reference the same agent config with different names. This creates separate agent instances from the same template:

```yaml
creatures:
  - name: backend_dev
    config: ./creatures/swe_agent/
    channels:
      listen: [tasks]
      can_send: [results]

  - name: frontend_dev
    config: ./creatures/swe_agent/     # Same config, different instance
    channels:
      listen: [tasks]
      can_send: [results]
```

## Channels

Channels are declared in a mapping where the key is the channel name.

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | No | `queue` | `queue` (point-to-point) or `broadcast` (all subscribers) |
| `description` | string | No | `""` | Shown in creature system prompts for channel awareness |

### Bare Declaration

Channels can be declared with just a name (defaults to queue, no description):

```yaml
channels:
  tasks: {}
```

Or with full options:

```yaml
channels:
  tasks:
    type: queue
    description: "Task assignments from architect to developers"
  team_chat:
    type: broadcast
    description: "Team-wide status updates and discussion"
```

### Channel Types

See [Channel System](channels.md) for detailed semantics of each channel type.

## Interface

The interface section configures how humans or external agents interact with the running terrarium. This section is optional.

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | No | `none` | Interface type: `cli`, `web`, `mcp`, `none` |
| `observe` | list[string] | No | `[]` | Channels the interface can read |
| `inject_to` | list[string] | No | `[]` | Channels the interface can write to |

### Example

```yaml
interface:
  type: cli
  observe: [ideas, outline, draft, feedback, team_chat]
  inject_to: [feedback]
```

This allows a human at the CLI to observe all channels and inject messages into the `feedback` channel.

## Environment Variables

Creature agent configs support environment variable interpolation with defaults:

```yaml
controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
```

### Required Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | API key for OpenRouter (or your LLM provider) |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_MODEL` | Depends on creature config | Model to use for LLM calls |

Set these in a `.env` file at the project root, loaded by `python-dotenv`:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemini-3-flash-preview
```

## Complete Example: Novel Writer

```yaml
# agents/novel_terrarium/terrarium.yaml
terrarium:
  name: novel_writer

  creatures:
    - name: brainstorm
      config: ./creatures/brainstorm/
      channels:
        listen: [feedback]
        can_send: [ideas, team_chat]

    - name: planner
      config: ./creatures/planner/
      channels:
        listen: [ideas]
        can_send: [outline, team_chat]

    - name: writer
      config: ./creatures/writer/
      channels:
        listen: [outline]
        can_send: [draft, feedback, team_chat]

  channels:
    ideas:      { type: queue, description: "Raw ideas from brainstorm to planner" }
    outline:    { type: queue, description: "Chapter outlines from planner to writer" }
    draft:      { type: queue, description: "Written chapters for review" }
    feedback:   { type: queue, description: "Feedback from writer back to brainstorm" }
    team_chat:  { type: broadcast, description: "Team-wide status updates" }

  interface:
    type: cli
    observe: [ideas, outline, draft, feedback, team_chat]
    inject_to: [feedback]
```

Each creature references its own agent config folder with a standard agent `config.yaml`:

```yaml
# agents/novel_terrarium/creatures/brainstorm/config.yaml
name: brainstorm
version: "1.0"

controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  temperature: 0.9
  max_tokens: 8192
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1

system_prompt_file: prompts/system.md

input:
  type: none

output:
  type: stdout

tools:
  - name: send_message
    type: builtin
  - name: wait_channel
    type: builtin
  - name: think
    type: builtin

termination:
  max_turns: 10
  keywords: ["BRAINSTORM_COMPLETE"]

startup_trigger:
  prompt: "Begin brainstorming. Generate creative ideas for a short story, then send your best idea to the 'ideas' channel using send_message."
```

The `input: type: none` is significant - in a terrarium, creatures receive work through channel triggers, not through direct user input. The terrarium runtime overrides input to `NoneInput` regardless of what the creature config specifies.

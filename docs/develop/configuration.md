# Configuration Reference

Complete reference for agent configuration (`config.yaml`) and terrarium configuration (`terrarium.yaml`).

## Part 1: Agent Configuration

KohakuTerrarium supports YAML, JSON, and TOML configuration formats. YAML is recommended.

### Environment Variable Interpolation

Use `${VAR:default}` syntax for environment variables:

```yaml
controller:
  model: "${OPENROUTER_MODEL:gpt-4o-mini}"  # Uses env var or default
  api_key_env: OPENROUTER_API_KEY           # Reads from this env var
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Agent identifier |
| `version` | string | No | Version string |
| `session_key` | string | No | Session key for shared state (default: agent name). Agents with the same key share channels, scratchpad, and TUI state |
| `controller` | object | Yes | LLM configuration |
| `system_prompt_file` | string | No | Path to system prompt markdown |
| `input` | object | No | Input module configuration |
| `output` | object | No | Output module configuration |
| `tools` | list | No | Tool configurations |
| `subagents` | list | No | Sub-agent configurations |
| `triggers` | list | No | Trigger configurations |
| `memory` | object | No | Memory system configuration |
| `startup_trigger` | object | No | Event fired on agent start |

### Controller Configuration

```yaml
controller:
  model: "google/gemini-3-flash-preview"
  temperature: 0.7
  max_tokens: 4096
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  max_messages: 100
  max_context_chars: 100000
  ephemeral: false
  include_tools_in_prompt: true
  include_hints_in_prompt: true
  skill_mode: "dynamic"
  tool_format: bracket       # "bracket", "xml", "native", or custom dict
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | Required | Model identifier |
| `temperature` | float | 0.7 | Sampling temperature |
| `max_tokens` | int | 4096 | Max tokens to generate |
| `api_key_env` | string | Required | Env var containing API key |
| `base_url` | string | OpenAI URL | API endpoint |
| `max_messages` | int | 0 (unlimited) | Max conversation messages |
| `max_context_chars` | int | 0 (unlimited) | Max context characters |
| `ephemeral` | bool | false | Clear conversation after each turn |
| `include_tools_in_prompt` | bool | true | Include tool list |
| `include_hints_in_prompt` | bool | true | Include framework hints |
| `skill_mode` | string | "dynamic" | "dynamic" (use info command) or "static" (all docs in prompt) |
| `tool_format` | string or dict | "bracket" | Tool call format. See [Tool Formats](../concept/tool-formats.md) |

### Input Configuration

```yaml
# CLI input (builtin)
input:
  type: cli
  prompt: "> "

# TUI input (builtin)
input:
  type: tui
  prompt: "You: "
  session_key: my_agent     # Optional: override session key

# None input (trigger-only agents)
input:
  type: none

# Custom input
input:
  type: custom
  module: ./custom/my_input.py
  class: MyInputModule
  my_option: value          # Additional fields passed to constructor
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "cli", "tui", "none", or "custom" |
| `module` | string | For custom | Path to module |
| `class` | string | For custom | Class name |
| `prompt` | string | For CLI/TUI | Input prompt string |
| `session_key` | string | For TUI | Override session key for TUI session |

### Output Configuration

```yaml
# Basic output
output:
  type: stdout
  controller_direct: true

# TUI output
output:
  type: tui
  controller_direct: true
  session_key: my_agent

# With named outputs
output:
  type: stdout
  named_outputs:
    discord:
      type: custom
      module: ./custom/discord_output.py
      class: DiscordOutput
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "stdout", "tui", or "custom" |
| `controller_direct` | bool | No | Controller output to default |
| `named_outputs` | object | No | Named output targets |

### Tools Configuration

```yaml
tools:
  # Builtin tools
  - name: bash
    type: builtin
  - name: read
    type: builtin

  # Custom tools
  - name: my_tool
    type: custom
    module: ./custom/my_tool.py
    class: MyTool
    timeout: 30
```

**Available built-in tools:**

| Name | Description | Name | Description |
|------|-------------|------|-------------|
| `bash` | Execute shell commands | `think` | Extended reasoning step |
| `python` | Execute Python code | `scratchpad` | Session key-value memory |
| `read` | Read file contents | `send_message` | Send to named channel |
| `write` | Create/overwrite files | `wait_channel` | Wait for channel message |
| `edit` | Search-replace in files | `http` | Make HTTP requests |
| `glob` | Find files by pattern | `ask_user` | Prompt user for input |
| `grep` | Regex search in files | `json_read` | Query JSON files |
| `tree` | Directory structure | `json_write` | Modify JSON files |

### Sub-Agents Configuration

```yaml
subagents:
  # Builtin
  - name: explore
    type: builtin

  # Custom
  - name: output
    type: custom
    description: Generate responses
    prompt_file: prompts/output.md
    tools: []
    can_modify: false
    max_turns: 5
    timeout: 60
    interactive: false
    output_to: controller
```

**Available built-in sub-agents:**

| Name | Description | Tools |
|------|-------------|-------|
| `explore` | Search and analyze codebase | glob, grep, read |
| `plan` | Create implementation plans | glob, grep, read |
| `worker` | Implement changes | read, write, edit, bash, glob, grep |
| `critic` | Review and critique | read, glob, grep |
| `summarize` | Condense content | (none) |
| `research` | Web + file research | http, read, glob, grep |
| `coordinator` | Multi-agent via channels | send_message, wait_channel |
| `memory_read` | Retrieve from memory | read, glob |
| `memory_write` | Store to memory | write, read |
| `response` | Generate user responses | (none) |

**Sub-agent fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | Required | Sub-agent identifier |
| `type` | string | Required | "builtin" or "custom" |
| `description` | string | "" | One-line description |
| `tools` | list | [] | Allowed tool names |
| `system_prompt` | string | "" | Inline system prompt |
| `prompt_file` | string | None | Path to prompt file |
| `can_modify` | bool | false | Allow write/edit tools |
| `stateless` | bool | true | No persistent state |
| `interactive` | bool | false | Long-lived with context updates |
| `context_mode` | string | "interrupt_restart" | How to handle updates |
| `output_to` | string | "controller" | "controller" or "external" |
| `output_module` | string | None | Output module name |
| `return_as_context` | bool | false | Return output to parent |
| `max_turns` | int | 10 | Max conversation turns |
| `timeout` | float | 300.0 | Max execution time |
| `model` | string | None | Override LLM model |
| `temperature` | float | None | Override temperature |
| `memory_path` | string | None | Memory folder path |

**Context update modes:** `interrupt_restart` (stop, start new), `queue_append` (queue, process after), `flush_replace` (flush, replace immediately).

### Triggers Configuration

```yaml
triggers:
  - type: custom
    module: ./custom/idle_trigger.py
    class: IdleTrigger
    prompt: "The chat has been quiet."
    min_idle_seconds: 300
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "custom" (builtins coming) |
| `module` | string | Yes | Path to module |
| `class` | string | Yes | Class name |
| `prompt` | string | No | Default prompt for events |

### Memory Configuration

```yaml
memory:
  path: ./memory
  init_files:
    - character.md       # Read-only
    - rules.md
  writable_files:
    - context.md         # Agent can modify
    - facts.md
```

### Startup Trigger

```yaml
startup_trigger:
  prompt: "Agent starting. Initialize your state."
```

### Agent Folder Structure

```
agents/my_agent/
+-- config.yaml              # Main configuration
+-- prompts/
|   +-- system.md            # System prompt
|   +-- output.md            # Output sub-agent prompt
|   +-- tools/               # Tool documentation overrides
|       +-- bash.md
+-- memory/
|   +-- character.md
|   +-- context.md
+-- custom/
    +-- my_input.py
    +-- my_tool.py
    +-- my_trigger.py
```

---

## Part 2: Terrarium Configuration

Terrarium configuration is a YAML file that defines creatures, channels, and the interface for a multi-agent system.

### File Location

The runtime looks for `terrarium.yaml` or `terrarium.yml` in the given path:

```python
from kohakuterrarium.terrarium import load_terrarium_config

config = load_terrarium_config("agents/novel_terrarium/")
config = load_terrarium_config("agents/novel_terrarium/terrarium.yaml")
```

### Full YAML Format

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

### Creatures

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Unique name for this creature instance |
| `config` | path | Yes | - | Path to agent config folder, relative to terrarium YAML |
| `channels.listen` | list[string] | No | `[]` | Channel names to receive messages from |
| `channels.can_send` | list[string] | No | `[]` | Channel names allowed for sending |
| `output_log` | bool | No | `false` | Enable output log capture |
| `output_log_size` | int | No | `100` | Number of log entries to retain |

**Config path resolution:** Creature config paths resolve relative to the directory containing the terrarium YAML file.

**Reusing agent configs:** Multiple creatures can reference the same agent config with different names, creating separate instances from the same template.

### Channels

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | No | `queue` | `queue` (point-to-point) or `broadcast` (all subscribers) |
| `description` | string | No | `""` | Shown in creature system prompts for channel awareness |

For channel semantics, see [Channels](../concept/channels.md).

### Interface

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | No | `none` | Interface type: `cli`, `web`, `mcp`, `none` |
| `observe` | list[string] | No | `[]` | Channels the interface can read |
| `inject_to` | list[string] | No | `[]` | Channels the interface can write to |

### Environment Variables

Creature agent configs support environment variable interpolation:

```yaml
controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  api_key_env: OPENROUTER_API_KEY
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | API key for your LLM provider |
| `OPENROUTER_MODEL` | No | Model override (creature configs have defaults) |

Set these in a `.env` file at the project root, loaded by `python-dotenv`.

### Complete Example

```yaml
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

**Key points:**
- `input: type: none` in creature configs is significant - creatures receive work through channel triggers, not direct user input. The terrarium runtime overrides input to `NoneInput` regardless.
- Creatures that participate in channels need `send_message` and/or `wait_channel` tools in their own `config.yaml`.
- The runtime fires each creature's `startup_trigger` after all creatures are started, so channels are available from the beginning.

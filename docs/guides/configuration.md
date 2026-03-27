# Configuration Reference

Complete reference for agent configuration files (`config.yaml`).

## Configuration Format

KohakuTerrarium supports YAML, JSON, and TOML configuration formats. YAML is recommended for readability.

### Environment Variable Interpolation

Use `${VAR:default}` syntax for environment variables:

```yaml
controller:
  model: "${OPENROUTER_MODEL:gpt-4o-mini}"  # Uses env var or default
  api_key_env: OPENROUTER_API_KEY           # Reads from this env var
```

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Agent identifier |
| `version` | string | No | Version string |
| `controller` | object | Yes | LLM configuration |
| `system_prompt_file` | string | No | Path to system prompt markdown |
| `input` | object | No | Input module configuration |
| `output` | object | No | Output module configuration |
| `tools` | list | No | Tool configurations |
| `subagents` | list | No | Sub-agent configurations |
| `triggers` | list | No | Trigger configurations |
| `memory` | object | No | Memory system configuration |
| `startup_trigger` | object | No | Event fired on agent start |

---

## Controller Configuration

```yaml
controller:
  # LLM settings
  model: "google/gemini-3-flash-preview"
  temperature: 0.7
  max_tokens: 4096

  # API configuration
  api_key_env: OPENROUTER_API_KEY    # Environment variable name
  base_url: https://openrouter.ai/api/v1

  # Context management
  max_messages: 100                  # Max messages in conversation
  max_context_chars: 100000          # Max total characters

  # Mode settings
  ephemeral: false                   # Clear conversation after each turn

  # Prompt settings
  include_tools_in_prompt: true      # Include tool list in system prompt
  include_hints_in_prompt: true      # Include framework hints
  skill_mode: "dynamic"              # "dynamic" or "static"
```

### Controller Fields

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
| `skill_mode` | string | "dynamic" | "dynamic" (use [/info]) or "static" (all docs in prompt) |

---

## Input Configuration

### CLI Input (builtin)

```yaml
input:
  type: cli
  prompt: "> "
```

### Custom Input

```yaml
input:
  type: custom
  module: ./custom/my_input.py
  class: MyInputModule
  # Additional fields passed to constructor
  my_option: value
```

### Input Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "cli", "builtin", or "custom" |
| `module` | string | For custom | Path to module |
| `class` | string | For custom | Class name |
| `prompt` | string | For CLI | Input prompt string |
| `*` | any | No | Additional fields passed to constructor |

---

## Output Configuration

### Basic Output

```yaml
output:
  type: stdout
  controller_direct: true    # Controller text goes to stdout
```

### With Named Outputs

```yaml
output:
  type: stdout               # Default output

  named_outputs:
    discord:
      type: custom
      module: ./custom/discord_output.py
      class: DiscordOutput
      # Additional options
      keywords_file: ./filtered_keywords.txt
```

### Output Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "stdout" or "custom" |
| `controller_direct` | bool | No | Controller output to default |
| `named_outputs` | object | No | Named output targets |

---

## Tools Configuration

### Builtin Tools

```yaml
tools:
  - name: bash
    type: builtin

  - name: read
    type: builtin

  - name: write
    type: builtin
```

### Custom Tools

```yaml
tools:
  - name: my_tool
    type: custom
    module: ./custom/my_tool.py
    class: MyTool
    # Additional options passed to constructor
    timeout: 30
    max_output: 10000
```

### Available Builtin Tools

| Name | Description |
|------|-------------|
| `bash` | Execute shell commands |
| `python` | Execute Python code |
| `read` | Read file contents |
| `write` | Create/overwrite files |
| `edit` | Edit file contents |
| `glob` | Find files by pattern |
| `grep` | Search file contents |
| `tree` | Show directory tree |

### Tool Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Tool identifier |
| `type` | string | Yes | "builtin" or "custom" |
| `module` | string | For custom | Path to module |
| `class` | string | For custom | Class name |
| `*` | any | No | Passed to ToolConfig |

---

## Sub-Agents Configuration

### Builtin Sub-Agents

```yaml
subagents:
  - name: explore
    type: builtin

  - name: plan
    type: builtin

  - name: memory_read
    type: builtin

  - name: memory_write
    type: builtin
```

### Custom Sub-Agents

```yaml
subagents:
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

### Interactive Sub-Agents

```yaml
subagents:
  - name: response
    type: custom
    description: Interactive response generator
    prompt_file: prompts/response.md
    interactive: true              # Long-lived
    context_mode: interrupt_restart
    output_to: external            # Stream to user
    return_as_context: false       # Don't return to controller
```

### Available Builtin Sub-Agents

| Name | Description | Tools |
|------|-------------|-------|
| `explore` | Search and analyze codebase | glob, grep, read |
| `plan` | Create implementation plans | glob, grep, read |
| `memory_read` | Retrieve from memory | read, glob |
| `memory_write` | Store to memory | write, read |
| `response` | Generate user responses | (none) |

### Sub-Agent Fields

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

### Context Update Modes

| Mode | Behavior |
|------|----------|
| `interrupt_restart` | Stop current response, start new |
| `queue_append` | Queue updates, process after current |
| `flush_replace` | Flush output, replace context immediately |

---

## Triggers Configuration

### Custom Triggers

```yaml
triggers:
  - type: custom
    module: ./custom/idle_trigger.py
    class: IdleTrigger
    prompt: "The chat has been quiet."
    min_idle_seconds: 300
    max_idle_seconds: 3600
```

### Trigger Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "custom" (builtins coming) |
| `module` | string | Yes | Path to module |
| `class` | string | Yes | Class name |
| `prompt` | string | No | Default prompt for events |
| `*` | any | No | Passed to constructor |

---

## Memory Configuration

```yaml
memory:
  path: ./memory

  # Read-only files (cannot be modified by agent)
  init_files:
    - character.md
    - rules.md

  # Writable files (can be modified by agent)
  writable_files:
    - context.md
    - facts.md
    - notes.md
```

### Memory Fields

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Memory folder path |
| `init_files` | list | Read-only files |
| `writable_files` | list | Files agent can modify |

---

## Startup Trigger

Fire an event when agent starts:

```yaml
startup_trigger:
  prompt: "Agent starting. Initialize your state."
```

---

## Complete Example

```yaml
name: complete_agent
version: "1.0"

controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  temperature: 0.7
  max_tokens: 65536
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  ephemeral: false
  max_messages: 100
  max_context_chars: 200000
  include_tools_in_prompt: true
  include_hints_in_prompt: true
  skill_mode: dynamic

system_prompt_file: prompts/system.md

startup_trigger:
  prompt: "Agent started. Initialize your state."

input:
  type: cli
  prompt: "> "

output:
  type: stdout
  controller_direct: true

  named_outputs:
    external:
      type: custom
      module: ./custom/external_output.py
      class: ExternalOutput

tools:
  - name: bash
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
  - name: tree
    type: builtin
  - name: python
    type: builtin

  - name: custom_tool
    type: custom
    module: ./custom/my_tool.py
    class: MyTool
    timeout: 60

subagents:
  - name: explore
    type: builtin

  - name: plan
    type: builtin

  - name: memory_read
    type: builtin

  - name: memory_write
    type: builtin

  - name: custom_agent
    type: custom
    description: Custom processing agent
    prompt_file: prompts/custom.md
    tools: [read, grep, glob]
    can_modify: false
    max_turns: 5

triggers:
  - type: custom
    module: ./custom/idle_trigger.py
    class: IdleTrigger
    min_idle_seconds: 300
    prompt: "Check for follow-up tasks."

memory:
  path: ./memory
  init_files:
    - character.md
    - rules.md
  writable_files:
    - context.md
    - facts.md
    - notes.md
```

---

## Folder Structure

```
agents/my_agent/
├── config.yaml              # Main configuration
├── prompts/
│   ├── system.md            # System prompt
│   ├── output.md            # Output sub-agent prompt
│   └── tools/               # Tool documentation overrides
│       └── bash.md
├── memory/
│   ├── character.md         # Character definition
│   ├── rules.md             # Protected rules
│   ├── context.md           # Current context
│   └── facts.md             # Stored facts
└── custom/
    ├── my_input.py          # Custom input module
    ├── my_output.py         # Custom output module
    ├── my_tool.py           # Custom tool
    └── my_trigger.py        # Custom trigger
```

# CLI Reference

KohakuTerrarium provides a command-line interface for running agents and terrariums.

## Installation

```bash
uv pip install -e .
```

After installation, commands are run via `kt`.

## Authentication

### `login` - Authenticate with a Provider

```bash
kt login <provider>
```

Currently supports Codex OAuth, which uses your ChatGPT Plus/Pro subscription for LLM access.

```bash
kt login codex
```

Opens a browser for ChatGPT OAuth. After login, agents configured with `auth_mode: codex-oauth` will use your subscription.

## Agent Commands

### `run` - Run an Agent

```bash
kt run <agent_path> [options]
```

Start an agent from a config folder and enter the interactive event loop.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `agent_path` | Yes | Path to agent config folder (e.g., `examples/agent-apps/swe_agent`) |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity |
| `--session` | flag | off | Enable session recording to `.kohakutr` file |

**Examples:**

```bash
# Run the SWE agent
kt run examples/agent-apps/swe_agent

# Run with session recording
kt run examples/agent-apps/swe_agent --session

# Run with debug logging
kt run examples/agent-apps/swe_agent --log-level DEBUG

# Run the TUI agent
kt run examples/agent-apps/swe_agent_tui
```

The agent folder must contain a `config.yaml` or `config.yml` file.

### `resume` - Resume a Session

```bash
kt resume <session_path>
```

Resume a previously saved session from a `.kohakutr` file. Restores conversation history, scratchpad state, and event log.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `session_path` | Yes | Path to `.kohakutr` session file |

**Examples:**

```bash
# Resume a specific session
kt resume .kohaku/sessions/swe_agent_20260401_120000.kohakutr

# Resume with glob (shell expansion)
kt resume .kohaku/sessions/swe_agent_*.kohakutr
```

The `.kohakutr` file contains all state needed for resume: conversation (with tool_calls metadata), scratchpad, event log, and session metadata. Both standalone agent sessions and terrarium sessions are supported.

### `list` - List Available Agents

```bash
kt list [options]
```

Scan a directory for agent folders (directories containing `config.yaml`) and display them.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `examples` | Path to agents directory |

**Example:**

```bash
kt list
kt list --path /path/to/agents
```

### `info` - Show Agent Info

```bash
kt info <agent_path>
```

Display agent configuration: name, model, tools, sub-agents, and files.

**Example:**

```bash
kt info examples/agent-apps/swe_agent
```

## Terrarium Commands

### `terrarium run` - Run a Terrarium

```bash
kt terrarium run <terrarium_path> [options]
```

Start a terrarium from a config folder. All creatures run concurrently.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `terrarium_path` | Yes | Path to terrarium config folder or file |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity |
| `--session` | flag | off | Enable session recording to `.kohakutr` file |
| `--seed` | string | (prompt) | Seed prompt to inject on startup |
| `--seed-channel` | string | `seed` | Channel to send the seed prompt to |
| `--observe` | channel names | all | Channels to observe (space-separated) |
| `--no-observe` | flag | off | Disable channel observation entirely |

**Examples:**

```bash
# Run the novel writer terrarium
kt terrarium run examples/terrariums/novel_terrarium/

# Run with channel observation (specific channels)
kt terrarium run examples/terrariums/novel_terrarium/ --observe ideas outline draft

# Run with a seed prompt
kt terrarium run examples/terrariums/novel_terrarium/ --seed "Write a cyberpunk story"

# Run without observation
kt terrarium run examples/terrariums/novel_terrarium/ --no-observe

# Run with debug logging
kt terrarium run examples/terrariums/novel_terrarium/ --log-level DEBUG
```

**Seed prompt behavior:** If the terrarium config declares a `seed` channel and no `--seed` flag is provided, the CLI prompts the user to enter a seed interactively.

**Observation:** By default, all declared channels are observed. When `--observe` is used with channel names, only those channels are watched. Use `--no-observe` to disable observation entirely. Observed messages are printed with a timestamp, channel name, sender, and content preview.

### `terrarium info` - Show Terrarium Info

```bash
kt terrarium info <terrarium_path>
```

Display terrarium configuration without running it: creature names, config paths, channel assignments, output log settings, and declared channels with types and descriptions.

**Example:**

```bash
kt terrarium info examples/terrariums/novel_terrarium/
```

**Sample output:**

```
Terrarium: novel_writer
========================================

Creatures (3):
  brainstorm
    config: /path/to/examples/terrariums/novel_terrarium/creatures/brainstorm
    listen: ['feedback']
    send:   ['ideas', 'team_chat']
  planner
    config: /path/to/examples/terrariums/novel_terrarium/creatures/planner
    listen: ['ideas']
    send:   ['outline', 'team_chat']
  writer
    config: /path/to/examples/terrariums/novel_terrarium/creatures/writer
    listen: ['outline']
    send:   ['draft', 'feedback', 'team_chat']

Channels (5):
  ideas (queue) - Raw ideas from brainstorm to planner
  outline (queue) - Chapter outlines from planner to writer
  draft (queue) - Written chapters for review
  feedback (queue) - Feedback from writer back to brainstorm
  team_chat (broadcast) - Team-wide status updates
```

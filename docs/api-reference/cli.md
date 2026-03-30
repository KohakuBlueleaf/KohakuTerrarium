# CLI Reference

KohakuTerrarium provides a command-line interface for running agents and terrariums.

## Installation

```bash
uv pip install -e .
```

After installation, commands are run via `python -m kohakuterrarium`.

## Agent Commands

### `run` - Run an Agent

```bash
python -m kohakuterrarium run <agent_path> [options]
```

Start an agent from a config folder and enter the interactive event loop.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `agent_path` | Yes | Path to agent config folder (e.g., `agents/swe_agent`) |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity |

**Examples:**

```bash
# Run the SWE agent
python -m kohakuterrarium run agents/swe_agent

# Run with debug logging
python -m kohakuterrarium run agents/swe_agent --log-level DEBUG

# Run the TUI agent
python -m kohakuterrarium run agents/swe_agent_tui
```

The agent folder must contain a `config.yaml` or `config.yml` file.

### `list` - List Available Agents

```bash
python -m kohakuterrarium list [options]
```

Scan a directory for agent folders (directories containing `config.yaml`) and display them.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `agents` | Path to agents directory |

**Example:**

```bash
python -m kohakuterrarium list
python -m kohakuterrarium list --path /path/to/agents
```

### `info` - Show Agent Info

```bash
python -m kohakuterrarium info <agent_path>
```

Display agent configuration: name, model, tools, sub-agents, and files.

**Example:**

```bash
python -m kohakuterrarium info agents/swe_agent
```

## Terrarium Commands

### `terrarium run` - Run a Terrarium

```bash
python -m kohakuterrarium terrarium run <terrarium_path> [options]
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
| `--seed` | string | (prompt) | Seed prompt to inject on startup |
| `--seed-channel` | string | `seed` | Channel to send the seed prompt to |
| `--observe` | channel names | all | Channels to observe (space-separated) |
| `--no-observe` | flag | off | Disable channel observation entirely |

**Examples:**

```bash
# Run the novel writer terrarium
python -m kohakuterrarium terrarium run agents/novel_terrarium/

# Run with channel observation (specific channels)
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --observe ideas outline draft

# Run with a seed prompt
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --seed "Write a cyberpunk story"

# Run without observation
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --no-observe

# Run with debug logging
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --log-level DEBUG
```

**Seed prompt behavior:** If the terrarium config declares a `seed` channel and no `--seed` flag is provided, the CLI prompts the user to enter a seed interactively.

**Observation:** By default, all declared channels are observed. When `--observe` is used with channel names, only those channels are watched. Use `--no-observe` to disable observation entirely. Observed messages are printed with a timestamp, channel name, sender, and content preview.

### `terrarium info` - Show Terrarium Info

```bash
python -m kohakuterrarium terrarium info <terrarium_path>
```

Display terrarium configuration without running it: creature names, config paths, channel assignments, output log settings, and declared channels with types and descriptions.

**Example:**

```bash
python -m kohakuterrarium terrarium info agents/novel_terrarium/
```

**Sample output:**

```
Terrarium: novel_writer
========================================

Creatures (3):
  brainstorm
    config: /path/to/agents/novel_terrarium/creatures/brainstorm
    listen: ['feedback']
    send:   ['ideas', 'team_chat']
  planner
    config: /path/to/agents/novel_terrarium/creatures/planner
    listen: ['ideas']
    send:   ['outline', 'team_chat']
  writer
    config: /path/to/agents/novel_terrarium/creatures/writer
    listen: ['outline']
    send:   ['draft', 'feedback', 'team_chat']

Channels (5):
  ideas (queue) - Raw ideas from brainstorm to planner
  outline (queue) - Chapter outlines from planner to writer
  draft (queue) - Written chapters for review
  feedback (queue) - Feedback from writer back to brainstorm
  team_chat (broadcast) - Team-wide status updates
```

# CLI Reference

KohakuTerrarium provides a command-line interface (`kt`) for running agents, managing terrariums, searching sessions, and configuring LLM providers.

## Installation

```bash
uv pip install -e .
```

After installation, all commands are available via `kt`.

## Quick Reference

| Command | Description |
|---------|-------------|
| `kt login <provider>` | Authenticate with an LLM provider |
| `kt model list` | List all available LLM profiles |
| `kt model default <name>` | Set the default LLM profile |
| `kt model show <name>` | Show detailed profile info |
| `kt run <path>` | Run an agent |
| `kt terrarium run <path>` | Run a multi-agent terrarium |
| `kt terrarium info <path>` | Show terrarium config without running |
| `kt resume [session]` | Resume a saved session |
| `kt list` | List installed packages and local agents |
| `kt search <session> <query>` | Search a session's memory |
| `kt embedding <session>` | Build embedding index for a session |
| `kt install <source>` | Install a creature/terrarium package |
| `kt uninstall <name>` | Remove an installed package |
| `kt edit <ref>` | Open a package config in your editor |
| `kt info <path>` | Show agent config info |

## Authentication

### `kt login` - Authenticate with a Provider

```bash
kt login <provider>
```

Supported providers: `codex`, `openrouter`, `openai`, `anthropic`, `gemini`.

**Codex** uses OAuth (opens a browser for ChatGPT login). After authenticating, agents with `auth_mode: codex-oauth` will use your ChatGPT Plus/Pro subscription. Tokens are saved to `~/.kohakuterrarium/codex-auth.json`.

**All other providers** prompt for an API key interactively. Keys are stored in `~/.kohakuterrarium/api_keys.yaml`. If a key already exists, you are shown a masked preview and asked to confirm replacement.

**Workflow example:**

```bash
# 1. Add your API key
kt login openrouter

# 2. See available models
kt model list

# 3. Set a default model
kt model default gpt-5.4

# 4. Run an agent (uses default model, or override with --llm)
kt run @kohaku-creatures/creatures/swe
kt run @kohaku-creatures/creatures/swe --llm claude-sonnet-4
```

## Model Management

### `kt model list` - List LLM Profiles

```bash
kt model list
```

Shows all available profiles (built-in presets and user-defined) with model name, provider, context size, and source. The current default is marked with `*`.

**Sample output:**

```
Default model: gpt-5.4

Name                      Model                                    Provider       Context    Src
-------------------------------------------------------------------------------------------------
gpt-5.4                   gpt-5.4                                  openai         1000k      preset *
claude-sonnet-4           claude-sonnet-4-20250514                  anthropic      200k       preset
gemini                    gemini-2.5-pro                            gemini         1000k      preset
```

### `kt model default` - Set Default Model

```bash
kt model default <name>
```

Sets the default LLM profile. The name must match a profile from `kt model list`.

```bash
kt model default claude-sonnet-4
```

### `kt model show` - Show Profile Details

```bash
kt model show <name>
```

Displays full configuration for a profile: provider, model, context window, max output tokens, base URL, API key env var, temperature, reasoning effort, and extra body parameters.

```bash
kt model show gpt-5.4
```

## Running Agents

### `kt run` - Run an Agent

```bash
kt run <agent_path> [options]
```

Start an agent from a config folder and enter the interactive event loop. The agent folder must contain a `config.yaml` or `config.yml` file.

Paths starting with `@` are resolved as package references (e.g., `@kohaku-creatures/creatures/swe`).

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `agent_path` | Yes | Path to agent config folder, or `@package/creatures/name` |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--mode` | `cli`, `tui` | `tui` | Input/output mode |
| `--llm` | profile name | (from config) | Override LLM profile (e.g., `gpt-5.4`, `claude-sonnet-4`) |
| `--session` | path | auto | Session file path; auto-generates in `~/.kohakuterrarium/sessions/` |
| `--no-session` | flag | off | Disable session persistence entirely |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity |

**Session behavior:** By default, sessions are saved automatically to `~/.kohakuterrarium/sessions/<agent_name>_<id>.kohakutr`. Use `--no-session` to disable. Use `--session <path>` to specify a custom file path.

**Examples:**

```bash
# Run a local agent (TUI mode, session auto-saved)
kt run examples/agent-apps/swe_agent

# Run a package agent with CLI mode
kt run @kohaku-creatures/creatures/swe --mode cli

# Override the LLM profile
kt run @kohaku-creatures/creatures/swe --llm gemini

# Disable session recording
kt run examples/agent-apps/swe_agent --no-session

# Run with debug logging
kt run examples/agent-apps/swe_agent --log-level DEBUG
```

## Running Terrariums

### `kt terrarium run` - Run a Terrarium

```bash
kt terrarium run <terrarium_path> [options]
```

Start a multi-agent terrarium. If the terrarium config declares a root agent, the TUI launches with tabs for the root, each creature, and each channel. Without a root agent, a simpler seed/observe CLI is used.

Paths starting with `@` are resolved as package references.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `terrarium_path` | Yes | Path to terrarium config folder/file, or `@package/terrariums/name` |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--seed` | string | (prompt) | Seed prompt to inject on startup |
| `--seed-channel` | string | `seed` | Channel to send the seed prompt to |
| `--observe` | channel names | all | Channels to observe (space-separated) |
| `--no-observe` | flag | off | Disable channel observation entirely |
| `--session` | path | auto | Session file path |
| `--no-session` | flag | off | Disable session persistence |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity |

**Seed prompt behavior:** If the terrarium config declares a `seed` channel and no `--seed` flag is provided, the CLI prompts the user to enter a seed interactively.

**Observation (no-root mode only):** By default, all declared channels are observed. When `--observe` is used with channel names, only those channels are watched. Use `--no-observe` to disable. Observed messages are printed with timestamp, channel name, sender, and content preview.

**Examples:**

```bash
# Run a terrarium (TUI if root agent is configured)
kt terrarium run examples/terrariums/novel_terrarium/

# Run with a seed prompt
kt terrarium run examples/terrariums/novel_terrarium/ --seed "Write a cyberpunk story"

# Observe specific channels only
kt terrarium run examples/terrariums/novel_terrarium/ --observe ideas outline draft

# Run without observation
kt terrarium run examples/terrariums/novel_terrarium/ --no-observe

# Disable session recording
kt terrarium run examples/terrariums/novel_terrarium/ --no-session
```

### `kt terrarium info` - Show Terrarium Info

```bash
kt terrarium info <terrarium_path>
```

Display terrarium configuration without running it: creature names, base configs, channel assignments, output log settings, and channel types/descriptions.

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
    base: creatures/brainstorm
    listen: ['feedback']
    send:   ['ideas', 'team_chat']
  planner
    base: creatures/planner
    listen: ['ideas']
    send:   ['outline', 'team_chat']
  writer
    base: creatures/writer
    listen: ['outline']
    send:   ['draft', 'feedback', 'team_chat']

Channels (5):
  ideas (queue) - Raw ideas from brainstorm to planner
  outline (queue) - Chapter outlines from planner to writer
  draft (queue) - Written chapters for review
  feedback (queue) - Feedback from writer back to brainstorm
  team_chat (broadcast) - Team-wide status updates
```

## Session Management

### `kt resume` - Resume a Session

```bash
kt resume [session] [options]
```

Resume a previously saved session from a `.kohakutr` file. Restores conversation history, scratchpad state, and event log. Both standalone agent sessions and terrarium sessions are supported.

The `session` argument accepts several forms: a full file path, a filename, a name prefix (matched against `~/.kohakuterrarium/sessions/`), or omitted entirely to list recent sessions interactively.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `session` | No | Session name/prefix, full path, or omit to list recent sessions |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--last` | flag | off | Resume the most recent session (no interactive picker) |
| `--mode` | `cli`, `tui` | `tui` | Input/output mode |
| `--pwd` | path | (original) | Override working directory |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity |

**Examples:**

```bash
# List recent sessions and pick interactively
kt resume

# Resume the most recent session
kt resume --last

# Resume by name prefix
kt resume swe_agent

# Resume a specific file
kt resume ~/.kohakuterrarium/sessions/swe_agent_01a2b3c4.kohakutr

# Resume in CLI mode
kt resume swe_agent --mode cli
```

### `kt list` - List Agents and Packages

```bash
kt list [options]
```

Shows installed packages (from `~/.kohakuterrarium/packages/`) with their creatures and terrariums, then scans a local directory for agent folders.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `agents` | Path to local agents directory |

**Examples:**

```bash
kt list
kt list --path /path/to/agents
```

## Session Search

### `kt search` - Search Session Memory

```bash
kt search <session> <query> [options]
```

Search a session's indexed memory. Supports full-text search (FTS), semantic search (requires embeddings), and hybrid mode.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `session` | Yes | Session name/prefix or path |
| `query` | Yes | Search query string |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--mode` | `fts`, `semantic`, `hybrid`, `auto` | `auto` | Search mode |
| `--agent` | agent name | (all) | Filter results by agent name |
| `-k` | integer | `10` | Maximum number of results |

**Search modes:**

- `fts`: Full-text search only (always available)
- `semantic`: Vector similarity search (requires `kt embedding` first)
- `hybrid`: Combines FTS and semantic results
- `auto`: Uses hybrid if vectors are available, falls back to FTS

**Examples:**

```bash
# Search with auto mode
kt search swe_agent "file reading bug"

# FTS only, filter by agent
kt search my_session "config loading" --mode fts --agent root

# Semantic search, top 5
kt search my_session "error handling patterns" --mode semantic -k 5
```

### `kt embedding` - Build Embedding Index

```bash
kt embedding <session> [options]
```

Build a vector embedding index for a session's events. This is required before using `semantic` or `hybrid` search modes.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `session` | Yes | Session name/prefix or path |

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--provider` | `auto`, `model2vec`, `sentence-transformer`, `api` | `auto` | Embedding provider (auto prefers jina v5 nano) |
| `--model` | model name | (provider-dependent) | Override embedding model |
| `--dimensions` | integer | (model default) | Embedding dimensions (Matryoshka truncation) |

**Examples:**

```bash
# Build with default provider
kt embedding swe_agent

# Use a specific provider and model
kt embedding swe_agent --provider sentence-transformer --model all-MiniLM-L6-v2

# Specify dimensions for Matryoshka embeddings
kt embedding swe_agent --dimensions 256
```

## Package Management

### `kt install` - Install a Package

```bash
kt install <source> [options]
```

Install a creature/terrarium package from a git URL or local path. Packages are stored in `~/.kohakuterrarium/packages/`.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `source` | Yes | Git URL or local path to the package |

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `-e`, `--editable` | off | Install as editable (symlink, like `pip -e`) |
| `--name` | (auto) | Override package name |

After installation, package contents are referenced with `@package_name/creatures/<name>` or `@package_name/terrariums/<name>`.

**Examples:**

```bash
# Install from git
kt install https://github.com/user/my-creatures.git

# Install from local path (editable)
kt install ./my-creatures -e

# Install with custom name
kt install ./my-creatures --name my-custom-pack
```

### `kt uninstall` - Remove a Package

```bash
kt uninstall <name>
```

Remove an installed package by name.

```bash
kt uninstall my-creatures
```

### `kt edit` - Edit Package Config

```bash
kt edit <target>
```

Open a creature or terrarium config file in your editor (`$EDITOR`, `$VISUAL`, or `nano`).

The target uses the `@package/path` format. The leading `@` is optional.

```bash
kt edit @kohaku-creatures/creatures/swe
kt edit kohaku-creatures/terrariums/novel
```

The command locates the config file (`config.yaml`, `config.yml`, `terrarium.yaml`, or `terrarium.yml`) inside the resolved path and opens it.

## Utility

### `kt info` - Show Agent Info

```bash
kt info <agent_path>
```

Display agent configuration: name, description, model, tools, sub-agents, and files in the config folder.

```bash
kt info examples/agent-apps/swe_agent
```

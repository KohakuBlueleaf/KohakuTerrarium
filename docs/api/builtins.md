# Builtins API Reference

API reference for built-in tools, sub-agents, inputs, and outputs.

## Builtin Tools

### bash

Execute shell commands.

```yaml
tools:
  - name: bash
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| command | body | Command to execute (required) |

**Example:**
```
[/bash]ls -la[bash/]
```

**Notes:**
- On Windows: Uses PowerShell Core (pwsh) or Windows PowerShell
- On Unix/Linux/Mac: Uses bash or sh
- Commands have configurable timeout
- Large outputs may be truncated

---

### python

Execute Python code.

```yaml
tools:
  - name: python
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| code | body | Python code to execute (required) |

**Example:**
```
[/python]
import os
for f in os.listdir('.'):
    print(f)
[python/]
```

**Notes:**
- Code runs in a separate subprocess
- Has access to installed packages
- stdout and stderr are captured

---

### read

Read file contents.

```yaml
tools:
  - name: read
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| path | @@path=... | File path to read (required) |
| limit | @@limit=... | Max lines to read (optional) |
| offset | @@offset=... | Line offset to start from (optional) |

**Example:**
```
[/read]@@path=src/main.py[read/]
```

With offset and limit:
```
[/read]
@@path=src/main.py
@@offset=100
@@limit=50
[read/]
```

---

### write

Create or overwrite files.

```yaml
tools:
  - name: write
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| path | @@path=... | File path to write (required) |
| content | body | File content (required) |

**Example:**
```
[/write]
@@path=output.txt
Hello, world!
This is the file content.
[write/]
```

**Notes:**
- Creates parent directories if needed
- Overwrites existing files

---

### edit

Edit file contents with targeted changes.

```yaml
tools:
  - name: edit
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| path | @@path=... | File path to edit (required) |
| diff | body | Diff/changes to apply (required) |

**Example:**
```
[/edit]
@@path=src/main.py
<<<<<<< SEARCH
def old_function():
    pass
=======
def new_function():
    return True
>>>>>>> REPLACE
[edit/]
```

**Notes:**
- Uses search/replace blocks
- Multiple changes in one edit supported

---

### glob

Find files by pattern.

```yaml
tools:
  - name: glob
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| pattern | @@pattern=... | Glob pattern (required) |
| path | @@path=... | Base path (optional, defaults to cwd) |

**Example:**
```
[/glob]@@pattern=**/*.py[glob/]
```

With base path:
```
[/glob]
@@pattern=*.md
@@path=docs/
[glob/]
```

**Pattern Syntax:**
- `*` - Match any characters (not path separator)
- `**` - Match any characters including path separator
- `?` - Match single character
- `[abc]` - Match character set

---

### grep

Search file contents.

```yaml
tools:
  - name: grep
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| pattern | @@pattern=... | Search pattern (required) |
| path | @@path=... | File/directory to search (optional) |
| glob | @@glob=... | File pattern filter (optional) |

**Example:**
```
[/grep]@@pattern=async def[grep/]
```

With filters:
```
[/grep]
@@pattern=import asyncio
@@glob=**/*.py
@@path=src/
[grep/]
```

**Notes:**
- Supports regex patterns
- Returns matching lines with context

---

### tree

Show directory tree.

```yaml
tools:
  - name: tree
    type: builtin
```

**Arguments:**
| Arg | Type | Description |
|-----|------|-------------|
| path | @@path=... | Directory path (optional, defaults to cwd) |
| depth | @@depth=... | Max depth (optional) |

**Example:**
```
[/tree]@@path=src/[tree/]
```

---

## Builtin Sub-Agents

### explore

Search and analyze codebase (read-only).

```yaml
subagents:
  - name: explore
    type: builtin
```

**Tools Available:** glob, grep, read

**Use Case:** Find code, understand patterns, search for implementations

**Example:**
```
[/explore]find all authentication-related code[explore/]
```

---

### plan

Create implementation plans (read-only).

```yaml
subagents:
  - name: plan
    type: builtin
```

**Tools Available:** glob, grep, read

**Use Case:** Analyze requirements, design solutions, create step-by-step plans

**Example:**
```
[/plan]design the user authentication system[plan/]
```

---

### memory_read

Retrieve from memory folder (read-only).

```yaml
subagents:
  - name: memory_read
    type: builtin
```

**Tools Available:** read, glob

**Use Case:** Load character definitions, rules, context, facts

**Example:**
```
[/memory_read]get character definition and current context[memory_read/]
```

---

### memory_write

Store to memory folder (read-write).

```yaml
subagents:
  - name: memory_write
    type: builtin
```

**Tools Available:** write, read

**Use Case:** Save facts, update context, store notes

**Example:**
```
[/memory_write]save that the user prefers dark mode[memory_write/]
```

---

### response

Generate user-facing responses.

```yaml
subagents:
  - name: response
    type: builtin
```

**Tools Available:** (none)

**Output:** External (streams to user)

**Use Case:** Generate in-character responses, format output

---

## Builtin Inputs

### cli

Command-line input.

```yaml
input:
  type: cli
  prompt: "> "
```

**Configuration:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| prompt | string | "> " | Input prompt |

---

## Builtin Outputs

### stdout

Standard output (console).

```yaml
output:
  type: stdout
```

**Features:**
- Streaming support
- Automatic flush on newlines

---

## Framework Commands

These commands are available to the LLM for framework interaction.

### info

Get full documentation for a tool or sub-agent.

```
[/info]bash[info/]
```

**Returns:** Full documentation loaded from:
1. `prompts/tools/{name}.md` (agent folder override)
2. `builtin_skills/tools/{name}.md` (package builtins)
3. Tool's `get_full_documentation()` method

---

### jobs

List running background jobs.

```
[/jobs][jobs/]
```

**Returns:** List of running jobs with:
- Job ID
- Type (tool/subagent)
- State (running/done/error)
- Duration
- Output preview

---

### wait

Wait for a background job to complete.

```
[/wait]agent_explore_abc123[wait/]
```

With timeout:
```
[/wait timeout="30"]job_id[wait/]
```

**Arguments:**
| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| job_id | body | Required | Job ID to wait for |
| timeout | @@timeout=... | 60 | Max wait time in seconds |

**Returns:**
- Job result when complete
- Timeout message if exceeded
- Error if job not found

**Notes:**
- Sub-agents always run in background
- Must use `wait` to get sub-agent results
- Without `wait`, results are not delivered

---

## Tool Execution Modes

### DIRECT

Tool completes before returning results.

```python
@property
def execution_mode(self) -> ExecutionMode:
    return ExecutionMode.DIRECT
```

**Behavior:**
- Agent waits for tool to complete
- Result included in same turn

### BACKGROUND

Tool runs in background with status updates.

```python
@property
def execution_mode(self) -> ExecutionMode:
    return ExecutionMode.BACKGROUND
```

**Behavior:**
- Tool starts immediately (non-blocking)
- Status reported: RUNNING → DONE/ERROR
- Use `wait` command for blocking behavior

### STATEFUL

Multi-turn interaction (advanced).

```python
@property
def execution_mode(self) -> ExecutionMode:
    return ExecutionMode.STATEFUL
```

**Behavior:**
- Tool maintains state across calls
- Like generators with yield

---

## Registering Builtins

### Get Builtin Tool

```python
from kohakuterrarium.builtins.tools import get_builtin_tool, BUILTIN_TOOLS

# Get specific tool class
BashTool = get_builtin_tool("bash")
tool = BashTool()

# List all builtin tool names
print(BUILTIN_TOOLS)  # ['bash', 'python', 'read', 'write', 'edit', 'glob', 'grep', 'tree']
```

### Get Builtin Sub-Agent Config

```python
from kohakuterrarium.builtins.subagents import get_builtin_subagent_config, BUILTIN_SUBAGENTS

# Get specific sub-agent config
explore_config = get_builtin_subagent_config("explore")

# List all builtin sub-agent names
print(BUILTIN_SUBAGENTS)  # ['explore', 'plan', 'memory_read', 'memory_write', 'response']
```

---

## Extending Builtins

### Override Tool Documentation

Create `prompts/tools/bash.md` in your agent folder:

```markdown
# bash

Custom documentation for bash tool specific to this agent.

## Custom Guidelines
- Only use for read-only commands
- Avoid destructive operations
```

### Custom Tool Based on Builtin

```python
from kohakuterrarium.builtins.tools.bash import BashTool
from kohakuterrarium.modules.tool.base import ToolResult

class SafeBashTool(BashTool):
    @property
    def tool_name(self) -> str:
        return "safe_bash"

    @property
    def description(self) -> str:
        return "Execute safe, read-only shell commands"

    async def _execute(self, args: dict) -> ToolResult:
        command = args.get("command", "")

        # Block dangerous commands
        dangerous = ["rm", "mv", "dd", "mkfs", ">", ">>"]
        for d in dangerous:
            if d in command:
                return ToolResult(error=f"Blocked dangerous command: {d}")

        return await super()._execute(args)
```

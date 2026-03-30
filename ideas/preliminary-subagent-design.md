# Sub-Agent System Design

> Comprehensive design for KohakuTerrarium's sub-agent system, including builtin sub-agents for common tasks.

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Architecture](#architecture)
3. [Sub-Agent Types](#sub-agent-types)
4. [Builtin Sub-Agents](#builtin-sub-agents)
5. [Memory System Design](#memory-system-design)
6. [Configuration](#configuration)
7. [Implementation Plan](#implementation-plan)

---

## Core Concepts

### What is a Sub-Agent?

A sub-agent is a **nested agent** with:
- Its own Controller (LLM or non-LLM)
- Its own Tool access (configurable, can be limited)
- Configurable output destination (parent controller or external)
- Lifecycle managed by parent

### Key Properties

| Property | Description | Default |
|----------|-------------|---------|
| `tools` | List of allowed tools | Inherited from parent |
| `can_modify` | Whether agent can modify files | `false` |
| `stateless` | No persistent state between calls | `true` |
| `output_to` | Where output goes | `controller` |
| `interactive` | Receives ongoing context updates | `false` |
| `max_turns` | Maximum conversation turns | `10` |
| `timeout` | Maximum execution time | `300s` |
| `model` | LLM model to use | Inherit from parent |

### Sub-Agent vs Tool vs Skill

| Concept | Definition | Use When |
|---------|------------|----------|
| **Tool** | Single function execution | Simple, atomic operations |
| **Sub-Agent** | Nested agent with LLM | Complex, multi-step tasks |
| **Skill** | Procedural knowledge (prompts) | Teaching patterns, not executing |

---

## Architecture

### Parent-Child Communication

```
┌────────────────────────────────────────────────────────────┐
│                    Parent Controller                        │
│                                                            │
│  System Prompt includes:                                   │
│  - Available sub-agents with descriptions                  │
│  - Running sub-agent status                                │
│  - Completed sub-agent results (summary)                   │
│                                                            │
│  Can call: <agent type="explore">query</agent>             │
│  Can read: <read_job>explore_123</read_job>                │
└─────────────────────────┬──────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │  explore  │   │   plan    │   │  memory   │
    │           │   │           │   │           │
    │ Tools:    │   │ Tools:    │   │ Tools:    │
    │ - glob    │   │ - glob    │   │ - read    │
    │ - grep    │   │ - grep    │   │ - write   │
    │ - read    │   │ - read    │   │ - glob    │
    │           │   │           │   │           │
    │ Returns:  │   │ Returns:  │   │ Returns:  │
    │ findings  │   │ plan.md   │   │ memories  │
    └───────────┘   └───────────┘   └───────────┘
```

### Output Modes

1. **Controller Output** (default)
   - Sub-agent returns results to parent controller
   - Parent decides what to do with results
   - Used for: search, planning, memory operations

2. **External Output** (`output_to: external`)
   - Sub-agent streams directly to user
   - Parent receives completion notification only
   - Used for: response generation, TTS streaming

3. **Interactive** (`interactive: true`)
   - Sub-agent stays alive between calls
   - Receives context updates from parent
   - Used for: conversational output agents

---

## Sub-Agent Types

### Classification

```
Sub-Agents
├── Worker Agents (output_to: controller)
│   ├── Read-Only Workers
│   │   ├── ExploreAgent      - Search codebase
│   │   ├── PlanAgent         - Create implementation plans
│   │   ├── ReviewAgent       - Analyze code quality
│   │   └── MemoryReadAgent   - Search/retrieve memories
│   │
│   └── Read-Write Workers
│       ├── CoderAgent        - Implement changes
│       ├── TestAgent         - Run and analyze tests
│       └── MemoryWriteAgent  - Store new memories
│
└── Output Agents (output_to: external)
    ├── ResponseAgent         - Generate user responses
    └── StreamAgent           - Continuous output (TTS)
```

---

## Builtin Sub-Agents

### 1. ExploreAgent (Read-Only Search)

**Purpose**: Search and understand codebase without modifications.

```yaml
name: explore
description: Search codebase to find files, patterns, and understand structure
tools: [glob, grep, read]
can_modify: false
stateless: true
max_turns: 8
timeout: 120

system_prompt: |
  You are an exploration agent. Search the codebase to answer questions.

  CAPABILITIES:
  - glob: Find files by pattern
  - grep: Search content by regex
  - read: Examine file contents

  GUIDELINES:
  - Start broad, then narrow down
  - Report file paths with line numbers
  - Summarize findings concisely
  - DO NOT suggest modifications

  OUTPUT FORMAT:
  Provide a structured summary:
  1. What you searched for
  2. Key findings (files, patterns, locations)
  3. Relevant code snippets (brief)
```

**When to Use**:
- "Find where X is defined"
- "What files use Y?"
- "How does the authentication work?"
- "List all API endpoints"

---

### 2. PlanAgent (Implementation Planning)

**Purpose**: Create detailed implementation plans without executing.

```yaml
name: plan
description: Analyze requirements and create step-by-step implementation plans
tools: [glob, grep, read]
can_modify: false
stateless: true
max_turns: 10
timeout: 180

system_prompt: |
  You are a planning agent. Create implementation plans based on requirements.

  PROCESS:
  1. Understand the requirement
  2. Explore relevant code
  3. Identify affected files
  4. Create step-by-step plan

  OUTPUT FORMAT:
  ## Plan: [Title]

  ### Overview
  Brief description of what will be implemented.

  ### Affected Files
  - path/to/file1.py - reason
  - path/to/file2.py - reason

  ### Steps
  1. [ ] Step description
     - File: path/to/file.py
     - Changes: what to modify
  2. [ ] Next step...

  ### Considerations
  - Edge cases
  - Testing needs
  - Potential issues
```

**When to Use**:
- "Plan how to implement X"
- "Design the architecture for Y"
- "What changes are needed for Z?"

---

### 3. CoderAgent (Code Implementation)

**Purpose**: Write and modify code for specific tasks.

```yaml
name: coder
description: Implement code changes based on specifications
tools: [read, write, edit, bash, python]
can_modify: true
stateless: true
max_turns: 15
timeout: 300

system_prompt: |
  You are a coding agent. Implement the requested changes.

  PROCESS:
  1. Read existing code first
  2. Understand the context
  3. Make minimal, focused changes
  4. Verify syntax is correct

  GUIDELINES:
  - Use edit for modifications, write for new files
  - Follow existing code style
  - Add comments only where logic is complex
  - No unnecessary refactoring

  TOOLS:
  - read: Examine existing code
  - edit: Modify existing files (old_string → new_string)
  - write: Create new files
  - bash: Run commands if needed
  - python: Test Python snippets
```

**When to Use**:
- "Implement feature X"
- "Fix bug Y"
- "Add function Z to module W"

---

### 4. TestAgent (Testing)

**Purpose**: Run and analyze tests.

```yaml
name: test
description: Execute tests and analyze results
tools: [bash, python, read, glob, grep]
can_modify: false
stateless: true
max_turns: 8
timeout: 300

system_prompt: |
  You are a testing agent. Run tests and report results.

  PROCESS:
  1. Identify relevant test files
  2. Run appropriate test commands
  3. Analyze output
  4. Report findings

  DO NOT:
  - Modify test files
  - Modify source code
  - Skip failing tests

  OUTPUT FORMAT:
  ## Test Results

  ### Summary
  - Total: X tests
  - Passed: Y
  - Failed: Z

  ### Failures (if any)
  - test_name: reason for failure

  ### Recommendations
  - What needs to be fixed
```

**When to Use**:
- "Run tests for X"
- "Verify changes work"
- "Check for regressions"

---

### 5. ReviewAgent (Code Review)

**Purpose**: Analyze code quality and suggest improvements.

```yaml
name: review
description: Review code for quality, bugs, and improvements
tools: [glob, grep, read]
can_modify: false
stateless: true
max_turns: 10
timeout: 180

system_prompt: |
  You are a code review agent. Analyze code quality.

  CHECK FOR:
  - Logic errors and bugs
  - Security vulnerabilities
  - Performance issues
  - Code style violations
  - Missing error handling

  OUTPUT FORMAT:
  ## Code Review: [file/feature]

  ### Critical Issues
  - Issue description (file:line)

  ### Suggestions
  - Improvement idea

  ### Good Practices Found
  - What's done well
```

---

### 6. MemoryReadAgent (Memory Retrieval)

**Purpose**: Search and retrieve from memory system.

```yaml
name: memory_read
description: Search and retrieve relevant memories
tools: [glob, grep, read]
can_modify: false
stateless: true
max_turns: 5
timeout: 60

system_prompt: |
  You are a memory retrieval agent. Find relevant information from memory.

  MEMORY STRUCTURE:
  memory/
  ├── context.md      - Current conversation context
  ├── preferences.md  - User preferences
  ├── facts.md        - Learned facts
  └── history/        - Past interactions

  PROCESS:
  1. Understand what information is needed
  2. Search relevant memory files
  3. Extract pertinent information
  4. Return concise summary

  OUTPUT FORMAT:
  ## Retrieved Memories

  ### Relevant to: [query]
  - Memory 1: content (source: file.md)
  - Memory 2: content (source: file.md)

  ### Confidence: high/medium/low
```

**When to Use**:
- "What did we discuss about X?"
- "What are user's preferences for Y?"
- "Find relevant context for Z"

---

### 7. MemoryWriteAgent (Memory Storage)

**Purpose**: Store new information to memory system.

```yaml
name: memory_write
description: Store new information in memory
tools: [read, write, edit, glob]
can_modify: true
stateless: true
max_turns: 5
timeout: 60

system_prompt: |
  You are a memory storage agent. Save important information.

  MEMORY TYPES:
  - preferences.md: User preferences and settings
  - facts.md: Learned facts about user/project
  - context.md: Current session context

  GUIDELINES:
  - Deduplicate: Don't store if already exists
  - Organize: Use consistent formatting
  - Concise: Store essence, not verbatim
  - Protected: Some files are read-only (check first)

  PROCESS:
  1. Read target file first
  2. Check for duplicates
  3. Append or update appropriately
  4. Confirm storage

  OUTPUT: "Stored: [summary]" or "Already exists: [reference]"
```

**When to Use**:
- Store user preferences
- Remember important facts
- Update context after conversation

---

## Memory System Design

### First-Citizen Memory (Folder-Based)

The builtin memory system uses a simple folder structure with markdown files.

```
memory/
├── README.md           # Memory system documentation (protected)
├── rules.md            # Agent rules/constraints (protected)
├── preferences.md      # User preferences (read-write)
├── facts.md            # Learned facts (read-write)
├── context.md          # Current context (read-write)
├── skills.md           # Learned skills/patterns (read-write)
└── history/            # Historical interactions
    ├── 2024-01.md
    └── 2024-02.md
```

### Memory File Format

```markdown
# Preferences

## Code Style
- Prefers TypeScript over JavaScript
- Uses 2-space indentation
- Likes functional programming patterns

## Communication
- Prefers concise responses
- Wants explanations for complex changes

---
Last updated: 2024-01-15
```

### Protected vs Editable

- **Protected files** (marked in config): Agent can read but not modify
- **Editable files**: Agent can read, append, and modify
- **Notes**: Agent can add notes in special blocks beside protected content

```markdown
# Rules (PROTECTED)

Never delete user files without confirmation.

<!-- AGENT NOTE: User is very cautious about deletions -->
```

### Memory Operations

| Operation | Sub-Agent | Description |
|-----------|-----------|-------------|
| Search | `memory_read` | Find relevant memories |
| Retrieve | `memory_read` | Get specific memory content |
| Store | `memory_write` | Add new memory |
| Update | `memory_write` | Modify existing memory |
| Summarize | `memory_write` | Compact old memories |

---

## Configuration

### Agent Config with Sub-Agents

```yaml
# config.yaml

name: my_agent
model: gpt-4o

# Sub-agent definitions
subagents:
  explore:
    tools: [glob, grep, read]
    prompt_file: prompts/subagents/explore.md
    can_modify: false
    max_turns: 8

  plan:
    tools: [glob, grep, read]
    prompt_file: prompts/subagents/plan.md
    can_modify: false
    max_turns: 10

  coder:
    tools: [read, write, edit, bash, python]
    prompt_file: prompts/subagents/coder.md
    can_modify: true
    max_turns: 15

  memory_read:
    tools: [glob, grep, read]
    prompt_file: prompts/subagents/memory_read.md
    can_modify: false
    max_turns: 5
    memory_path: ./memory

  memory_write:
    tools: [read, write, edit, glob]
    prompt_file: prompts/subagents/memory_write.md
    can_modify: true
    max_turns: 5
    memory_path: ./memory

# Memory configuration
memory:
  path: ./memory
  protected:
    - rules.md
    - README.md
  auto_load:
    - context.md      # Always in context
    - preferences.md  # Always in context
```

### Sub-Agent Call Syntax

```xml
<agent type="explore">
Find all files that handle user authentication
</agent>

<agent type="plan">
Plan implementation of dark mode toggle
</agent>

<agent type="memory_read">
What are user's code style preferences?
</agent>
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

1. **SubAgent Base Class**
   ```python
   class SubAgent:
       config: SubAgentConfig
       controller: Controller
       registry: Registry  # Limited tool set

       async def run(self, task: str) -> SubAgentResult
   ```

2. **SubAgentManager**
   - Lifecycle management (spawn, monitor, cleanup)
   - Status tracking for parent visibility
   - Resource limits and timeouts

3. **SubAgentTool**
   - Tool for parent to spawn sub-agents
   - Handles call syntax parsing
   - Routes to appropriate sub-agent type

### Phase 2: Builtin Sub-Agents

1. **ExploreAgent** - Search/exploration
2. **PlanAgent** - Implementation planning
3. **MemoryReadAgent** - Memory retrieval
4. **MemoryWriteAgent** - Memory storage

### Phase 3: Advanced Sub-Agents

1. **CoderAgent** - Code implementation
2. **TestAgent** - Test execution
3. **ReviewAgent** - Code review

### Phase 4: Output Sub-Agents

1. **ResponseAgent** - Generate responses
2. **Interactive mode** - Context updates

### File Structure

```
src/kohakuterrarium/
├── modules/
│   └── subagent/
│       ├── __init__.py
│       ├── base.py          # SubAgent base class
│       ├── manager.py       # SubAgentManager
│       ├── config.py        # SubAgentConfig
│       └── tool.py          # SubAgentTool (for spawning)
│
├── builtins/
│   └── subagents/
│       ├── __init__.py
│       ├── explore.py       # ExploreAgent
│       ├── plan.py          # PlanAgent
│       ├── coder.py         # CoderAgent
│       ├── test.py          # TestAgent
│       ├── review.py        # ReviewAgent
│       ├── memory_read.py   # MemoryReadAgent
│       └── memory_write.py  # MemoryWriteAgent
│
└── builtin_skills/
    └── subagents/
        ├── explore.md       # ExploreAgent prompt
        ├── plan.md          # PlanAgent prompt
        ├── coder.md         # CoderAgent prompt
        ├── test.md          # TestAgent prompt
        ├── review.md        # ReviewAgent prompt
        ├── memory_read.md   # MemoryReadAgent prompt
        └── memory_write.md  # MemoryWriteAgent prompt
```

---

## Example Workflow

### SWE Agent: "Add user authentication"

```
User: "Add authentication to the API"
                    │
                    ▼
            Main Controller
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
<agent:explore>  <agent:explore>  <agent:memory_read>
"Find existing   "Find API        "Auth preferences?"
auth code"       endpoints"
    │               │               │
    └───────┬───────┘               │
            ▼                       ▼
    Results combined          "Prefers JWT"
            │                       │
            └───────────┬───────────┘
                        ▼
                <agent:plan>
                "Plan JWT auth implementation"
                        │
                        ▼
                Step-by-step plan
                        │
                        ▼
            For each step:
                <agent:coder>
                "Implement step N"
                        │
                        ▼
                <agent:test>
                "Run auth tests"
                        │
                        ▼
                Main Controller
                summarizes to user
```

---

## Open Questions

1. **Model Selection**: Should sub-agents use same model or cheaper/faster?
   - Recommendation: Configurable per sub-agent, default to parent

2. **Parallel Execution**: When to run multiple sub-agents?
   - Independent searches: parallel
   - Sequential dependencies: serial

3. **Context Sharing**: Should sub-agents see parent's conversation?
   - Default: No (stateless)
   - Optional: Pass relevant context in task

4. **Error Recovery**: What if sub-agent fails?
   - Return error to parent
   - Parent decides: retry, skip, or fail

5. **Token Limits**: How to handle long sub-agent outputs?
   - Truncate with summary
   - Let parent request more via `<read_job>`

---

*Document Version: 1.0*
*Created: Based on initial_discussion.md and subagent_design.md*

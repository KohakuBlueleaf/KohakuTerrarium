# Creature System

Creatures are pre-built agent personalities with tools, sub-agents, and system prompts. They form a hierarchy where specialized creatures inherit from a general-purpose base.

## How It Works

Every creature lives in the `creatures/` directory at the project root. Each creature has:

- `config.yaml` -- tools, sub-agents, controller settings
- `prompts/system.md` -- system prompt additions

Agents in `agents/` point to a creature via `base_config` and inherit everything. The agent only needs to specify what differs (model, API key, input/output).

## Creature Hierarchy

```
creatures/
  general/          <-- Base: 16 tools, 6 sub-agents, core personality
    |
    +-- swe/        <-- Software engineering workflow, git safety
    +-- reviewer/   <-- Code review, severity levels, structured feedback
    +-- ops/        <-- Infrastructure, CI/CD, deployment, monitoring
    +-- researcher/ <-- Research methodology, source evaluation
    +-- root/       <-- Terrarium management, task delegation
```

All specialized creatures inherit from `general`. They add domain-specific prompt sections and optionally extend the tool set.

## Inheritance Rules

When a config has `base_config`, the loader:

1. Loads the base config as the foundation
2. Merges child config on top using these rules:

| Type | Merge Strategy |
|------|---------------|
| Scalars (model, temperature) | Child overrides base |
| Dicts (controller, input, output) | Shallow merge -- child keys override |
| tools, subagents | Child entries EXTEND base list (deduplicated by name) |
| system_prompt_file | Base prompt loaded first, child prompt APPENDED |

### Multi-level Inheritance

Inheritance is recursive. If creature A inherits from B which inherits from C, the final config is C + B + A (each layer extending the previous).

### System Prompt Concatenation

The system prompt is assembled from the full inheritance chain. For an agent inheriting from `creatures/swe`:

1. `creatures/general/prompts/system.md` (identity, communication, safety)
2. `creatures/swe/prompts/system.md` (code editing, git, validation)

The prompts are joined with double newlines. The result is a single coherent system prompt with the general foundation followed by specialized additions.

## Default Creatures

### General

The foundation creature. Handles 80% of tasks without specialization.

- **Tools (16)**: bash, read, write, edit, glob, grep, tree, think, scratchpad, ask_user, http, json_read, json_write, send_message, wait_channel, python
- **Sub-agents (6)**: explore, plan, worker, critic, summarize, research
- **Prompt sections**: Identity, Communication, Approaching Tasks, Progress Updates, Tool Usage, Output, Safety

### SWE

Software engineering specialist. Inherits everything from general and adds coding workflow.

- **Additional prompt sections**: Workflow (understand/search/read/plan/implement/validate), Code Editing (smallest correct change), Git Safety, Validation
- **Controller**: `reasoning_effort: high` (overrides general's medium)
- **Tool set**: Inherited from general (no additions needed)

### Reviewer

Code review specialist. Inherits everything from general and adds structured review methodology.

- **Additional prompt sections**: Philosophy (catch bugs not style nits), Severity Levels (critical/bug/warning/suggestion), What to Check (logic, security, concurrency, resources), Output (structured findings with verdict)
- **Controller**: `reasoning_effort: high` (overrides general's medium)
- **Tool set**: Inherited from general

### Ops

Infrastructure and operations specialist. Inherits everything from general and adds deployment/monitoring methodology.

- **Additional prompt sections**: Philosophy (stability first, boring over clever), Before Any Change (check state, plan rollback), Infrastructure (Docker, CI, config management), Monitoring & Debugging (logs before hypotheses), Cloud & Networking (least privilege, tagging)
- **Tool set**: Inherited from general

### Researcher

Research and analysis specialist. Inherits everything from general and adds research methodology.

- **Additional prompt sections**: Approach (multiple sources, reliability evaluation), Output (citations, confidence levels)
- **Tool set**: Inherited from general

### Root

Terrarium manager. Inherits from general and adds multi-agent management tools.

- **Additional prompt sections**: Terrarium Management (workflow, when to delegate, how to manage)
- **Additional tools (7)**: terrarium_create, terrarium_status, terrarium_stop, terrarium_send, terrarium_observe, creature_start, creature_stop

## Creating Your Own Agent

### Minimal Agent (inheriting from a creature)

```yaml
# agents/my_agent/config.yaml
name: my_agent
version: "1.0"
base_config: creatures/swe

controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  tool_format: native

input:
  type: cli
  prompt: "> "

output:
  type: stdout
  controller_direct: true
```

This agent inherits all tools, sub-agents, and system prompts from the SWE creature (which itself inherits from general). It only specifies model, input, and output.

### Agent with Additional Tools

```yaml
name: my_agent
base_config: creatures/general

tools:
  - { name: my_custom_tool, type: custom, module: ./tools/my_tool.py }
```

The custom tool is added on top of general's 16 tools.

### Agent with Custom Prompt Additions

Create `agents/my_agent/prompts/system.md` with your additions:

```markdown
## My Domain

Domain-specific guidelines here.
```

Then in config:

```yaml
name: my_agent
base_config: creatures/general
system_prompt_file: prompts/system.md
```

The general prompt is loaded first, then your prompt is appended.

### Creating a New Creature

To create a new creature that others can inherit from:

```
creatures/
  my_creature/
    config.yaml
    prompts/
      system.md
```

```yaml
# creatures/my_creature/config.yaml
name: my_creature
version: "1.0"
base_config: ../general

system_prompt_file: prompts/system.md

# Extend with additional tools (optional)
tools:
  - { name: special_tool, type: builtin }
```

## System Prompt Design Philosophy

The system prompt follows these principles from the design research:

1. **Progressive disclosure**: Only essential personality and rules in the system prompt. Full tool docs loaded on demand via `##info##`.

2. **The model is smart**: Only include knowledge the model cannot infer. No explanations of general concepts.

3. **Concise over verbose**: The general prompt is ~300-400 tokens. Specialized additions are ~100-200 tokens each. Total system prompt stays under 2000 tokens.

4. **Contrastive guidance**: "For new projects: ambitious and creative. For existing codebases: surgical and precise." Rather than long rule lists, use calibrated oppositions.

5. **No redundancy**: Tool list is auto-generated. Tool call syntax is framework-level. Environment info is injected. The authored prompt only covers personality, methodology, and safety.

## Environment Variable Support

Creature and agent configs support `${VAR:default}` syntax:

```yaml
controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  api_key_env: OPENROUTER_API_KEY
```

Set `OPENROUTER_MODEL` to override the default model.

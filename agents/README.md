# agents/ -- Example Agents

Each subdirectory is a complete agent configuration that demonstrates a different
architecture pattern. Run any agent with:

```bash
uv pip install -e .
python -m kohakuterrarium agents/<agent_name>
```

---

## swe_agent

**Software engineering assistant** (like Claude Code / Codex CLI).

- **Pattern:** Controller with direct output -- the controller itself writes to stdout
- **Tools:** bash, python, read, write, edit, glob, grep, think, scratchpad, ask_user
- **Sub-agents:** explore, plan, worker, critic, summarize
- **Key features:** `controller_direct: true`, keyword termination (`TASK_COMPLETE`), 100-turn limit
- **Config:** [config.yaml](swe_agent/config.yaml)

## swe_agent_tui

**Software engineering assistant with TUI input/output.**

- **Pattern:** Same as swe_agent but uses TUI modules for richer terminal experience
- **Tools:** bash, python, read, write, edit, glob, grep, think, scratchpad, ask_user
- **Sub-agents:** explore, plan, worker, critic, summarize
- **Key features:** `input: {type: tui}`, `output: {type: tui}`, shared TUI session via session registry
- **Config:** [config.yaml](swe_agent_tui/config.yaml)

## multi_agent

**Multi-agent coordination** with parallel sub-agent dispatch.

- **Pattern:** Controller dispatches tasks to specialized sub-agents via channels
- **Tools:** send_message, wait_channel, scratchpad, think, read, write, edit, bash, glob, grep, http
- **Sub-agents:** explore, research, worker, coordinator, summarize, critic
- **Key features:** Channel-based communication, coordinator sub-agent, 30-turn limit
- **Config:** [config.yaml](multi_agent/config.yaml)

## planner_agent

**Plan-execute-reflect loop** with scratchpad tracking.

- **Pattern:** Plan steps with `plan` sub-agent, execute with `worker`, review with `critic`
- **Tools:** read, write, edit, bash, glob, grep, scratchpad, think
- **Sub-agents:** plan (with custom extra prompt), worker, critic (PASS/FAIL review), summarize
- **Key features:** Scratchpad for plan state, critic extra_prompt for step review, 50-turn limit
- **Config:** [config.yaml](planner_agent/config.yaml)

## monitor_agent

**Trigger-driven autonomous monitoring** (no user input).

- **Pattern:** Timer and channel triggers fire health checks without user interaction
- **Tools:** bash, http, read, scratchpad, send_message, think
- **Sub-agents:** explore, summarize
- **Triggers:** 60s timer (immediate first fire), `monitor_alerts` channel trigger
- **Key features:** `input: {type: none}` (NoneInput -- blocks forever, trigger-only), custom alert output module, 24h max_duration
- **Config:** [config.yaml](monitor_agent/config.yaml)

## conversational

**Streaming ASR/TTS conversational agent** (Neuro-sama style).

- **Pattern:** Whisper input, interactive output sub-agent streams to TTS
- **Tools:** read, write, think, scratchpad
- **Sub-agents:** memory_read, memory_write, research, critic, output (interactive), memory_writer (custom)
- **Key features:** `whisper` input with VAD, `interrupt_restart` context mode, `output_to: external`
- **Requires:** `pip install -e ".[asr]"` and FFmpeg
- **Config:** [config.yaml](conversational/config.yaml)

## discord_bot

**Group chat bot** with memory and character.

- **Pattern:** Custom Discord I/O, ephemeral controller, named output routing
- **Tools:** tree, read, write, edit, glob, grep, emoji_search, emoji_list, emoji_get (custom)
- **Sub-agents:** memory_read, memory_write
- **Key features:** `ephemeral: true` controller, custom input/output modules, multimodal images, keyword filtering, drop-chance for stale responses, named output (`[/output_discord]`)
- **Config:** [config.yaml](discord_bot/config.yaml)

## rp_agent

**Character roleplay** with memory-first architecture.

- **Pattern:** Controller manages memory + character state, interactive output sub-agent generates responses
- **Tools:** tree, read, write, edit, grep, glob
- **Sub-agents:** memory_read, memory_write, output (interactive with `interrupt_restart`)
- **Key features:** `startup_trigger` loads character on boot, `controller_direct: false`, protected memory files (character.md, rules.md)
- **Config:** [config.yaml](rp_agent/config.yaml)

---

## Common Configuration Patterns

| Pattern | Example Agent | Key Config |
|---------|---------------|------------|
| Direct output | swe_agent | `controller_direct: true` |
| TUI input/output | swe_agent_tui | `input: {type: tui}`, `output: {type: tui}` |
| Output sub-agent | rp_agent, conversational | `output_to: external`, `interactive: true` |
| Ephemeral mode | discord_bot | `ephemeral: true` |
| Trigger-only (no input) | monitor_agent | `input: {type: none}`, `triggers:` |
| Channel messaging | multi_agent | `send_message` + `wait_channel` tools |
| Startup trigger | rp_agent | `startup_trigger: { prompt: "..." }` |
| Named outputs | discord_bot | `named_outputs: { discord: ... }` |
| Shared session | (any pair) | `session_key: shared_key` on multiple agents |
| Custom I/O | discord_bot | `type: custom`, `module:`, `class:` |

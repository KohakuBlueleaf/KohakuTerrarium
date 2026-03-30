# Examples

## Agent Apps (`agent-apps/`)

Single-agent configurations demonstrating different architecture patterns.

```bash
uv pip install -e .
kt examples/agent-apps/<agent_name>
```

| Agent | Pattern | Key Feature |
|-------|---------|-------------|
| swe_agent | SWE assistant (CLI) | `base_config: creatures/swe`, direct output |
| swe_agent_tui | SWE assistant (TUI) | TUI input/output, inline tool display |
| discord_bot | Group chat bot | Custom Discord I/O, ephemeral, native tool calling |
| planner_agent | Plan-execute-reflect | Scratchpad tracking, critic review |
| monitor_agent | Trigger-driven monitoring | No user input, timer triggers |
| conversational | Streaming ASR/TTS | Whisper input, interactive output sub-agent |
| rp_agent | Character roleplay | Memory-first, startup trigger |

## Terrariums (`terrariums/`)

Multi-agent configurations demonstrating creature coordination.

```bash
kt --terrarium examples/terrariums/<terrarium_name>
```

| Terrarium | Creatures | Root | Topology |
|-----------|-----------|------|----------|
| novel_terrarium | brainstorm, planner, writer | No | Pipeline with feedback loop |
| swe_team_managed_tui | swe, reviewer | Yes (TUI) | Root agent manages team via TUI |

## Code (`code/`)

Programmatic usage examples for embedding agents in applications.

## Notes

- These are example configurations, not the default creature/terrarium templates
- Default creatures live in `creatures/` at project root
- Default terrarium templates live in `terrariums/` at project root
- Examples may need updating as the framework evolves

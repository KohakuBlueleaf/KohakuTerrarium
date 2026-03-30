"""
Critic sub-agent - review and self-critique.

Evaluates proposed actions, code changes, or outputs and provides
structured feedback with severity-rated issues and suggestions.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

CRITIC_SYSTEM_PROMPT = """\
You are a code reviewer. Examine the given changes.
- Prioritize bugs, risks, and behavioral regressions
- Present findings by severity with file:line references
- Note missing tests or edge cases
- Keep summaries brief -- findings first
- If no issues found, say so and note residual risks
"""

CRITIC_CONFIG = SubAgentConfig(
    name="critic",
    description="Review and critique code, plans, or outputs",
    tools=["read", "glob", "grep", "tree", "bash"],
    system_prompt=CRITIC_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

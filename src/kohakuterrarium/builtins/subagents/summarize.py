"""
Summarize sub-agent - content summarization.

Condenses long content into concise, actionable summaries.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

SUMMARIZE_SYSTEM_PROMPT = """\
Summarize the conversation for context continuation.
Focus on: what was done, what's in progress, what's next.
Include: files modified, key decisions, user preferences.
Be comprehensive but concise. Do not answer questions.
"""

SUMMARIZE_CONFIG = SubAgentConfig(
    name="summarize",
    description="Summarize conversation for context continuation",
    tools=[],
    system_prompt=SUMMARIZE_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

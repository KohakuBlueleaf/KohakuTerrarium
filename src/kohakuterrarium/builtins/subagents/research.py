"""
Research sub-agent - Deep research with web access.

Gathers information from local files and external sources to answer
questions thoroughly, citing sources and synthesizing findings.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

RESEARCH_SYSTEM_PROMPT = """\
You are a research agent. Find accurate information.
- Use http tool for web requests
- Evaluate source reliability
- Track all sources in your output
- Distinguish facts from speculation
- Return structured findings with citations
"""

RESEARCH_CONFIG = SubAgentConfig(
    name="research",
    description="Research topics using files and web access",
    tools=["http", "read", "write", "think", "scratchpad"],
    system_prompt=RESEARCH_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

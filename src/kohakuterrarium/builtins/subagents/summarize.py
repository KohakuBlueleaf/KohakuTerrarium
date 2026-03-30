"""
Summarize sub-agent - content summarization.

Condenses long content into concise, actionable summaries.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

SUMMARIZE_SYSTEM_PROMPT = """You are a summarization specialist. Condense long content into concise, actionable summaries.

## Guidelines

1. **Focus on Key Information**
   - Extract the most important points
   - Preserve critical details (names, numbers, paths)
   - Remove redundancy and filler

2. **Structure Your Summary**
   - Lead with the main conclusion or finding
   - Use bullet points for multiple items
   - Keep to 1/3 or less of the original length

3. **Preserve Context**
   - Include file paths and line numbers when relevant
   - Note any assumptions or caveats
   - Flag anything that seems incomplete or unclear

## Output Format

### Summary
Brief overview (1-2 sentences)

### Key Points
- Point 1
- Point 2

### Details (if needed)
Additional relevant information
"""

SUMMARIZE_CONFIG = SubAgentConfig(
    name="summarize",
    description="Summarize long content into concise summaries",
    tools=["read"],
    system_prompt=SUMMARIZE_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

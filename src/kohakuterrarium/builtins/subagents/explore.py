"""
Explore sub-agent - Read-only codebase search.

Searches and explores codebase without making any modifications.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

EXPLORE_SYSTEM_PROMPT = """\
You are a file search specialist. You excel at navigating codebases.
- Use Glob for file pattern matching
- Use Grep for content search with regex
- Use Read for specific files you know the path to
- Use Bash only for read-only operations (ls, git log, etc.)
- Return absolute file paths
- Adapt thoroughness to the caller's requirements
- Do not create or modify any files
"""

EXPLORE_CONFIG = SubAgentConfig(
    name="explore",
    description="Search and explore codebase (read-only)",
    tools=["glob", "grep", "read", "tree", "bash"],
    system_prompt=EXPLORE_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

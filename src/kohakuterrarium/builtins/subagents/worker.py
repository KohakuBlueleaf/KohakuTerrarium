"""Worker sub-agent - general-purpose implementation worker."""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

WORKER_SYSTEM_PROMPT = """\
You are an execution agent. Complete the assigned task.
- You own the files you're given -- edit them directly
- Follow the plan provided by the caller
- If you encounter blockers, document them and continue
- Validate your work before reporting completion
- Report what you changed and why
"""

WORKER_CONFIG = SubAgentConfig(
    name="worker",
    description="Implement code changes, fix bugs, refactor (read-write)",
    tools=["read", "write", "edit", "bash", "glob", "grep"],
    system_prompt=WORKER_SYSTEM_PROMPT,
    can_modify=True,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

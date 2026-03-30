"""
Critic sub-agent - review and self-critique.

Evaluates proposed actions, code changes, or outputs and provides
structured feedback with severity-rated issues and suggestions.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

CRITIC_SYSTEM_PROMPT = """You are a critical reviewer. Evaluate proposed actions, code changes, or outputs and provide structured feedback.

## Review Process

1. **Understand the Intent**
   - What was the goal?
   - What constraints apply?

2. **Check Correctness**
   - Does it do what was intended?
   - Are there logic errors or edge cases?
   - Does it handle errors properly?

3. **Check Quality**
   - Is the code clean and readable?
   - Are there security concerns?
   - Does it follow existing patterns?

4. **Check Completeness**
   - Is anything missing?
   - Are all cases handled?
   - Is documentation adequate?

## Output Format

### Verdict: PASS or FAIL

### Issues Found
1. [severity: high/medium/low] Description
2. ...

### Suggestions
- Suggestion 1
- Suggestion 2

### Summary
Brief overall assessment
"""

CRITIC_CONFIG = SubAgentConfig(
    name="critic",
    description="Review and critique code, plans, or outputs",
    tools=["read", "grep", "glob"],
    system_prompt=CRITIC_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
)

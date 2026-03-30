"""
Response sub-agent - Generate user-facing responses.

This is an output sub-agent that generates responses and can stream
directly to the user. Used for chat agents and role-playing scenarios.
"""

from kohakuterrarium.modules.subagent.config import OutputTarget, SubAgentConfig

RESPONSE_SYSTEM_PROMPT = """You are a response generation agent. Generate appropriate responses to users.

## Role

You receive context from the main controller and generate the actual user-facing response.
The controller decides WHEN to respond - you decide WHAT to say and HOW to say it.

## Context You Receive

The controller will provide:
- Current conversation context
- Retrieved memories (if any)
- User's input/question
- Any relevant information

## Capabilities

- read: Access context files if needed
- No modification tools (output only)

## Guidelines

1. **Response Decision**
   - You CAN decide to stay silent (output nothing)
   - Not every input requires a response
   - Consider if you have anything meaningful to add

2. **Response Style**
   - Be natural and conversational
   - Match the tone of the conversation
   - Be concise unless detail is requested

3. **Memory Integration**
   - Use provided memories naturally
   - Don't explicitly mention "checking memory"
   - Weave context into responses

## Silence Cases

Output nothing (empty response) when:
- Input wasn't directed at you
- You have nothing meaningful to add
- The topic doesn't match your character/role
- It's clearly a rhetorical question

## Output

Simply output your response text directly.
NO formatting, NO headers, NO explanations.

If choosing silence, output exactly: [SILENCE]
"""

# Base response config - typically customized per agent
RESPONSE_CONFIG = SubAgentConfig(
    name="response",
    description="Generate user-facing responses",
    tools=["read"],  # Minimal tools - mainly receives context
    system_prompt=RESPONSE_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    interactive=False,  # Can be set to True for persistent output agent
    output_to=OutputTarget.EXTERNAL,  # Streams to user
    max_turns=50,  # Usually single turn
    timeout=600.0,
)


# Interactive response agent that stays alive
INTERACTIVE_RESPONSE_CONFIG = SubAgentConfig(
    name="response_interactive",
    description="Interactive response agent (stays alive)",
    tools=["read"],
    system_prompt=RESPONSE_SYSTEM_PROMPT,
    can_modify=False,
    stateless=False,  # Maintains conversation
    interactive=True,  # Receives context updates
    output_to=OutputTarget.EXTERNAL,
    max_turns=50,
    timeout=600.0,
)

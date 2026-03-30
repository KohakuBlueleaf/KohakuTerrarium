"""
Memory Read sub-agent - Retrieve from memory system.

Searches and retrieves relevant information from the memory folder.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

MEMORY_READ_SYSTEM_PROMPT = """You are a memory retrieval agent.

## First: Read Tool Documentation

Before using any tool, read its documentation:
[/info]tree[info/]
[/info]read[info/]
[/info]grep[info/]

## Your Process

1. Use tree to list files in the memory path
2. Read relevant files based on what you're looking for
3. Use grep if searching for specific content across files
4. Report what you found

## Rules

- ALWAYS use tree first to discover files
- NEVER guess file names
- NEVER put tool calls in code blocks - write them directly
- Wait for tool results before responding
"""

MEMORY_READ_CONFIG = SubAgentConfig(
    name="memory_read",
    description="Search and retrieve from memory",
    tools=["tree", "read", "grep"],
    system_prompt=MEMORY_READ_SYSTEM_PROMPT,
    can_modify=False,
    stateless=True,
    max_turns=50,
    timeout=600.0,
    memory_path="./memory",
)

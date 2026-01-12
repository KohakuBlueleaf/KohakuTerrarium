"""
Memory Write sub-agent - Store to memory system.

Stores new information and updates existing memories.
"""

from kohakuterrarium.modules.subagent.config import SubAgentConfig

MEMORY_WRITE_SYSTEM_PROMPT = """You are a memory storage agent.

## Your Process

1. Use tree to list existing files in the memory path
2. If updating an existing file: read it first, then write the complete updated content
3. If creating a new file: just write directly (creates directories automatically)

## Tool Usage

For memory files, prefer the simple approach:
1. Read the file to see current content
2. Write the complete updated file (with your changes merged in)

The write tool is simpler and more reliable than edit for small files.

## Rules

- ALWAYS use tree first to see existing files
- For EXISTING files: read first, then write with merged content
- For NEW files: just write directly
- NEVER modify protected files (character.md, rules.md)
- Keep content organized and append new info appropriately
- NEVER put tool calls in code blocks - write them directly
- You CAN create subdirectories like channels/, users/, topics/ to organize memory
"""

MEMORY_WRITE_CONFIG = SubAgentConfig(
    name="memory_write",
    description="Store information to memory (can create files)",
    tools=["tree", "read", "write"],
    system_prompt=MEMORY_WRITE_SYSTEM_PROMPT,
    can_modify=True,
    stateless=True,
    max_turns=5,
    timeout=60.0,
    memory_path="./memory",
)

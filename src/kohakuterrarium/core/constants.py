"""
Framework-wide constants.

Centralizes magic numbers and default values used across modules.
"""

# Tool result truncation limits
TOOL_RESULT_MAX_CHARS = 2000  # Max chars for tool results fed back to controller
STATUS_PREVIEW_MAX_CHARS = 500  # Max chars for background job status previews
COMPLETION_EVENT_MAX_CHARS = 1000  # Max chars for completion event content
SUBAGENT_TOOL_OUTPUT_MAX_CHARS = 1500  # Max chars for sub-agent tool output preview
TOOL_OUTPUT_PREVIEW_CHARS = 200  # Max chars for job status preview field

"""
SessionOutput - OutputModule that persists events to SessionStore.

Added as a secondary output on the agent's output router (same pattern
as the WS StreamOutput). Captures text, tool activity, processing state,
trigger events, and token usage without modifying the processing loop.
"""

import time
from typing import Any

from kohakuterrarium.modules.output.base import OutputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class SessionOutput(OutputModule):
    """Output module that records events to a SessionStore.

    Accumulates streaming text chunks and flushes as one event
    on processing_end. Tool/subagent activity recorded immediately.
    Saves conversation snapshot and agent state after each processing cycle.
    """

    def __init__(self, agent_name: str, store: Any, agent: Any):
        self._agent_name = agent_name
        self._store = store
        self._agent = agent  # direct reference, not dict lookup
        self._text_buffer: list[str] = []

    def _record(self, event_type: str, data: dict) -> None:
        """Record an event."""
        try:
            self._store.append_event(self._agent_name, event_type, data)
        except Exception as e:
            logger.debug("Session record failed", error=str(e))

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def write(self, text: str) -> None:
        if text:
            self._text_buffer.append(text)

    async def write_stream(self, chunk: str) -> None:
        if chunk:
            self._text_buffer.append(chunk)

    async def flush(self) -> None:
        pass

    async def on_processing_start(self) -> None:
        self._text_buffer.clear()
        self._record("processing_start", {})

    async def on_processing_end(self) -> None:
        # Flush accumulated text as one event
        if self._text_buffer:
            text = "".join(self._text_buffer)
            if text.strip():
                self._record("text", {"content": text})
            self._text_buffer.clear()

        self._record("processing_end", {})

        # Save conversation snapshot (raw messages list, not JSON)
        try:
            if self._agent and hasattr(self._agent, "controller"):
                messages = self._agent.controller.conversation.to_messages()
                self._store.save_conversation(self._agent_name, messages)
        except Exception as e:
            logger.warning("Conversation snapshot failed", error=str(e))

        # Save agent state (scratchpad, turn count, token usage)
        try:
            if self._agent:
                state_kwargs = {}

                # Scratchpad
                if hasattr(self._agent, "session") and self._agent.session:
                    pad = self._agent.session.scratchpad
                    if hasattr(pad, "to_dict"):
                        state_kwargs["scratchpad"] = pad.to_dict()

                # Token usage from controller
                if hasattr(self._agent, "controller"):
                    usage = getattr(self._agent.controller, "_last_usage", {})
                    if usage:
                        state_kwargs["token_usage"] = usage

                if state_kwargs:
                    self._store.save_state(self._agent_name, **state_kwargs)
        except Exception as e:
            logger.debug("State save failed", error=str(e))

    def on_activity(self, activity_type: str, detail: str) -> None:
        name, info = _parse_detail(detail)
        self._flush_text_before_activity()
        self._record_activity(activity_type, name, info, {})

    def on_activity_with_metadata(
        self, activity_type: str, detail: str, metadata: dict
    ) -> None:
        name, info = _parse_detail(detail)
        self._flush_text_before_activity()
        self._record_activity(activity_type, name, info, metadata)

    def _flush_text_before_activity(self) -> None:
        if self._text_buffer:
            text = "".join(self._text_buffer)
            if text.strip():
                self._record("text", {"content": text})
            self._text_buffer.clear()

    def _record_activity(
        self, activity_type: str, name: str, detail: str, metadata: dict
    ) -> None:
        if activity_type == "trigger_fired":
            self._record(
                "trigger_fired",
                {
                    "trigger_id": metadata.get("trigger_id", ""),
                    "channel": metadata.get("channel", ""),
                    "sender": metadata.get("sender", ""),
                    "content": metadata.get("content", ""),
                },
            )
        elif activity_type == "tool_start":
            self._record(
                "tool_call",
                {
                    "name": name,
                    "call_id": metadata.get("job_id", ""),
                    "args": metadata.get("args", {}),
                },
            )
        elif activity_type == "tool_done":
            self._record(
                "tool_result",
                {
                    "name": name,
                    "call_id": metadata.get("job_id", ""),
                    "output": detail,
                    "exit_code": 0,
                },
            )
        elif activity_type == "tool_error":
            self._record(
                "tool_result",
                {
                    "name": name,
                    "call_id": metadata.get("job_id", ""),
                    "output": detail,
                    "exit_code": 1,
                    "error": detail,
                },
            )
        elif activity_type == "subagent_start":
            self._record(
                "subagent_call",
                {
                    "name": name,
                    "task": metadata.get("task", detail),
                    "job_id": metadata.get("job_id", ""),
                },
            )
        elif activity_type == "subagent_done":
            self._record(
                "subagent_result",
                {
                    "name": name,
                    "job_id": metadata.get("job_id", ""),
                    "output": metadata.get("result", detail),
                    "tools_used": metadata.get("tools_used", []),
                    "turns": metadata.get("turns", 0),
                    "duration": metadata.get("duration", 0),
                },
            )
        elif activity_type == "subagent_error":
            self._record(
                "subagent_result",
                {
                    "name": name,
                    "job_id": metadata.get("job_id", ""),
                    "output": detail,
                    "error": detail,
                    "success": False,
                },
            )
        elif activity_type == "token_usage":
            self._record(
                "token_usage",
                {
                    "prompt_tokens": metadata.get("prompt_tokens", 0),
                    "completion_tokens": metadata.get("completion_tokens", 0),
                    "total_tokens": metadata.get("total_tokens", 0),
                },
            )
        elif activity_type.startswith("subagent_tool_"):
            self._record(
                "subagent_tool",
                {
                    "subagent": metadata.get("subagent", name),
                    "tool_name": metadata.get("tool", ""),
                    "activity": activity_type.replace("subagent_", ""),
                    "detail": metadata.get("detail", detail),
                },
            )
        elif activity_type == "processing_complete":
            self._record(
                "processing_complete",
                {
                    "trigger_channel": metadata.get("trigger_channel", ""),
                    "trigger_sender": metadata.get("trigger_sender", ""),
                    "output_preview": metadata.get("output_preview", ""),
                },
            )
        else:
            self._record(
                f"activity:{activity_type}",
                {"name": name, "detail": detail, **metadata},
            )


def _parse_detail(detail: str) -> tuple[str, str]:
    """Extract [name] prefix from detail string."""
    try:
        if detail.startswith("["):
            end = detail.index("]", 1)
            return detail[1:end], detail[end + 2 :]
    except ValueError:
        pass
    return "unknown", detail

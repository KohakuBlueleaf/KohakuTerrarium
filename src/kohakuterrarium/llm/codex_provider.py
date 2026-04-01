"""
Codex OAuth LLM provider - uses ChatGPT subscription for model access.

Uses the OpenAI Python SDK with the Codex backend endpoint. Authenticates
via OAuth PKCE (browser or device code flow). Billing goes to the user's
ChatGPT Plus/Pro subscription, not API credits.
"""

import asyncio
import json as _json
from typing import Any, AsyncIterator

from kohakuterrarium.llm.base import (
    BaseLLMProvider,
    ChatResponse,
    NativeToolCall,
    ToolSchema,
)
from kohakuterrarium.llm.codex_auth import (
    CodexTokens,
    oauth_login,
    refresh_tokens,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


class CodexOAuthProvider(BaseLLMProvider):
    """LLM provider using ChatGPT subscription via Codex OAuth.

    Uses the OpenAI SDK's Responses API routed through the Codex backend.
    Supports streaming, tool calls, and auto token refresh.

    Usage:
        provider = CodexOAuthProvider(model="gpt-5.4")
        await provider.ensure_authenticated()

        async for chunk in provider.chat(messages, stream=True):
            print(chunk, end="")
    """

    def __init__(
        self,
        model: str = "gpt-5.4",
        *,
        reasoning_effort: str = "medium",
        service_tier: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 2,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort  # none/minimal/low/medium/high/xhigh
        self.service_tier = service_tier  # None/priority/flex
        self.timeout = timeout
        self.max_retries = max_retries
        self._tokens: CodexTokens | None = None
        self._client: Any = None  # openai.OpenAI
        self._last_tool_calls: list[NativeToolCall] = []
        self._last_usage: dict[str, int] = {}

    async def ensure_authenticated(self) -> None:
        """Ensure valid tokens exist. Opens browser/device code if needed."""
        self._tokens = CodexTokens.load()

        if self._tokens and self._tokens.is_expired():
            try:
                self._tokens = await refresh_tokens(self._tokens)
            except Exception as e:
                logger.warning("Token refresh failed", error=str(e))
                self._tokens = None

        if not self._tokens:
            self._tokens = await oauth_login()

        self._rebuild_client()

    def _rebuild_client(self) -> None:
        """Create or recreate the OpenAI SDK client with current token."""
        from openai import OpenAI

        if not self._tokens:
            return
        self._client = OpenAI(
            api_key=self._tokens.access_token,
            base_url=CODEX_BASE_URL,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    async def _ensure_valid_token(self) -> None:
        """Refresh token if expired and rebuild client."""
        if not self._tokens:
            await self.ensure_authenticated()
            return
        if self._tokens.is_expired():
            self._tokens = await refresh_tokens(self._tokens)
            self._rebuild_client()

    @property
    def last_tool_calls(self) -> list[NativeToolCall]:
        return self._last_tool_calls

    # ------------------------------------------------------------------
    # Chat Completions -> Responses API message conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Chat Completions messages to Responses API flat array.

        The Responses API uses a flat list of typed items instead of the
        nested ``role / tool_calls`` structure used by Chat Completions.
        System messages are skipped here because they are extracted
        separately as ``instructions``.
        """
        items: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "user":
                if isinstance(content, str):
                    items.append(
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": content}],
                        }
                    )
                elif isinstance(content, list):
                    # Multimodal content parts
                    input_content: list[dict[str, Any]] = []
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                input_content.append(
                                    {
                                        "type": "input_text",
                                        "text": part.get("text", ""),
                                    }
                                )
                            elif part.get("type") == "image_url":
                                input_content.append(
                                    {
                                        "type": "input_image",
                                        "image_url": part["image_url"]["url"],
                                    }
                                )
                    items.append({"role": "user", "content": input_content})

            elif role == "assistant":
                # Text part (if any)
                if content:
                    text = content if isinstance(content, str) else str(content)
                    items.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    )

                # Tool calls become separate top-level function_call items
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "arguments": func.get("arguments", "{}"),
                        }
                    )

            elif role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg.get("tool_call_id", ""),
                        "output": content if isinstance(content, str) else str(content),
                    }
                )

            # Skip system messages (already extracted as instructions)

        return items

    # ------------------------------------------------------------------
    # Streaming (called by BaseLLMProvider.chat)
    # ------------------------------------------------------------------

    async def _stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[ToolSchema] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream response from Codex backend using OpenAI SDK."""
        self._last_tool_calls = []
        await self._ensure_valid_token()

        if not self._client:
            self._rebuild_client()

        # Extract system message as instructions
        instructions = ""
        input_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                instructions = msg.get("content", "")
            else:
                input_messages.append(msg)

        # Convert Chat Completions format to Responses API flat array
        api_input = self._to_responses_input(input_messages)

        # Build tools in Responses API format
        api_tools = None
        if tools:
            api_tools = []
            for t in tools:
                api_tools.append(
                    {
                        "type": "function",
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                )

        # Call SDK in a thread (SDK is sync, we're async)
        loop = asyncio.get_running_loop()

        # Validate: function_calls and function_call_outputs must be paired
        call_ids = {
            item["call_id"] for item in api_input if item.get("type") == "function_call"
        }
        output_ids = {
            item["call_id"]
            for item in api_input
            if item.get("type") == "function_call_output"
        }

        # Add missing outputs (call without result)
        for call_id in call_ids - output_ids:
            name = ""
            for item in api_input:
                if (
                    item.get("type") == "function_call"
                    and item.get("call_id") == call_id
                ):
                    name = item.get("name", "")
                    break
            api_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": f"[{name}] Execution pending.",
                }
            )
            logger.warning("Added missing function_call_output", call_id=call_id)

        # Remove orphan outputs (result without call)
        orphan_ids = output_ids - call_ids
        if orphan_ids:
            api_input = [
                item
                for item in api_input
                if not (
                    item.get("type") == "function_call_output"
                    and item.get("call_id") in orphan_ids
                )
            ]
            logger.warning(
                "Removed orphan function_call_outputs",
                orphan_count=len(orphan_ids),
            )

        logger.debug(
            "Codex API request",
            model=self.model,
            input_items=len(api_input),
            input_preview=_json.dumps(api_input, ensure_ascii=False)[:500],
        )

        # Build optional params
        extra_params: dict[str, Any] = {}
        if self.reasoning_effort and self.reasoning_effort != "none":
            extra_params["reasoning"] = {"effort": self.reasoning_effort}
        if self.service_tier:
            extra_params["service_tier"] = self.service_tier

        def _create_stream() -> Any:
            return self._client.responses.create(
                model=self.model,
                instructions=instructions or "You are a helpful assistant.",
                input=api_input,
                tools=api_tools,
                store=False,
                stream=True,
                **extra_params,
            )

        try:
            stream = await loop.run_in_executor(None, _create_stream)
        except Exception as e:
            logger.error("Codex API request failed", error=str(e))
            raise

        # Process events in a thread and push to queue
        text_queue: asyncio.Queue[str | None] = asyncio.Queue()
        collected_tool_calls: list[NativeToolCall] = []

        def _consume_stream() -> None:
            # Track tool call names from output_item events
            # (arguments.done has name=None, output_item.done has full info)
            pending_names: dict[str, str] = {}  # item_id -> name
            try:
                for event in stream:
                    match event.type:
                        case "response.output_text.delta":
                            text_queue.put_nowait(event.delta)
                        case "response.output_item.added":
                            item = event.item
                            if hasattr(item, "name") and item.name:
                                item_id = getattr(item, "id", "")
                                pending_names[item_id] = item.name
                        case "response.output_item.done":
                            item = event.item
                            if getattr(item, "type", "") == "function_call":
                                collected_tool_calls.append(
                                    NativeToolCall(
                                        id=getattr(item, "call_id", ""),
                                        name=getattr(item, "name", "") or "",
                                        arguments=getattr(item, "arguments", ""),
                                    )
                                )
                        case "response.completed":
                            # Extract usage from completed response
                            resp = getattr(event, "response", None)
                            if resp:
                                u = getattr(resp, "usage", None)
                                if u:
                                    text_queue.put_nowait(
                                        (
                                            "__usage__",
                                            {
                                                "prompt_tokens": getattr(
                                                    u, "input_tokens", 0
                                                ),
                                                "completion_tokens": getattr(
                                                    u, "output_tokens", 0
                                                ),
                                                "total_tokens": getattr(
                                                    u, "total_tokens", 0
                                                ),
                                            },
                                        )
                                    )
            except Exception as e:
                logger.error("Stream error", error=str(e))
            finally:
                text_queue.put_nowait(None)  # signal done

        consume_task = loop.run_in_executor(None, _consume_stream)

        # Yield text chunks as they arrive
        while True:
            chunk = await text_queue.get()
            if chunk is None:
                break
            # Handle usage tuple from response.completed
            if isinstance(chunk, tuple) and chunk[0] == "__usage__":
                self._last_usage = chunk[1]
                continue
            yield chunk

        await consume_task
        self._last_tool_calls = collected_tool_calls

    # ------------------------------------------------------------------
    # Non-streaming
    # ------------------------------------------------------------------

    async def _complete_chat(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> ChatResponse:
        """Non-streaming completion (collects streaming output)."""
        parts: list[str] = []
        async for chunk in self._stream_chat(messages, **kwargs):
            parts.append(chunk)
        return ChatResponse(
            content="".join(parts),
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            model=self.model,
        )

    async def close(self) -> None:
        """Cleanup."""
        self._client = None

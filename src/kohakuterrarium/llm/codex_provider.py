"""
Codex OAuth LLM provider - uses ChatGPT subscription for model access.

Routes requests through the Codex backend endpoint which bills against
the user's ChatGPT Plus/Pro subscription instead of API credits.

The endpoint accepts OpenAI Responses API format and returns SSE streams
with response.* event types. We also handle Chat Completions format as
a fallback since some endpoint configurations may return it.
"""

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from kohakuterrarium.llm.base import (
    BaseLLMProvider,
    ChatResponse,
    LLMConfig,
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

CODEX_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"


class CodexOAuthProvider(BaseLLMProvider):
    """
    LLM provider that uses a ChatGPT subscription via Codex OAuth.

    Authenticates via OAuth PKCE (opens browser on first use) and routes
    requests to the Codex backend endpoint. Usage is billed against the
    ChatGPT Plus/Pro subscription quota, not API credits.

    Usage:
        provider = CodexOAuthProvider(model="gpt-5.4")
        await provider.ensure_authenticated()

        async for chunk in provider.chat(messages, stream=True):
            print(chunk, end="")
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        *,
        timeout: float = 300.0,
        max_retries: int = 2,
        retry_delay: float = 2.0,
    ):
        super().__init__(LLMConfig(model=model))
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._tokens: CodexTokens | None = None
        self._client: httpx.AsyncClient | None = None

        logger.debug("CodexOAuthProvider initialized", model=model)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def ensure_authenticated(self) -> None:
        """
        Ensure valid OAuth tokens are available.

        Loads cached tokens from disk, refreshes if expired, or opens
        the browser for a fresh login if no tokens exist.
        """
        self._tokens = CodexTokens.load()

        if self._tokens and self._tokens.is_expired():
            try:
                self._tokens = await refresh_tokens(self._tokens)
            except Exception as e:
                logger.warning("Token refresh failed, will re-login", error=str(e))
                self._tokens = None

        if not self._tokens:
            self._tokens = await oauth_login()

    async def _ensure_valid_token(self) -> str:
        """Get a valid access token, refreshing or logging in as needed."""
        if not self._tokens:
            await self.ensure_authenticated()
        assert self._tokens is not None
        if self._tokens.is_expired():
            self._tokens = await refresh_tokens(self._tokens)
        return self._tokens.access_token

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=15.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _build_request_body(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[ToolSchema] | None = None,
    ) -> dict[str, Any]:
        """
        Build request body for the Codex backend.

        Uses standard Chat Completions format (messages, model, stream).
        The Codex backend accepts this format directly, same as OpenCode
        which sends standard OpenAI SDK requests and just rewrites the URL.
        """
        # Extract system message as "instructions" (required by Codex backend)
        instructions = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                instructions = msg.get("content", "")
            else:
                chat_messages.append(msg)

        body: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions or "You are a helpful assistant.",
            "input": chat_messages,
            "stream": True,
            "store": False,
        }
        if tools:
            body["tools"] = [t.to_api_format() for t in tools]
        return body

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def _stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[ToolSchema] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat response from the Codex backend with retry."""
        self._last_tool_calls = []
        pending_calls: dict[int, dict[str, str]] = {}

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Retrying Codex request",
                    attempt=attempt,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                pending_calls = {}

            token = await self._ensure_valid_token()
            client = await self._get_client()
            body = self._build_request_body(messages, tools=tools)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            try:
                async with client.stream(
                    "POST", CODEX_ENDPOINT, json=body, headers=headers
                ) as response:
                    if response.status_code == 401:
                        logger.warning("Token rejected (401), refreshing...")
                        assert self._tokens is not None
                        try:
                            self._tokens = await refresh_tokens(self._tokens)
                        except Exception:
                            self._tokens = None
                            await self.ensure_authenticated()
                        last_error = RuntimeError("Auth expired, retried")
                        continue

                    if response.status_code >= 500 or response.status_code == 429:
                        error_text = (await response.aread()).decode()
                        logger.error(
                            "Codex API error (retryable)",
                            status=response.status_code,
                            error=error_text,
                        )
                        last_error = httpx.HTTPStatusError(
                            f"Codex API: {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                        if attempt < self.max_retries:
                            continue
                        raise last_error

                    if response.status_code >= 400:
                        error_body = (await response.aread()).decode()
                        logger.error(
                            "Codex API error",
                            status=response.status_code,
                            body=error_body[:500],
                        )
                        response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # --- Responses API events ---
                        event_type = data.get("type", "")

                        if event_type == "response.output_text.delta":
                            text = data.get("delta", "")
                            if text:
                                yield text

                        if event_type == "response.function_call_arguments.done":
                            self._last_tool_calls.append(
                                NativeToolCall(
                                    id=data.get("call_id", ""),
                                    name=data.get("name", ""),
                                    arguments=data.get("arguments", ""),
                                )
                            )

                        # --- Chat Completions fallback ---
                        if "choices" in data:
                            for choice in data["choices"]:
                                delta = choice.get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                                if "tool_calls" in delta:
                                    self._accumulate_tool_calls(
                                        delta["tool_calls"], pending_calls
                                    )

                    # Stream finished successfully
                    self._finalize_tool_calls(pending_calls)
                    return

            except httpx.TimeoutException as e:
                logger.error(
                    "Codex request timed out",
                    timeout=self.timeout,
                    attempt=attempt,
                )
                last_error = e
                if attempt < self.max_retries:
                    continue
                raise
            except httpx.HTTPStatusError:
                raise
            except Exception as e:
                if (
                    isinstance(
                        e,
                        (
                            httpx.RemoteProtocolError,
                            httpx.ReadError,
                            httpx.ConnectError,
                        ),
                    )
                    and attempt < self.max_retries
                ):
                    logger.warning(
                        "Retryable network error", error=str(e), attempt=attempt
                    )
                    last_error = e
                    continue
                raise

        # All retries exhausted
        self._finalize_tool_calls(pending_calls)
        if last_error:
            raise last_error

    # ------------------------------------------------------------------
    # Tool call accumulation (Chat Completions format fallback)
    # ------------------------------------------------------------------

    def _accumulate_tool_calls(
        self,
        deltas: list[dict[str, Any]],
        pending: dict[int, dict[str, str]],
    ) -> None:
        """Accumulate incremental tool_call deltas from streaming chunks."""
        for tc in deltas:
            idx = tc.get("index", 0)
            if idx not in pending:
                pending[idx] = {"id": tc.get("id", ""), "name": "", "arguments": ""}
            if tc.get("id"):
                pending[idx]["id"] = tc["id"]
            fn = tc.get("function", {})
            if fn.get("name"):
                pending[idx]["name"] = fn["name"]
            if fn.get("arguments"):
                pending[idx]["arguments"] += fn["arguments"]

    def _finalize_tool_calls(self, pending: dict[int, dict[str, str]]) -> None:
        """Convert accumulated pending tool calls into NativeToolCall list."""
        for _, call in sorted(pending.items()):
            if call["name"]:
                self._last_tool_calls.append(
                    NativeToolCall(
                        id=call["id"],
                        name=call["name"],
                        arguments=call["arguments"],
                    )
                )
        if self._last_tool_calls:
            logger.debug(
                "Native tool calls received",
                count=len(self._last_tool_calls),
                tools=[tc.name for tc in self._last_tool_calls],
            )

    # ------------------------------------------------------------------
    # Non-streaming convenience
    # ------------------------------------------------------------------

    async def _complete_chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatResponse:
        """Non-streaming completion (collects full stream)."""
        parts: list[str] = []
        async for chunk in self._stream_chat(messages, **kwargs):
            parts.append(chunk)
        return ChatResponse(
            content="".join(parts),
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            model=self.model,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "CodexOAuthProvider":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

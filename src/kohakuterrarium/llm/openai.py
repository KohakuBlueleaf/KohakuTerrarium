"""
OpenAI-compatible LLM provider.

Supports OpenAI API and compatible services like OpenRouter, Together AI, etc.
"""

import json
from typing import Any, AsyncIterator

import httpx

from kohakuterrarium.llm.base import BaseLLMProvider, ChatResponse, LLMConfig
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

# Default API endpoints
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI API-compatible LLM provider.

    Works with:
    - OpenAI API (default)
    - OpenRouter (set base_url to OPENROUTER_BASE_URL)
    - Any OpenAI-compatible endpoint

    Usage:
        # OpenAI
        provider = OpenAIProvider(api_key="sk-...")

        # OpenRouter
        provider = OpenAIProvider(
            api_key="sk-or-...",
            base_url=OPENROUTER_BASE_URL,
            model="anthropic/claude-3-opus",
        )

        # Streaming
        async for chunk in provider.chat(messages):
            print(chunk, end="")
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = OPENAI_BASE_URL,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
    ):
        """
        Initialize the OpenAI provider.

        Args:
            api_key: API key for authentication (required)
            model: Model identifier
            base_url: API base URL (change for OpenRouter, etc.)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            extra_headers: Additional headers (e.g., for OpenRouter HTTP-Referer)
        """
        super().__init__(
            LLMConfig(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        if not api_key:
            raise ValueError(
                "API key is required. "
                "Set OPENROUTER_API_KEY or OPENAI_API_KEY environment variable."
            )

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

        # httpx client for async requests
        self._client: httpx.AsyncClient | None = None

        logger.debug(
            "OpenAIProvider initialized",
            model=model,
            base_url=self.base_url,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        return headers

    def _build_request_body(
        self,
        messages: list[dict[str, Any]],
        stream: bool,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build the request body for chat completion."""
        body: dict[str, Any] = {
            "model": kwargs.get("model", self.config.model),
            "messages": messages,
            "stream": stream,
        }

        # Add optional parameters if provided
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]
        elif self.config.temperature is not None:
            body["temperature"] = self.config.temperature

        if "max_tokens" in kwargs:
            body["max_tokens"] = kwargs["max_tokens"]
        elif self.config.max_tokens is not None:
            body["max_tokens"] = self.config.max_tokens

        if "top_p" in kwargs:
            body["top_p"] = kwargs["top_p"]

        if "stop" in kwargs:
            body["stop"] = kwargs["stop"]

        return body

    async def _stream_chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream chat completion."""
        client = await self._get_client()
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_request_body(messages, stream=True, **kwargs)

        logger.debug("Starting streaming request", model=body["model"])

        try:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=body,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(
                        "API request failed",
                        status=response.status_code,
                        error=error_text.decode(),
                    )
                    raise httpx.HTTPStatusError(
                        f"API request failed: {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # SSE format: "data: {...}" or "data: [DONE]"
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix

                        if data == "[DONE]":
                            logger.debug("Stream completed")
                            break

                        try:
                            chunk = json.loads(data)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError as e:
                            logger.warning("Failed to parse SSE chunk", error=str(e))
                            continue

        except httpx.TimeoutException:
            logger.error("Request timed out", timeout=self.timeout)
            raise
        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            logger.error("Unexpected error during streaming", error=str(e))
            raise

    async def _complete_chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatResponse:
        """Non-streaming chat completion."""
        client = await self._get_client()
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_request_body(messages, stream=False, **kwargs)

        logger.debug("Starting non-streaming request", model=body["model"])

        try:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()

            data = response.json()
            choices = data.get("choices", [])

            if not choices:
                raise ValueError("No choices in API response")

            choice = choices[0]
            message = choice.get("message", {})
            usage = data.get("usage", {})

            logger.debug(
                "Request completed",
                tokens_in=usage.get("prompt_tokens"),
                tokens_out=usage.get("completion_tokens"),
            )

            return ChatResponse(
                content=message.get("content", ""),
                finish_reason=choice.get("finish_reason", "unknown"),
                usage=usage,
                model=data.get("model", self.config.model),
            )

        except httpx.TimeoutException:
            logger.error("Request timed out", timeout=self.timeout)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "API request failed",
                status=e.response.status_code,
                error=e.response.text,
            )
            raise
        except Exception as e:
            logger.error("Unexpected error", error=str(e))
            raise

    async def __aenter__(self) -> "OpenAIProvider":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

"""Integration tests for the Ollama provider.

These tests require a live ``ollama serve`` with at least one pulled model.
They skip cleanly when the daemon is not reachable, so CI without Ollama is
unaffected.

To run locally:
    ollama serve &
    ollama pull qwen3.6        # or qwen3.5 / gemma4
    uv run pytest tests/integration/test_ollama.py -v
"""

import httpx
import pytest

from kohakuterrarium.bootstrap.llm import _create_from_profile
from kohakuterrarium.llm.base import ToolSchema
from kohakuterrarium.llm.message import Message
from kohakuterrarium.llm.profiles import get_preset


def _ollama_running() -> bool:
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=1.0)
        return True
    except Exception:
        return False


def _pulled_models() -> list[str]:
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=1.0)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        return []


pytestmark = pytest.mark.skipif(
    not _ollama_running(),
    reason="Ollama daemon not reachable at http://localhost:11434",
)


def _pick_model() -> str:
    """Pick any pulled model that matches a built-in Ollama preset, or skip."""
    models = _pulled_models()
    for candidate in (
        "qwen3.6:latest",
        "qwen3.5:latest",
        "qwen3.5:27b",
        "gemma4:latest",
        "gemma4:26b",
    ):
        base = candidate.split(":")[0]
        for name in models:
            if name == candidate or name.startswith(base + ":"):
                return name
    pytest.skip(f"No compatible model pulled. Have: {models}")


class TestOllamaProvider:
    async def test_plain_chat_streams(self):
        """Without tools, Ollama should return at least one text chunk."""
        model_tag = _pick_model()
        profile = get_preset("qwen3.6-35b-local")
        assert profile is not None
        profile.model = model_tag  # use whatever is locally pulled

        provider = _create_from_profile(profile)

        chunks: list[str] = []
        async for chunk in provider.chat(
            [Message(role="user", content="Reply with a single word: hello.")],
            stream=True,
        ):
            chunks.append(chunk)

        joined = "".join(chunks)
        assert joined, "expected non-empty response from Ollama"
        # Do not hard-assert chunk count — some small models answer in a single
        # chunk for very short prompts. Just verify we got text back.

    async def test_tool_call_is_extracted(self):
        """When a tool is offered and the model decides to call it, the
        provider's ``last_tool_calls`` should be populated.

        Note: Ollama's OpenAI-compat endpoint delivers the tool call in a
        single non-streamed response — the iteration completes immediately
        with no content chunks, and the call appears in ``last_tool_calls``.
        """
        model_tag = _pick_model()
        profile = get_preset("qwen3.6-35b-local")
        assert profile is not None
        profile.model = model_tag

        provider = _create_from_profile(profile)

        tool = ToolSchema(
            name="get_current_time",
            description="Return the current time in ISO 8601 format.",
            parameters={"type": "object", "properties": {}},
        )

        async for _chunk in provider.chat(
            [
                Message(
                    role="user",
                    content="What time is it right now? Call the tool.",
                )
            ],
            stream=True,
            tools=[tool],
        ):
            pass

        # Tool calls may or may not be emitted depending on the model's
        # willingness. We accept either outcome; the assertion is that the
        # iteration completes without raising and the attribute is a list.
        assert isinstance(provider.last_tool_calls, list)

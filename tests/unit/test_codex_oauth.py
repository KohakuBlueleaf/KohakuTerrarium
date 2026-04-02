"""
Tests for Codex OAuth authentication and provider.

These tests cover offline functionality only (no browser auth, no network).
"""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from kohakuterrarium.llm.codex_auth import (
    AUTH_URL,
    CLIENT_ID,
    CODEX_CLI_TOKEN_PATH,
    DEFAULT_TOKEN_PATH,
    CodexTokens,
    _build_auth_url,
    _generate_pkce,
)
from kohakuterrarium.llm.codex_provider import CODEX_BASE_URL, CodexOAuthProvider


# =========================================================================
# CodexTokens dataclass
# =========================================================================


class TestCodexTokens:
    """Tests for the CodexTokens dataclass."""

    def test_is_expired_true(self):
        tokens = CodexTokens(
            access_token="tok",
            refresh_token="ref",
            expires_at=time.time() - 100,
        )
        assert tokens.is_expired()

    def test_is_expired_within_buffer(self):
        # Expires in 30s, but 60s buffer makes it "expired"
        tokens = CodexTokens(
            access_token="tok",
            refresh_token="ref",
            expires_at=time.time() + 30,
        )
        assert tokens.is_expired()

    def test_is_expired_false(self):
        tokens = CodexTokens(
            access_token="tok",
            refresh_token="ref",
            expires_at=time.time() + 3600,
        )
        assert not tokens.is_expired()

    def test_is_expired_default(self):
        # Default expires_at=0 should be expired
        tokens = CodexTokens(access_token="tok", refresh_token="ref")
        assert tokens.is_expired()

    def test_save_and_load(self, tmp_path: Path):
        token_path = tmp_path / "tokens.json"
        original = CodexTokens(
            access_token="my-access-token",
            refresh_token="my-refresh-token",
            expires_at=1234567890.0,
        )
        original.save(token_path)

        # Verify file was written
        assert token_path.exists()
        data = json.loads(token_path.read_text())
        assert data["access_token"] == "my-access-token"
        assert data["refresh_token"] == "my-refresh-token"
        assert data["expires_at"] == 1234567890.0

        # Load it back
        loaded = CodexTokens.load(token_path)
        assert loaded is not None
        assert loaded.access_token == "my-access-token"
        assert loaded.refresh_token == "my-refresh-token"
        assert loaded.expires_at == 1234567890.0

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        token_path = tmp_path / "deep" / "nested" / "tokens.json"
        tokens = CodexTokens(access_token="tok", refresh_token="ref")
        tokens.save(token_path)
        assert token_path.exists()

    def test_load_nonexistent_returns_none(self, tmp_path: Path):
        result = CodexTokens.load(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_empty_access_token_returns_none(self, tmp_path: Path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(
            json.dumps(
                {
                    "access_token": "",
                    "refresh_token": "ref",
                }
            )
        )
        result = CodexTokens.load(token_path)
        assert result is None

    def test_load_malformed_json_returns_none(self, tmp_path: Path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text("not json at all")
        result = CodexTokens.load(token_path)
        assert result is None


# =========================================================================
# PKCE generation
# =========================================================================


class TestPKCE:
    """Tests for PKCE code generation."""

    def test_generate_pkce_returns_two_strings(self):
        verifier, challenge = _generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) > 32
        assert len(challenge) > 16

    def test_generate_pkce_unique(self):
        v1, c1 = _generate_pkce()
        v2, c2 = _generate_pkce()
        assert v1 != v2
        assert c1 != c2

    def test_build_auth_url(self):
        url = _build_auth_url("test-challenge", "test-state")
        assert url.startswith(AUTH_URL)
        assert "client_id=" + CLIENT_ID in url
        assert "redirect_uri=" in url  # URL-encoded
        assert "code_challenge=test-challenge" in url
        assert "state=test-state" in url
        assert "code_challenge_method=S256" in url
        assert "response_type=code" in url
        # Scope should be URL-encoded (no raw spaces)
        assert "scope=openid+email+profile" in url or "scope=openid%20email" in url


# =========================================================================
# CodexOAuthProvider
# =========================================================================


class TestCodexOAuthProvider:
    """Tests for the CodexOAuthProvider class."""

    def test_init_defaults(self):
        provider = CodexOAuthProvider()
        assert provider.model == "gpt-5.4"
        assert provider._tokens is None
        assert provider._client is None

    def test_init_custom_model(self):
        provider = CodexOAuthProvider(model="o3")
        assert provider.model == "o3"

    def test_last_tool_calls_default_empty(self):
        provider = CodexOAuthProvider()
        assert provider.last_tool_calls == []

    @pytest.mark.asyncio
    async def test_ensure_authenticated_uses_cached(self, tmp_path: Path):
        """If valid tokens exist on disk, no browser login needed."""
        token_path = tmp_path / "tokens.json"
        CodexTokens(
            access_token="cached-token",
            refresh_token="cached-refresh",
            expires_at=time.time() + 3600,
        ).save(token_path)

        provider = CodexOAuthProvider()
        with patch("kohakuterrarium.llm.codex_auth.DEFAULT_TOKEN_PATH", token_path):
            await provider.ensure_authenticated()

        assert provider._tokens is not None
        assert provider._tokens.access_token == "cached-token"

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        """Closing without ever making a request should not error."""
        provider = CodexOAuthProvider()
        await provider.close()  # Should not raise


# =========================================================================
# _to_responses_input conversion
# =========================================================================


class TestToResponsesInput:
    """Tests for Chat Completions -> Responses API message conversion."""

    def test_user_string_content(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert result == [
            {"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}
        ]

    def test_user_multimodal_content(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/img.png"},
                    },
                ],
            }
        ]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        parts = result[0]["content"]
        assert parts[0] == {"type": "input_text", "text": "What is this?"}
        assert parts[1] == {
            "type": "input_image",
            "image_url": "https://example.com/img.png",
        }

    def test_assistant_text_only(self):
        messages = [{"role": "assistant", "content": "I'll help you"}]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert result == [
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I'll help you"}],
            }
        ]

    def test_assistant_with_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "ls"}',
                        },
                    }
                ],
            }
        ]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert len(result) == 2
        assert result[0] == {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Let me check."}],
        }
        assert result[1] == {
            "type": "function_call",
            "call_id": "call_abc",
            "name": "bash",
            "arguments": '{"command": "ls"}',
        }

    def test_assistant_tool_calls_no_content(self):
        """Assistant with tool calls but no text content."""
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "read", "arguments": '{"path": "/a"}'},
                    },
                    {
                        "id": "call_2",
                        "function": {"name": "read", "arguments": '{"path": "/b"}'},
                    },
                ],
            }
        ]
        result = CodexOAuthProvider._to_responses_input(messages)
        # No text item, just two function_call items
        assert len(result) == 2
        assert result[0]["type"] == "function_call"
        assert result[0]["call_id"] == "call_1"
        assert result[1]["type"] == "function_call"
        assert result[1]["call_id"] == "call_2"

    def test_tool_result(self):
        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_abc",
                "content": "file1.txt\nfile2.txt",
            }
        ]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert result == [
            {
                "type": "function_call_output",
                "call_id": "call_abc",
                "output": "file1.txt\nfile2.txt",
            }
        ]

    def test_system_messages_skipped(self):
        messages = [{"role": "system", "content": "You are helpful."}]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert result == []

    def test_full_conversation(self):
        """Multi-turn conversation with tool use round-trip."""
        messages = [
            {"role": "user", "content": "List files"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "bash", "arguments": '{"command":"ls"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "a.py\nb.py"},
            {"role": "assistant", "content": "Found a.py and b.py."},
            {"role": "user", "content": "Read a.py"},
        ]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert len(result) == 5
        assert result[0]["role"] == "user"
        assert result[1]["type"] == "function_call"
        assert result[2]["type"] == "function_call_output"
        assert result[3]["role"] == "assistant"
        assert result[4]["role"] == "user"

    def test_empty_messages(self):
        result = CodexOAuthProvider._to_responses_input([])
        assert result == []

    def test_unknown_role_skipped(self):
        """Messages with unknown roles are silently ignored."""
        messages = [{"role": "unknown", "content": "???"}]
        result = CodexOAuthProvider._to_responses_input(messages)
        assert result == []


class TestConstants:
    """Verify critical constants are correct."""

    def test_codex_endpoint(self):
        assert CODEX_BASE_URL == "https://chatgpt.com/backend-api/codex"

    def test_default_token_path(self):
        assert (
            DEFAULT_TOKEN_PATH == Path.home() / ".kohakuterrarium" / "codex-auth.json"
        )

    def test_codex_cli_token_path(self):
        assert CODEX_CLI_TOKEN_PATH == Path.home() / ".codex" / "auth.json"

    def test_client_id(self):
        assert CLIENT_ID == "app_EMoamEEZ73f0CkXaXp7hrann"

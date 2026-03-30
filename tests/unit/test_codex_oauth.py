"""
Tests for Codex OAuth authentication and provider.

These tests cover offline functionality only (no browser auth, no network).
"""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from kohakuterrarium.llm.codex_auth import (
    AUTH_URL,
    CLIENT_ID,
    CODEX_CLI_TOKEN_PATH,
    DEFAULT_TOKEN_PATH,
    REDIRECT_URI,
    CodexTokens,
    _build_auth_url,
    _generate_pkce,
)
from kohakuterrarium.llm.codex_provider import CODEX_ENDPOINT, CodexOAuthProvider


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
        assert "redirect_uri=" + REDIRECT_URI in url
        assert "code_challenge=test-challenge" in url
        assert "state=test-state" in url
        assert "code_challenge_method=S256" in url
        assert "response_type=code" in url


# =========================================================================
# CodexOAuthProvider
# =========================================================================


class TestCodexOAuthProvider:
    """Tests for the CodexOAuthProvider class."""

    def test_init_defaults(self):
        provider = CodexOAuthProvider()
        assert provider.model == "gpt-4o"
        assert provider._tokens is None
        assert provider._client is None

    def test_init_custom_model(self):
        provider = CodexOAuthProvider(model="o3")
        assert provider.model == "o3"

    def test_build_request_body_basic(self):
        provider = CodexOAuthProvider(model="gpt-4o")
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        body = provider._build_request_body(messages)

        assert body["model"] == "gpt-4o"
        assert body["input"] == messages
        assert body["stream"] is True
        assert "tools" not in body

    def test_build_request_body_with_tools(self):
        from kohakuterrarium.llm.base import ToolSchema

        provider = CodexOAuthProvider()
        tools = [
            ToolSchema(
                name="bash",
                description="Execute a shell command",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                    "required": ["command"],
                },
            )
        ]
        messages = [{"role": "user", "content": "run ls"}]
        body = provider._build_request_body(messages, tools=tools)

        assert "tools" in body
        assert len(body["tools"]) == 1
        tool = body["tools"][0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "bash"
        assert tool["function"]["description"] == "Execute a shell command"

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

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Provider works as an async context manager."""
        async with CodexOAuthProvider() as provider:
            assert isinstance(provider, CodexOAuthProvider)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify critical constants are correct."""

    def test_codex_endpoint(self):
        assert CODEX_ENDPOINT == "https://chatgpt.com/backend-api/codex/responses"

    def test_default_token_path(self):
        assert (
            DEFAULT_TOKEN_PATH == Path.home() / ".kohakuterrarium" / "codex-auth.json"
        )

    def test_codex_cli_token_path(self):
        assert CODEX_CLI_TOKEN_PATH == Path.home() / ".codex" / "auth.json"

    def test_client_id(self):
        assert CLIENT_ID == "app_EMoamEEZ73f0CkXaXp7hrann"

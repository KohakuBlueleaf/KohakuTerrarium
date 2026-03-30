"""
Codex OAuth PKCE authentication for ChatGPT subscription access.

Implements the OAuth 2.0 + PKCE flow used by Codex CLI to authenticate
with a ChatGPT subscription. Tokens are cached locally and refreshed
automatically.

Token search order:
  1. ~/.kohakuterrarium/codex-auth.json  (our own cache)
  2. ~/.codex/auth.json                  (Codex CLI cache)
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REDIRECT_PORT = 1455
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}"
SCOPE = "openid email profile"
AUDIENCE = "https://api.openai.com/v1"

DEFAULT_TOKEN_PATH = Path.home() / ".kohakuterrarium" / "codex-auth.json"
CODEX_CLI_TOKEN_PATH = Path.home() / ".codex" / "auth.json"


@dataclass
class CodexTokens:
    """OAuth token set for Codex backend access."""

    access_token: str
    refresh_token: str
    expires_at: float = 0.0  # Unix timestamp

    def is_expired(self) -> bool:
        """Check if the access token is expired (with 60s safety buffer)."""
        return time.time() >= self.expires_at - 60

    def save(self, path: Path | None = None) -> None:
        """Persist tokens to disk."""
        p = path or DEFAULT_TOKEN_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.expires_at,
                }
            )
        )
        logger.debug("Tokens saved", path=str(p))

    @classmethod
    def load(cls, path: Path | None = None) -> "CodexTokens | None":
        """
        Load tokens from disk.

        Tries our path first, then the Codex CLI path as fallback.
        Returns None if no valid tokens found.
        """
        candidates = [path or DEFAULT_TOKEN_PATH, CODEX_CLI_TOKEN_PATH]
        for p in candidates:
            if p and p.exists():
                try:
                    data = json.loads(p.read_text())
                    tokens = cls(
                        access_token=data.get("access_token", ""),
                        refresh_token=data.get("refresh_token", ""),
                        expires_at=data.get("expires_at", 0),
                    )
                    if tokens.access_token:
                        logger.info("Tokens loaded", path=str(p))
                        return tokens
                except Exception as e:
                    logger.warning("Failed to load tokens", path=str(p), error=str(e))
        return None


def _build_auth_url(code_challenge: str, state: str) -> str:
    """Construct the OAuth authorization URL with PKCE parameters."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "audience": AUDIENCE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def _generate_pkce() -> tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge.

    Returns:
        (code_verifier, code_challenge_b64)
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP handler that captures the OAuth callback.

    Stores the authorization code and state on the server instance
    so the caller can retrieve them after the request completes.
    """

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        server: Any = self.server
        server.auth_code = qs.get("code", [None])[0]
        server.callback_state = qs.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body>"
            b"<h2>Authentication successful!</h2>"
            b"<p>You can close this tab.</p>"
            b"</body></html>"
        )

    # Suppress default request logging
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


async def oauth_login() -> CodexTokens:
    """
    Run the full OAuth PKCE flow via browser.

    1. Start a local HTTP server on REDIRECT_PORT
    2. Open the authorization URL in the default browser
    3. Wait for the callback with the authorization code
    4. Exchange the code for tokens
    5. Save and return the tokens

    Raises:
        RuntimeError: If the login times out or state mismatches.
    """
    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    auth_url = _build_auth_url(code_challenge, state)

    # Run stdlib HTTPServer in a background thread
    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _OAuthCallbackHandler)
    server.auth_code = None  # type: ignore[attr-defined]
    server.callback_state = None  # type: ignore[attr-defined]
    server.timeout = 120  # per-request timeout

    received = asyncio.Event()

    def _serve_once() -> None:
        server.handle_request()  # blocks until one request arrives
        received._loop.call_soon_threadsafe(received.set)  # type: ignore[attr-defined]

    loop = asyncio.get_running_loop()
    received._loop = loop  # type: ignore[attr-defined]

    thread = Thread(target=_serve_once, daemon=True)
    thread.start()

    logger.info("Opening browser for authentication...")
    print("Opening browser for OpenAI authentication...")
    print()
    print("If the browser didn't open, visit this URL manually:")
    print(auth_url)
    print()
    print(f"Waiting for callback on http://127.0.0.1:{REDIRECT_PORT} ...")
    webbrowser.open(auth_url)

    try:
        await asyncio.wait_for(received.wait(), timeout=120)
    except asyncio.TimeoutError:
        server.server_close()
        raise RuntimeError("OAuth login timed out (120s)")
    finally:
        server.server_close()

    auth_code: str | None = server.auth_code  # type: ignore[attr-defined]
    callback_state: str | None = server.callback_state  # type: ignore[attr-defined]

    if callback_state != state:
        raise RuntimeError("OAuth state mismatch - possible CSRF attack")
    if not auth_code:
        raise RuntimeError("No authorization code received")

    # Exchange authorization code for tokens
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            json={
                "client_id": CLIENT_ID,
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    tokens = CodexTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_at=time.time() + data.get("expires_in", 3600),
    )
    tokens.save()
    logger.info("OAuth login successful")
    return tokens


async def refresh_tokens(tokens: CodexTokens) -> CodexTokens:
    """
    Refresh an expired access token using the refresh token.

    Args:
        tokens: Current token set with a valid refresh_token.

    Returns:
        New CodexTokens with a fresh access_token.
    """
    if not tokens.refresh_token:
        raise RuntimeError("No refresh token available - please re-authenticate")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            json={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    new_tokens = CodexTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", tokens.refresh_token),
        expires_at=time.time() + data.get("expires_in", 3600),
    )
    new_tokens.save()
    logger.info("Tokens refreshed")
    return new_tokens

"""Authentication CLI."""

import asyncio

import httpx

from kohakuterrarium.llm.codex_auth import CodexTokens, oauth_login
from kohakuterrarium.llm.profiles import get_api_key, load_backends, save_api_key


def login_cli(provider: str) -> int:
    """Authenticate with a built-in or custom provider profile."""
    backends = load_backends()
    backend = backends.get(provider)
    if backend is None:
        print(f"Unknown provider: {provider}")
        return 1
    if backend.backend_type == "codex":
        return _login_codex()
    if provider == "ollama":
        return _login_ollama(backend.base_url)
    return _login_api_key(provider, backend.api_key_env)


def _login_api_key(provider: str, env_var: str) -> int:
    existing = get_api_key(provider)
    if existing:
        masked = f"{existing[:4]}...{existing[-4:]}" if len(existing) > 8 else "****"
        print(f"Existing {provider} key: {masked}")
        answer = input("Replace? [y/N]: ").strip().lower()
        if answer != "y":
            return 0

    print(f"Enter token/API key for provider '{provider}'")
    if env_var:
        print(f"Environment fallback: {env_var}")
    print()

    try:
        key = input("API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled")
        return 0

    if not key:
        print("No key provided")
        return 1

    save_api_key(provider, key)
    print(f"\nSaved provider token for: {provider}")
    print("You can now use presets bound to this provider:")
    print("  kt model list")
    print("  kt run @kt-biome/creatures/swe --llm <model>")
    return 0


def _login_ollama(base_url: str) -> int:
    """Verify Ollama daemon connectivity and list locally-pulled models.

    Ollama does not require authentication; this command only sanity-checks
    that the daemon is reachable and prints available models so the user knows
    what to pass as ``--llm``.
    """
    tags_url = base_url.rstrip("/").removesuffix("/v1") + "/api/tags"
    print(f"Checking Ollama at {base_url} ...")
    try:
        response = httpx.get(tags_url, timeout=3.0)
        response.raise_for_status()
    except httpx.ConnectError:
        print("Cannot reach Ollama.")
        print("  1. Install:         https://ollama.com/download")
        print("  2. Start daemon:    ollama serve")
        print("  3. Pull a model:    ollama pull gemma4:latest")
        return 1
    except httpx.HTTPError as exc:
        print(f"Ollama responded with an error: {exc}")
        return 1

    data = response.json()
    models = data.get("models", [])
    if not models:
        print("Ollama is running, but no models are pulled.")
        print("  Run: ollama pull gemma4:latest")
        return 0

    print(f"Ollama is reachable. {len(models)} local model(s):")
    for entry in models:
        name = entry.get("name", "?")
        size_gb = entry.get("size", 0) / (1024**3)
        print(f"  {name:<40} {size_gb:.1f} GB")
    print()
    print(
        "Built-in presets: qwen3.6-35b-local, qwen3.5-27b-local, "
        "qwen3.5-9b-local, gemma4-e4b-local, gemma4-26b-local"
    )
    print("Aliases: ollama, qwen-local, gemma-local")
    print("Run:  kt model list")
    return 0


def _login_codex() -> int:
    existing = CodexTokens.load()
    if existing and not existing.is_expired():
        print("Already authenticated (tokens valid).")
        print(
            f"Token path: {existing._path if hasattr(existing, '_path') else '~/.kohakuterrarium/codex-auth.json'}"
        )
        answer = input("Re-authenticate? [y/N]: ").strip().lower()
        if answer != "y":
            return 0

    print("Authenticating with OpenAI (ChatGPT subscription)...")
    print()
    try:
        asyncio.run(oauth_login())
        print()
        print("Authentication successful!")
        print("Tokens saved to: ~/.kohakuterrarium/codex-auth.json")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

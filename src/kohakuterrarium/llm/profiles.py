"""
LLM profile system: centralized model configuration.

Profiles define complete LLM settings (provider, model, context limits,
extra params). Stored in ~/.kohakuterrarium/llm_profiles.yaml.

Resolution order for an agent's LLM:
  1. controller.llm (profile name) in agent config
  2. default_model in ~/.kohakuterrarium/llm_profiles.yaml
  3. Inline controller config (backward compat)
  4. Built-in presets by model name

Built-in presets include model-specific metadata (context size, output
limits, required extra_body params) that can't be obtained from APIs.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

KT_DIR = Path.home() / ".kohakuterrarium"
PROFILES_PATH = KT_DIR / "llm_profiles.yaml"
KEYS_PATH = KT_DIR / "api_keys.yaml"

# ── Built-in Presets ──────────────────────────────────────────
# Model-specific metadata that can't be obtained from APIs.
# Keys are model names (or aliases). Users reference these by name.

PRESETS: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════
    #  OpenAI via Codex OAuth (ChatGPT subscription auth)
    # ═══════════════════════════════════════════════════════
    "gpt-5.4": {
        "provider": "codex-oauth",
        "model": "gpt-5.4",
        "max_context": 1050000,
    },
    "gpt-5.3-codex": {
        "provider": "codex-oauth",
        "model": "gpt-5.3-codex",
        "max_context": 400000,
    },
    "gpt-5.1": {
        "provider": "codex-oauth",
        "model": "gpt-5.1",
        "max_context": 400000,
    },
    "gpt-4o": {
        "provider": "codex-oauth",
        "model": "gpt-4o",
        "max_context": 128000,
    },
    "gpt-4o-mini": {
        "provider": "codex-oauth",
        "model": "gpt-4o-mini",
        "max_context": 128000,
    },
    # ═══════════════════════════════════════════════════════
    #  OpenAI Direct API (api key auth)
    #  reasoning_effort: none | low | medium | high | xhigh
    # ═══════════════════════════════════════════════════════
    "gpt-5.4-direct": {
        "provider": "openai",
        "model": "gpt-5.4",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 1050000,
    },
    "gpt-5.4-mini-direct": {
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 400000,
    },
    "gpt-5.4-nano-direct": {
        "provider": "openai",
        "model": "gpt-5.4-nano",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 400000,
    },
    "gpt-5.3-codex-direct": {
        "provider": "openai",
        "model": "gpt-5.3-codex",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 400000,
    },
    "gpt-5.1-direct": {
        "provider": "openai",
        "model": "gpt-5.1",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 400000,
    },
    "gpt-4o-direct": {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 128000,
    },
    "gpt-4o-mini-direct": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "max_context": 128000,
    },
    # ═══════════════════════════════════════════════════════
    #  OpenAI via OpenRouter
    # ═══════════════════════════════════════════════════════
    "or-gpt-5.4": {
        "provider": "openai",
        "model": "openai/gpt-5.4",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1050000,
    },
    "or-gpt-5.4-mini": {
        "provider": "openai",
        "model": "openai/gpt-5.4-mini",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 400000,
    },
    "or-gpt-5.4-nano": {
        "provider": "openai",
        "model": "openai/gpt-5.4-nano",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 400000,
    },
    "or-gpt-5.3-codex": {
        "provider": "openai",
        "model": "openai/gpt-5.3-codex",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 400000,
    },
    "or-gpt-5.1": {
        "provider": "openai",
        "model": "openai/gpt-5.1",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 400000,
    },
    "or-gpt-4o": {
        "provider": "openai",
        "model": "openai/gpt-4o",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 128000,
    },
    "or-gpt-4o-mini": {
        "provider": "openai",
        "model": "openai/gpt-4o-mini",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 128000,
    },
    # ═══════════════════════════════════════════════════════
    #  Anthropic Claude via OpenRouter (OpenAI-compat API)
    # ═══════════════════════════════════════════════════════
    "claude-opus-4.6": {
        "provider": "openai",
        "model": "anthropic/claude-opus-4.6",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1000000,
    },
    "claude-sonnet-4.6": {
        "provider": "openai",
        "model": "anthropic/claude-sonnet-4.6",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1000000,
    },
    "claude-sonnet-4.5": {
        "provider": "openai",
        "model": "anthropic/claude-sonnet-4.5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1000000,
    },
    "claude-haiku-4.5": {
        "provider": "openai",
        "model": "anthropic/claude-haiku-4.5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 200000,
    },
    # Legacy aliases kept for backward compat
    "claude-sonnet-4": {
        "provider": "openai",
        "model": "anthropic/claude-sonnet-4",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 200000,
    },
    "claude-opus-4": {
        "provider": "openai",
        "model": "anthropic/claude-opus-4",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 200000,
    },
    # ═══════════════════════════════════════════════════════
    #  Anthropic Claude Direct API (non-OpenAI format)
    #  NOTE: provider="anthropic" requires dedicated client,
    #  not the OpenAI-compat provider. Adaptive thinking is
    #  the recommended mode for 4.6 models:
    #    thinking: {type: "adaptive"}, effort: low|medium|high|max
    #  Fast mode (Opus 4.6 only):
    #    speed="fast", betas=["fast-mode-2026-02-01"]
    # ═══════════════════════════════════════════════════════
    "claude-opus-4.6-direct": {
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_context": 1000000,
    },
    "claude-sonnet-4.6-direct": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_context": 1000000,
    },
    "claude-haiku-4.5-direct": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_context": 200000,
    },
    # ═══════════════════════════════════════════════════════
    #  Google Gemini via OpenRouter
    # ═══════════════════════════════════════════════════════
    "gemini-3.1-pro": {
        "provider": "openai",
        "model": "google/gemini-3.1-pro-preview",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1048576,
    },
    "gemini-3-flash": {
        "provider": "openai",
        "model": "google/gemini-3-flash-preview",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1048576,
    },
    "gemini-3.1-flash-lite": {
        "provider": "openai",
        "model": "google/gemini-3.1-flash-lite-preview",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1048576,
    },
    "nano-banana": {
        "provider": "openai",
        "model": "google/gemini-3.1-flash-image-preview",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 65536,
    },
    # ═══════════════════════════════════════════════════════
    #  Google Gemini Direct API (OpenAI-compat endpoint)
    # ═══════════════════════════════════════════════════════
    "gemini-3.1-pro-direct": {
        "provider": "openai",
        "model": "gemini-3.1-pro-preview",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "max_context": 1048576,
    },
    "gemini-3-flash-direct": {
        "provider": "openai",
        "model": "gemini-3-flash-preview",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "max_context": 1048576,
    },
    "gemini-3.1-flash-lite-direct": {
        "provider": "openai",
        "model": "gemini-3.1-flash-lite-preview",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "max_context": 1048576,
    },
    # ═══════════════════════════════════════════════════════
    #  Gemma 4 (open models, via OpenRouter)
    # ═══════════════════════════════════════════════════════
    "gemma-4-31b": {
        "provider": "openai",
        "model": "google/gemma-4-31b-it",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
    },
    "gemma-4-26b": {
        "provider": "openai",
        "model": "google/gemma-4-26b-a4b-it",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
    },
    # ═══════════════════════════════════════════════════════
    #  Qwen 3.5 / 3.6 series (via OpenRouter)
    # ═══════════════════════════════════════════════════════
    "qwen3.5-plus": {
        "provider": "openai",
        "model": "qwen/qwen3.5-plus-02-15",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1000000,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    "qwen3.5-flash": {
        "provider": "openai",
        "model": "qwen/qwen3.5-flash-02-23",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1000000,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    "qwen3.5-397b": {
        "provider": "openai",
        "model": "qwen/qwen3.5-397b-a17b",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    "qwen3.5-27b": {
        "provider": "openai",
        "model": "qwen/qwen3.5-27b",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    "qwen3-coder": {
        "provider": "openai",
        "model": "qwen/qwen3-coder",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
    },
    "qwen3-coder-plus": {
        "provider": "openai",
        "model": "qwen/qwen3-coder-plus",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1000000,
    },
    # ═══════════════════════════════════════════════════════
    #  Moonshot Kimi K2.5 / K2 (via OpenRouter)
    #  K2.5 has built-in thinking (enabled by default).
    #  Disable via reasoning param if needed.
    # ═══════════════════════════════════════════════════════
    "kimi-k2.5": {
        "provider": "openai",
        "model": "moonshotai/kimi-k2.5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
    },
    "kimi-k2-thinking": {
        "provider": "openai",
        "model": "moonshotai/kimi-k2-thinking",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 131072,
    },
    # ═══════════════════════════════════════════════════════
    #  MiniMax (via OpenRouter)
    # ═══════════════════════════════════════════════════════
    "minimax-m2.7": {
        "provider": "openai",
        "model": "minimax/minimax-m2.7",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 204800,
    },
    "minimax-m2.5": {
        "provider": "openai",
        "model": "minimax/minimax-m2.5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 197000,
    },
    # ═══════════════════════════════════════════════════════
    #  Xiaomi MiMo (via OpenRouter)
    # ═══════════════════════════════════════════════════════
    "mimo-v2-pro": {
        "provider": "openai",
        "model": "xiaomi/mimo-v2-pro",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 1048576,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    "mimo-v2-flash": {
        "provider": "openai",
        "model": "xiaomi/mimo-v2-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 262144,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    # ═══════════════════════════════════════════════════════
    #  Xiaomi MiMo Direct API (kt login mimo)
    # ═══════════════════════════════════════════════════════
    "mimo-v2-pro-direct": {
        "provider": "openai",
        "model": "MiMo-V2-Pro",
        "base_url": "https://api.xiaomimimo.com/v1",
        "api_key_env": "MIMO_API_KEY",
        "max_context": 1048576,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    "mimo-v2-flash-direct": {
        "provider": "openai",
        "model": "MiMo-V2-Flash",
        "base_url": "https://api.xiaomimimo.com/v1",
        "api_key_env": "MIMO_API_KEY",
        "max_context": 262144,
        "extra_body": {"reasoning": {"enabled": True}},
    },
    # ═══════════════════════════════════════════════════════
    #  GLM (Z.ai, via OpenRouter)
    # ═══════════════════════════════════════════════════════
    "glm-5": {
        "provider": "openai",
        "model": "z-ai/glm-5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 80000,
    },
    "glm-5-turbo": {
        "provider": "openai",
        "model": "z-ai/glm-5-turbo",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_context": 202752,
    },
}

# Aliases: short names -> canonical preset names
ALIASES: dict[str, str] = {
    # OpenAI
    "gpt5": "gpt-5.4",
    "gpt54": "gpt-5.4",
    "gpt53": "gpt-5.3-codex",
    "gpt4o": "gpt-4o",
    # Gemini
    "gemini": "gemini-3.1-pro",
    "gemini-pro": "gemini-3.1-pro",
    "gemini-flash": "gemini-3-flash",
    "gemini-lite": "gemini-3.1-flash-lite",
    # Claude (via OpenRouter)
    "claude": "claude-sonnet-4.6",
    "claude-sonnet": "claude-sonnet-4.6",
    "claude-opus": "claude-opus-4.6",
    "claude-haiku": "claude-haiku-4.5",
    "sonnet": "claude-sonnet-4.6",
    "opus": "claude-opus-4.6",
    "haiku": "claude-haiku-4.5",
    # Gemma
    "gemma": "gemma-4-31b",
    "gemma-4": "gemma-4-31b",
    # Qwen
    "qwen": "qwen3.5-plus",
    "qwen-coder": "qwen3-coder",
    # Kimi
    "kimi": "kimi-k2.5",
    # MiniMax
    "minimax": "minimax-m2.7",
    # MiMo
    "mimo": "mimo-v2-pro",
    # GLM
    "glm": "glm-5-turbo",
}

# ── Profile dataclass ─────────────────────────────────────────


@dataclass
class LLMProfile:
    """A complete LLM configuration."""

    name: str
    provider: str  # "codex-oauth" | "openai"
    model: str
    max_context: int = 256000
    max_output: int = 65536
    base_url: str = ""
    api_key_env: str = ""
    temperature: float | None = None
    reasoning_effort: str = ""
    service_tier: str = ""
    extra_body: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "max_context": self.max_context,
            "max_output": self.max_output,
        }
        if self.base_url:
            d["base_url"] = self.base_url
        if self.api_key_env:
            d["api_key_env"] = self.api_key_env
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.reasoning_effort:
            d["reasoning_effort"] = self.reasoning_effort
        if self.service_tier:
            d["service_tier"] = self.service_tier
        if self.extra_body:
            d["extra_body"] = self.extra_body
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "LLMProfile":
        return cls(
            name=name,
            provider=data.get("provider", "openai"),
            model=data.get("model", ""),
            max_context=data.get("max_context", 256000),
            max_output=data.get("max_output", 65536),
            base_url=data.get("base_url", ""),
            api_key_env=data.get("api_key_env", ""),
            temperature=data.get("temperature"),
            reasoning_effort=data.get("reasoning_effort", ""),
            service_tier=data.get("service_tier", ""),
            extra_body=data.get("extra_body", {}),
        )


# ── Profile storage ───────────────────────────────────────────


def _load_yaml() -> dict[str, Any]:
    """Load the profiles YAML file."""
    if not PROFILES_PATH.exists():
        return {}
    try:
        with open(PROFILES_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load LLM profiles", error=str(e))
        return {}


def _save_yaml(data: dict[str, Any]) -> None:
    """Save the profiles YAML file."""
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILES_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_profiles() -> dict[str, LLMProfile]:
    """Load all user-defined profiles."""
    data = _load_yaml()
    profiles = {}
    for name, pdata in data.get("profiles", {}).items():
        if isinstance(pdata, dict):
            profiles[name] = LLMProfile.from_dict(name, pdata)
    return profiles


def get_default_model() -> str:
    """Get the default model name from user config."""
    data = _load_yaml()
    return data.get("default_model", "")


def set_default_model(model_name: str) -> None:
    """Set the default model name."""
    data = _load_yaml()
    data["default_model"] = model_name
    _save_yaml(data)
    logger.info("Default model set", model=model_name)


def save_profile(profile: LLMProfile) -> None:
    """Save a user-defined profile."""
    data = _load_yaml()
    if "profiles" not in data:
        data["profiles"] = {}
    data["profiles"][profile.name] = profile.to_dict()
    _save_yaml(data)
    logger.info("Profile saved", profile=profile.name)


def delete_profile(name: str) -> bool:
    """Delete a user-defined profile. Returns True if found."""
    data = _load_yaml()
    profiles = data.get("profiles", {})
    if name in profiles:
        del profiles[name]
        _save_yaml(data)
        return True
    return False


# ── Profile resolution ────────────────────────────────────────


def get_profile(name: str) -> LLMProfile | None:
    """Look up a profile by name.

    Resolution: user profiles -> aliases -> presets.
    """
    # Resolve alias
    canonical = ALIASES.get(name, name)

    # User profiles first
    profiles = load_profiles()
    if canonical in profiles:
        return profiles[canonical]

    # Built-in presets
    if canonical in PRESETS:
        return LLMProfile.from_dict(canonical, PRESETS[canonical])

    # Try original name in presets (in case alias didn't match)
    if name in PRESETS:
        return LLMProfile.from_dict(name, PRESETS[name])

    return None


def get_preset(name: str) -> LLMProfile | None:
    """Look up a built-in preset only (not user profiles)."""
    canonical = ALIASES.get(name, name)
    if canonical in PRESETS:
        return LLMProfile.from_dict(canonical, PRESETS[canonical])
    return None


def resolve_controller_llm(
    controller_config: dict[str, Any],
    llm_override: str | None = None,
) -> LLMProfile | None:
    """Resolve the LLM profile for a controller config.

    Resolution order:
      1. llm_override (from --llm CLI flag)
      2. controller_config["llm"] (profile name in agent config)
      3. default_model from ~/.kohakuterrarium/llm_profiles.yaml
         (only if agent has no explicit inline model)
      4. None (fall back to inline controller config, backward compat)

    Returns None if no profile found (caller should use inline config).
    """
    # 1. CLI override
    name = llm_override

    # 2. Config reference
    if not name:
        name = controller_config.get("llm")

    # 3. Default model (only when agent didn't set an explicit inline model)
    if not name:
        inline_model = controller_config.get("model", "")
        default_model = "openai/gpt-4o-mini"
        has_explicit_model = inline_model and inline_model != default_model
        if not has_explicit_model:
            name = get_default_model()

    if not name:
        return None

    profile = get_profile(name)
    if not profile:
        logger.warning("LLM profile not found", profile_name=name)
        return None

    # Merge inline overrides from controller config
    overrides = {}
    for key in ("temperature", "reasoning_effort", "service_tier", "max_tokens"):
        if key in controller_config and key != "llm":
            if key == "max_tokens":
                overrides["max_output"] = controller_config[key]
            else:
                overrides[key] = controller_config[key]

    if overrides:
        for k, v in overrides.items():
            if hasattr(profile, k) and v is not None:
                setattr(profile, k, v)

    return profile


def _login_provider_for(profile_or_data: dict[str, Any] | LLMProfile) -> str:
    """Determine which ``kt login <provider>`` gives access to this model.

    Returns the login provider name (codex, openrouter, openai, anthropic,
    gemini, mimo) or empty string if unknown.
    """
    if isinstance(profile_or_data, LLMProfile):
        provider = profile_or_data.provider
        api_key_env = profile_or_data.api_key_env
    else:
        provider = profile_or_data.get("provider", "")
        api_key_env = profile_or_data.get("api_key_env", "")

    if provider == "codex-oauth":
        return "codex"

    # Reverse lookup: env var → login provider
    _ENV_TO_LOGIN = {v: k for k, v in PROVIDER_KEY_MAP.items()}
    if api_key_env in _ENV_TO_LOGIN:
        return _ENV_TO_LOGIN[api_key_env]

    return provider


def _is_available(login_provider: str) -> bool:
    """Check if credentials exist for a login provider."""
    if login_provider == "codex":
        from kohakuterrarium.llm.codex_auth import CodexTokens

        return CodexTokens.load() is not None
    if login_provider in PROVIDER_KEY_MAP:
        return bool(get_api_key(login_provider))
    return False


def list_all() -> list[dict[str, Any]]:
    """List all profiles and presets with availability info."""
    result = []

    # User profiles
    for name, profile in load_profiles().items():
        login = _login_provider_for(profile)
        result.append(
            {
                "name": name,
                "model": profile.model,
                "provider": profile.provider,
                "login_provider": login,
                "available": _is_available(login),
                "source": "user",
                "max_context": profile.max_context,
            }
        )

    # Presets (skip if user has same name)
    user_names = {r["name"] for r in result}
    for name, data in PRESETS.items():
        if name not in user_names:
            login = _login_provider_for(data)
            result.append(
                {
                    "name": name,
                    "model": data.get("model", ""),
                    "provider": data.get("provider", ""),
                    "login_provider": login,
                    "available": _is_available(login),
                    "source": "preset",
                    "max_context": data.get("max_context", 0),
                }
            )

    # Default
    default = get_default_model()
    for r in result:
        r["is_default"] = r["name"] == default or r["model"] == default

    return result


# ── API key storage ───────────────────────────────────────────
# Keys are stored in ~/.kohakuterrarium/api_keys.yaml
# Format: { openrouter: "sk-or-...", openai: "sk-...", anthropic: "sk-ant-...", gemini: "AI..." }

# Maps provider short names to env var names (for fallback)
PROVIDER_KEY_MAP: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mimo": "MIMO_API_KEY",
}


def save_api_key(provider: str, key: str) -> None:
    """Save an API key for a provider."""
    KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    keys = _load_api_keys()
    keys[provider] = key
    with open(KEYS_PATH, "w") as f:
        yaml.dump(keys, f, default_flow_style=False)
    logger.info("API key saved", provider=provider)


def get_api_key(provider_or_env: str) -> str:
    """Get an API key by provider name or env var name.

    Resolution:
      1. Stored key in ~/.kohakuterrarium/api_keys.yaml
      2. Environment variable
      3. Empty string (not found)
    """
    # Normalize: env var name -> provider name
    provider = provider_or_env
    for prov, env in PROVIDER_KEY_MAP.items():
        if provider_or_env == env:
            provider = prov
            break

    # 1. Stored key
    keys = _load_api_keys()
    if provider in keys and keys[provider]:
        return keys[provider]

    # 2. Env var (by provider name or direct env var name)
    env_var = PROVIDER_KEY_MAP.get(provider, provider_or_env)
    key = os.environ.get(env_var, "")
    if key:
        return key

    # 3. Try the raw string as env var
    if provider_or_env != env_var:
        key = os.environ.get(provider_or_env, "")

    return key


def list_api_keys() -> dict[str, str]:
    """List stored API keys (masked)."""
    keys = _load_api_keys()
    masked = {}
    for provider, key in keys.items():
        if key and len(key) > 8:
            masked[provider] = f"{key[:4]}...{key[-4:]}"
        elif key:
            masked[provider] = "****"
    return masked


def _load_api_keys() -> dict[str, str]:
    """Load API keys from file."""
    if not KEYS_PATH.exists():
        return {}
    try:
        with open(KEYS_PATH) as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

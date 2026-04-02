"""
LLM provider factory.

Creates the correct LLM provider based on auth_mode in agent config.
"""

from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.llm.base import LLMProvider
from kohakuterrarium.llm.codex_provider import CodexOAuthProvider
from kohakuterrarium.llm.openai import OpenAIProvider
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def create_llm_provider(config: AgentConfig) -> LLMProvider:
    """Create an LLM provider from agent config.

    Selects between Codex OAuth (ChatGPT subscription) and standard
    OpenAI-compatible API key auth based on config.auth_mode.
    """
    if config.auth_mode == "codex-oauth":
        provider = CodexOAuthProvider(
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            service_tier=config.service_tier,
        )
        logger.info(
            "Using Codex OAuth provider (ChatGPT subscription)",
            model=config.model,
        )
        return provider

    # Standard API key auth (OpenAI, OpenRouter, etc.)
    api_key = config.get_api_key()
    if not api_key:
        raise ValueError(
            f"API key not found. "
            f"Set {config.api_key_env} environment variable."
        )

    return OpenAIProvider(
        api_key=api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

"""Tests for LLM profile system."""

from unittest.mock import patch

import pytest

from kohakuterrarium.llm.profiles import (
    ALIASES,
    PRESETS,
    LLMProfile,
    delete_profile,
    get_default_model,
    get_preset,
    list_all,
    load_backends,
    load_profiles,
    resolve_controller_llm,
    save_profile,
    set_default_model,
)


@pytest.fixture
def tmp_profiles(tmp_path):
    """Use a temp file for profiles instead of ~/.kohakuterrarium/."""
    profiles_path = tmp_path / "llm_profiles.yaml"
    with patch("kohakuterrarium.llm.profiles.PROFILES_PATH", profiles_path):
        yield profiles_path


# ── Presets ───────────────────────────────────────────────────


class TestPresets:
    def test_presets_not_empty(self):
        assert len(PRESETS) > 0

    def test_all_presets_have_required_fields(self):
        for name, data in PRESETS.items():
            assert "provider" in data, f"{name} missing provider"
            assert "model" in data, f"{name} missing model"
            assert "max_context" in data, f"{name} missing max_context"

    def test_aliases_point_to_valid_presets(self):
        for alias, target in ALIASES.items():
            assert (
                target in PRESETS
            ), f"alias '{alias}' points to missing preset '{target}'"

    def test_get_preset_by_name(self):
        p = get_preset("gpt-5.4")
        assert p is not None
        assert p.model == "gpt-5.4"
        assert p.max_context > 0

    def test_get_preset_by_alias(self):
        p = get_preset("gemini")
        assert p is not None
        assert "gemini" in p.model

    def test_get_preset_nonexistent(self):
        assert get_preset("nonexistent-model-xyz") is None


# ── LLMProfile ────────────────────────────────────────────────


class TestLLMProfile:
    def test_from_dict(self):
        p = LLMProfile.from_dict(
            "test",
            {
                "provider": "openai",
                "model": "test-model",
                "max_context": 100000,
            },
        )
        assert p.name == "test"
        assert p.model == "test-model"
        assert p.max_context == 100000

    def test_to_dict(self):
        p = LLMProfile(
            name="test",
            provider="openai",
            model="test-model",
            max_context=100000,
            base_url="https://example.com",
        )
        d = p.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "test-model"
        assert d["base_url"] == "https://example.com"
        assert "name" not in d  # name is not in the dict

    def test_defaults(self):
        p = LLMProfile(name="test", provider="openai", model="m")
        assert p.max_context == 256000
        assert p.max_output == 65536
        assert p.temperature is None
        assert p.extra_body == {}


# ── Profile storage ───────────────────────────────────────────


class TestProfileStorage:
    def test_save_and_load(self, tmp_profiles):
        profile = LLMProfile(
            name="myprofile",
            provider="openai",
            model="custom-model",
            max_context=50000,
        )
        save_profile(profile)

        profiles = load_profiles()
        assert "myprofile" in profiles
        assert profiles["myprofile"].model == "custom-model"

    def test_delete_profile(self, tmp_profiles):
        profile = LLMProfile(name="todel", provider="openai", model="m")
        save_profile(profile)
        assert delete_profile("todel") is True
        assert delete_profile("todel") is False  # already deleted

    def test_default_model(self, tmp_profiles):
        # No explicit default + mock no API keys → empty
        with patch("kohakuterrarium.llm.profiles._is_available", return_value=False):
            assert get_default_model() == ""
        set_default_model("gpt-5.4")
        assert get_default_model() == "gpt-5.4"

    def test_load_empty(self, tmp_profiles):
        profiles = load_profiles()
        assert profiles == {}

    def test_load_corrupt_file(self, tmp_profiles):
        tmp_profiles.write_text("not: valid: yaml: [[[")
        profiles = load_profiles()
        assert profiles == {}


# ── Profile resolution ────────────────────────────────────────


class TestResolution:
    def test_resolve_from_config_llm(self, tmp_profiles):
        """controller.llm = 'gpt-5.4' resolves to preset."""
        profile = resolve_controller_llm({"llm": "gpt-5.4"})
        assert profile is not None
        assert profile.model == "gpt-5.4"

    def test_resolve_from_alias(self, tmp_profiles):
        profile = resolve_controller_llm({"llm": "gemini"})
        assert profile is not None
        assert "gemini" in profile.model

    def test_resolve_from_default(self, tmp_profiles):
        set_default_model("gpt-4o")
        profile = resolve_controller_llm({})
        assert profile is not None
        assert profile.model == "gpt-4o"

    def test_resolve_cli_override(self, tmp_profiles):
        """CLI --llm takes priority over config."""
        profile = resolve_controller_llm({"llm": "gpt-5.4"}, llm_override="gemini")
        assert profile is not None
        assert "gemini" in profile.model

    def test_resolve_inline_overrides(self, tmp_profiles):
        """Inline controller fields override profile defaults."""
        profile = resolve_controller_llm(
            {"llm": "gpt-5.4", "temperature": 0.3, "reasoning_effort": "xhigh"}
        )
        assert profile is not None
        assert profile.temperature == 0.3
        assert profile.reasoning_effort == "xhigh"

    def test_resolve_user_profile_over_preset(self, tmp_profiles):
        """User profile with same name as preset takes priority."""
        custom = LLMProfile(
            name="gpt-5.4",
            provider="openai",
            model="custom-gpt-5.4",
            max_context=999999,
        )
        save_profile(custom)
        profile = resolve_controller_llm({"llm": "gpt-5.4"})
        assert profile is not None
        assert profile.model == "custom-gpt-5.4"

    def test_resolve_no_profile_returns_none(self, tmp_profiles):
        """No llm, no default, no API keys -> None (backward compat)."""
        with patch("kohakuterrarium.llm.profiles._is_available", return_value=False):
            profile = resolve_controller_llm({})
            assert profile is None

    def test_resolve_unknown_returns_none(self, tmp_profiles):
        profile = resolve_controller_llm({"llm": "nonexistent-xyz"})
        assert profile is None


# ── list_all ──────────────────────────────────────────────────


class TestListAll:
    def test_includes_presets(self, tmp_profiles):
        entries = list_all()
        names = [e["name"] for e in entries]
        assert "gpt-5.4" in names
        assert "gemini-3.1-pro" in names

    def test_includes_user_profiles(self, tmp_profiles):
        save_profile(LLMProfile(name="custom", provider="openai", model="m"))
        entries = list_all()
        names = [e["name"] for e in entries]
        assert "custom" in names

    def test_marks_default(self, tmp_profiles):
        set_default_model("gpt-5.4")
        entries = list_all()
        defaults = [e for e in entries if e.get("is_default")]
        assert len(defaults) >= 1
        assert defaults[0]["name"] == "gpt-5.4"


# ── Ollama ────────────────────────────────────────────────────


class TestOllama:
    def test_backend_registered(self, tmp_profiles):
        backends = load_backends()
        assert "ollama" in backends
        ollama = backends["ollama"]
        assert ollama.backend_type == "openai"
        assert "11434" in ollama.base_url

    def test_presets_resolve_to_ollama_backend(self, tmp_profiles):
        for name in (
            "qwen3.5-9b-local",
            "qwen3.5-27b-local",
            "qwen3.6-35b-local",
            "gemma4-e4b-local",
            "gemma4-26b-local",
        ):
            profile = get_preset(name)
            assert profile is not None, f"preset {name!r} not found"
            assert profile.provider == "ollama"
            assert profile.backend_type == "openai"
            assert "11434" in profile.base_url

    def test_aliases_resolve(self, tmp_profiles):
        for alias in ("ollama", "qwen-local", "gemma-local"):
            profile = get_preset(alias)
            assert profile is not None, f"alias {alias!r} not resolved"
            assert profile.provider == "ollama"

    def test_localhost_base_url_inferred_as_ollama(self, tmp_profiles):
        """Legacy presets with localhost:11434 should reverse-map to ollama."""
        from kohakuterrarium.llm.profiles import _legacy_provider_from_data

        assert (
            _legacy_provider_from_data(
                {"base_url": "http://localhost:11434/v1", "model": "x"}
            )
            == "ollama"
        )
        assert (
            _legacy_provider_from_data(
                {"base_url": "http://127.0.0.1:11434/v1", "model": "x"}
            )
            == "ollama"
        )

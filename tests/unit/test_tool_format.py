"""
Tests for configurable tool format support.

Tests for:
- ToolCallFormat dataclass and preset constants
- tool_format field in AgentConfig
- _resolve_tool_format in AgentInitMixin

These tests run offline without API keys.
"""

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

import pytest

from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.parsing.format import BRACKET_FORMAT, XML_FORMAT, ToolCallFormat


class TestToolCallFormat:
    """Tests for ToolCallFormat dataclass and presets."""

    def test_bracket_format_defaults(self):
        """Default format matches bracket syntax."""
        fmt = ToolCallFormat()
        assert fmt.start_char == "["
        assert fmt.end_char == "]"
        assert fmt.slash_means_open is True
        assert fmt.arg_style == "line"
        assert fmt.arg_prefix == "@@"
        assert fmt.arg_kv_sep == "="

    def test_bracket_preset_matches_default(self):
        """BRACKET_FORMAT preset matches the default constructor."""
        default = ToolCallFormat()
        assert BRACKET_FORMAT == default

    def test_xml_format_values(self):
        """XML format has correct delimiters."""
        assert XML_FORMAT.start_char == "<"
        assert XML_FORMAT.end_char == ">"
        assert XML_FORMAT.slash_means_open is False
        assert XML_FORMAT.arg_style == "inline"
        assert XML_FORMAT.arg_prefix == ""

    def test_custom_format(self):
        """Custom format accepts arbitrary delimiters."""
        fmt = ToolCallFormat(
            start_char="{",
            end_char="}",
            slash_means_open=False,
            arg_style="inline",
            arg_prefix="--",
            arg_kv_sep=":",
        )
        assert fmt.start_char == "{"
        assert fmt.end_char == "}"
        assert fmt.slash_means_open is False
        assert fmt.arg_style == "inline"
        assert fmt.arg_prefix == "--"
        assert fmt.arg_kv_sep == ":"

    def test_format_is_frozen(self):
        """ToolCallFormat is immutable (frozen dataclass)."""
        fmt = ToolCallFormat()
        with pytest.raises(FrozenInstanceError):
            fmt.start_char = "<"

    def test_format_equality(self):
        """Two formats with same values are equal."""
        a = ToolCallFormat(start_char="<", end_char=">")
        b = ToolCallFormat(start_char="<", end_char=">")
        assert a == b

    def test_format_inequality(self):
        """Formats with different values are not equal."""
        assert BRACKET_FORMAT != XML_FORMAT

    def test_bracket_and_xml_presets_are_distinct(self):
        """BRACKET_FORMAT and XML_FORMAT differ in all key ways."""
        assert BRACKET_FORMAT.start_char != XML_FORMAT.start_char
        assert BRACKET_FORMAT.end_char != XML_FORMAT.end_char
        assert BRACKET_FORMAT.slash_means_open != XML_FORMAT.slash_means_open
        assert BRACKET_FORMAT.arg_style != XML_FORMAT.arg_style


class TestConfigToolFormat:
    """Tests for tool_format in agent config."""

    def test_default_is_bracket(self):
        """Default config uses bracket format."""
        config = AgentConfig(name="test")
        assert config.tool_format == "bracket"

    def test_config_accepts_string(self):
        """Config accepts preset string names."""
        for preset in ("bracket", "xml", "native"):
            config = AgentConfig(name="test", tool_format=preset)
            assert config.tool_format == preset

    def test_config_accepts_dict(self):
        """Config accepts custom format dict."""
        custom = {
            "start_char": "{",
            "end_char": "}",
            "slash_means_open": True,
            "arg_style": "line",
            "arg_prefix": "@@",
        }
        config = AgentConfig(name="test", tool_format=custom)
        assert isinstance(config.tool_format, dict)
        assert config.tool_format["start_char"] == "{"

    def test_config_dict_preserves_all_keys(self):
        """Config dict preserves all format keys."""
        custom = {
            "start_char": "<",
            "end_char": ">",
            "slash_means_open": False,
            "arg_style": "inline",
            "arg_prefix": "",
            "arg_kv_sep": "=",
        }
        config = AgentConfig(name="test", tool_format=custom)
        assert config.tool_format == custom


class TestFormatResolution:
    """Tests for _resolve_tool_format in AgentInitMixin."""

    def _make_mixin(self, tool_format: str | dict = "bracket"):
        """Create a minimal AgentInitMixin-like object for testing."""
        from kohakuterrarium.core.agent_init import AgentInitMixin

        mixin = object.__new__(AgentInitMixin)
        mixin.config = AgentConfig(name="test", tool_format=tool_format)
        return mixin

    def test_resolve_bracket(self):
        """String 'bracket' resolves to BRACKET_FORMAT."""
        mixin = self._make_mixin("bracket")
        result = mixin._resolve_tool_format()
        assert result == BRACKET_FORMAT

    def test_resolve_xml(self):
        """String 'xml' resolves to XML_FORMAT."""
        mixin = self._make_mixin("xml")
        result = mixin._resolve_tool_format()
        assert result == XML_FORMAT

    def test_resolve_native(self):
        """String 'native' resolves to None (bypass parser)."""
        mixin = self._make_mixin("native")
        result = mixin._resolve_tool_format()
        assert result is None

    def test_resolve_custom_dict(self):
        """Dict resolves to custom ToolCallFormat."""
        custom = {
            "start_char": "{",
            "end_char": "}",
            "slash_means_open": True,
            "arg_style": "line",
            "arg_prefix": "@@",
        }
        mixin = self._make_mixin(custom)
        result = mixin._resolve_tool_format()
        assert isinstance(result, ToolCallFormat)
        assert result.start_char == "{"
        assert result.end_char == "}"

    def test_resolve_custom_dict_all_fields(self):
        """Dict with all fields resolves correctly."""
        custom = {
            "start_char": "<",
            "end_char": ">",
            "slash_means_open": False,
            "arg_style": "inline",
            "arg_prefix": "",
            "arg_kv_sep": ":",
        }
        mixin = self._make_mixin(custom)
        result = mixin._resolve_tool_format()
        assert isinstance(result, ToolCallFormat)
        assert result.start_char == "<"
        assert result.end_char == ">"
        assert result.slash_means_open is False
        assert result.arg_style == "inline"
        assert result.arg_prefix == ""
        assert result.arg_kv_sep == ":"

    def test_resolve_unknown_falls_back(self):
        """Unknown string falls back to bracket with warning."""
        mixin = self._make_mixin("nonexistent_format")
        result = mixin._resolve_tool_format()
        assert result == BRACKET_FORMAT

    def test_resolve_empty_string_falls_back(self):
        """Empty string falls back to bracket."""
        mixin = self._make_mixin("")
        result = mixin._resolve_tool_format()
        assert result == BRACKET_FORMAT

    def test_resolve_partial_dict(self):
        """Dict with only some fields uses defaults for the rest."""
        custom = {"start_char": "{"}
        mixin = self._make_mixin(custom)
        result = mixin._resolve_tool_format()
        assert isinstance(result, ToolCallFormat)
        assert result.start_char == "{"
        # Other fields should get defaults
        assert result.end_char == "]"
        assert result.slash_means_open is True

    def test_resolve_default_config(self):
        """Default AgentConfig resolves to BRACKET_FORMAT."""
        mixin = self._make_mixin()
        result = mixin._resolve_tool_format()
        assert result == BRACKET_FORMAT

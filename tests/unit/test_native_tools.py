"""
Unit tests for native tool calling support.

Tests for:
- ToolSchema creation and API format conversion
- NativeToolCall argument parsing
- build_tool_schemas helper
- OpenAIProvider tool call accumulation
"""

import pytest

from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import NativeToolCall, ToolSchema
from kohakuterrarium.llm.tools import build_tool_schemas
from kohakuterrarium.modules.tool.base import BaseTool, ToolConfig, ToolResult


# =============================================================================
# ToolSchema Tests
# =============================================================================


class TestToolSchema:
    """Tests for ToolSchema dataclass."""

    def test_default_parameters(self):
        """Test that default parameters create empty object schema."""
        schema = ToolSchema(name="test", description="A test tool")
        assert schema.parameters == {"type": "object", "properties": {}}

    def test_to_api_format_basic(self):
        """Test conversion to OpenAI API tools format."""
        schema = ToolSchema(
            name="bash",
            description="Run shell commands",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    }
                },
                "required": ["command"],
            },
        )
        api_format = schema.to_api_format()

        assert api_format["type"] == "function"
        assert api_format["function"]["name"] == "bash"
        assert api_format["function"]["description"] == "Run shell commands"
        assert api_format["function"]["parameters"]["type"] == "object"
        assert "command" in api_format["function"]["parameters"]["properties"]
        assert api_format["function"]["parameters"]["required"] == ["command"]

    def test_to_api_format_minimal(self):
        """Test API format with minimal schema."""
        schema = ToolSchema(name="ping", description="Ping a host")
        api_format = schema.to_api_format()

        assert api_format == {
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Ping a host",
                "parameters": {"type": "object", "properties": {}},
            },
        }

    def test_to_api_format_complex_parameters(self):
        """Test API format with nested parameter schemas."""
        schema = ToolSchema(
            name="search",
            description="Search files",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                    "options": {
                        "type": "object",
                        "properties": {
                            "case_sensitive": {"type": "boolean"},
                        },
                    },
                },
                "required": ["query"],
            },
        )
        api_format = schema.to_api_format()
        params = api_format["function"]["parameters"]

        assert params["properties"]["query"]["type"] == "string"
        assert params["properties"]["max_results"]["default"] == 10
        assert params["properties"]["options"]["type"] == "object"


# =============================================================================
# NativeToolCall Tests
# =============================================================================


class TestNativeToolCall:
    """Tests for NativeToolCall dataclass."""

    def test_parsed_arguments_valid_json(self):
        """Test parsing valid JSON arguments."""
        tc = NativeToolCall(
            id="call_123",
            name="bash",
            arguments='{"command": "ls -la"}',
        )
        args = tc.parsed_arguments()
        assert args == {"command": "ls -la"}

    def test_parsed_arguments_empty_object(self):
        """Test parsing empty JSON object."""
        tc = NativeToolCall(id="call_456", name="ping", arguments="{}")
        args = tc.parsed_arguments()
        assert args == {}

    def test_parsed_arguments_invalid_json(self):
        """Test parsing invalid JSON falls back to _raw."""
        tc = NativeToolCall(
            id="call_789",
            name="broken",
            arguments="not valid json {",
        )
        args = tc.parsed_arguments()
        assert args == {"_raw": "not valid json {"}

    def test_parsed_arguments_complex(self):
        """Test parsing complex nested JSON arguments."""
        tc = NativeToolCall(
            id="call_abc",
            name="write_file",
            arguments='{"path": "/tmp/test.txt", "content": "hello\\nworld", "overwrite": true}',
        )
        args = tc.parsed_arguments()
        assert args["path"] == "/tmp/test.txt"
        assert args["content"] == "hello\nworld"
        assert args["overwrite"] is True


# =============================================================================
# build_tool_schemas Tests
# =============================================================================


class _DummyTool(BaseTool):
    """A minimal test tool for registry tests."""

    def __init__(self, name: str = "dummy", desc: str = "A dummy tool"):
        super().__init__(ToolConfig())
        self._name = name
        self._desc = desc

    @property
    def tool_name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    async def _execute(self, args, **kwargs):
        return ToolResult(output="ok")


class _DummyToolWithSchema(BaseTool):
    """A test tool that provides a parameters schema."""

    def __init__(self):
        super().__init__(ToolConfig())

    @property
    def tool_name(self) -> str:
        return "schema_tool"

    @property
    def description(self) -> str:
        return "Tool with custom schema"

    def get_parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }

    async def _execute(self, args, **kwargs):
        return ToolResult(output="ok")


class TestBuildToolSchemas:
    """Tests for build_tool_schemas utility."""

    def test_empty_registry(self):
        """Test with no registered tools."""
        registry = Registry()
        schemas = build_tool_schemas(registry)
        assert schemas == []

    def test_single_tool_default_schema(self):
        """Test building schema for tool without get_parameters_schema."""
        registry = Registry()
        registry.register_tool(_DummyTool("bash", "Execute shell commands"))

        schemas = build_tool_schemas(registry)
        assert len(schemas) == 1
        assert schemas[0].name == "bash"
        assert schemas[0].description == "Execute shell commands"
        # Should get fallback content-based schema
        assert schemas[0].parameters["type"] == "object"
        assert "content" in schemas[0].parameters["properties"]

    def test_tool_with_custom_schema(self):
        """Test building schema for tool with get_parameters_schema."""
        registry = Registry()
        registry.register_tool(_DummyToolWithSchema())

        schemas = build_tool_schemas(registry)
        assert len(schemas) == 1
        assert schemas[0].name == "schema_tool"
        assert schemas[0].parameters["properties"]["query"]["type"] == "string"
        assert schemas[0].parameters["required"] == ["query"]

    def test_multiple_tools(self):
        """Test building schemas for multiple tools."""
        registry = Registry()
        registry.register_tool(_DummyTool("bash", "Run commands"))
        registry.register_tool(_DummyTool("read", "Read files"))
        registry.register_tool(_DummyToolWithSchema())

        schemas = build_tool_schemas(registry)
        assert len(schemas) == 3

        names = {s.name for s in schemas}
        assert names == {"bash", "read", "schema_tool"}

    def test_api_format_roundtrip(self):
        """Test that built schemas produce valid API format."""
        registry = Registry()
        registry.register_tool(_DummyToolWithSchema())

        schemas = build_tool_schemas(registry)
        api_format = schemas[0].to_api_format()

        assert api_format["type"] == "function"
        assert api_format["function"]["name"] == "schema_tool"
        assert api_format["function"]["description"] == "Tool with custom schema"
        assert "query" in api_format["function"]["parameters"]["properties"]


# =============================================================================
# OpenAIProvider Tool Call Accumulation Tests
# =============================================================================


class TestOpenAIProviderToolAccumulation:
    """Tests for OpenAIProvider._accumulate_tool_calls and _finalize_tool_calls."""

    def _make_provider(self):
        """Create a provider instance for testing internal methods."""
        from kohakuterrarium.llm.openai import OpenAIProvider

        return OpenAIProvider(api_key="test-key-not-real", model="gpt-4o-mini")

    def test_accumulate_single_tool_call(self):
        """Test accumulating a single tool call across chunks."""
        provider = self._make_provider()
        pending: dict[int, dict[str, str]] = {}

        # First chunk: id and function name
        provider._accumulate_tool_calls(
            [
                {
                    "index": 0,
                    "id": "call_abc123",
                    "function": {"name": "bash", "arguments": ""},
                }
            ],
            pending,
        )

        # Subsequent chunks: argument fragments
        provider._accumulate_tool_calls(
            [{"index": 0, "function": {"arguments": '{"com'}}],
            pending,
        )
        provider._accumulate_tool_calls(
            [{"index": 0, "function": {"arguments": 'mand": '}}],
            pending,
        )
        provider._accumulate_tool_calls(
            [{"index": 0, "function": {"arguments": '"ls -la"}'}}],
            pending,
        )

        provider._finalize_tool_calls(pending)

        assert len(provider.last_tool_calls) == 1
        tc = provider.last_tool_calls[0]
        assert tc.id == "call_abc123"
        assert tc.name == "bash"
        assert tc.arguments == '{"command": "ls -la"}'
        assert tc.parsed_arguments() == {"command": "ls -la"}

    def test_accumulate_multiple_tool_calls(self):
        """Test accumulating multiple parallel tool calls."""
        provider = self._make_provider()
        pending: dict[int, dict[str, str]] = {}

        # Two tool calls arriving interleaved
        provider._accumulate_tool_calls(
            [
                {
                    "index": 0,
                    "id": "call_001",
                    "function": {"name": "bash", "arguments": ""},
                },
                {
                    "index": 1,
                    "id": "call_002",
                    "function": {"name": "read", "arguments": ""},
                },
            ],
            pending,
        )

        provider._accumulate_tool_calls(
            [
                {"index": 0, "function": {"arguments": '{"cmd": "ls"}'}},
                {"index": 1, "function": {"arguments": '{"path": "/tmp"}'}},
            ],
            pending,
        )

        provider._finalize_tool_calls(pending)

        assert len(provider.last_tool_calls) == 2
        assert provider.last_tool_calls[0].name == "bash"
        assert provider.last_tool_calls[0].id == "call_001"
        assert provider.last_tool_calls[1].name == "read"
        assert provider.last_tool_calls[1].id == "call_002"

    def test_finalize_empty_pending(self):
        """Test finalizing with no pending tool calls."""
        provider = self._make_provider()
        provider._finalize_tool_calls({})
        assert provider.last_tool_calls == []

    def test_last_tool_calls_initially_empty(self):
        """Test that last_tool_calls is empty on fresh provider."""
        provider = self._make_provider()
        assert provider.last_tool_calls == []

    def test_build_request_body_without_tools(self):
        """Test request body has no tools key when tools=None."""
        provider = self._make_provider()
        body = provider._build_request_body(
            [{"role": "user", "content": "hello"}],
            stream=True,
        )
        assert "tools" not in body

    def test_build_request_body_with_tools(self):
        """Test request body includes tools when provided."""
        provider = self._make_provider()
        schemas = [
            ToolSchema(
                name="bash",
                description="Run commands",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                },
            )
        ]
        body = provider._build_request_body(
            [{"role": "user", "content": "hello"}],
            stream=True,
            tools=schemas,
        )
        assert "tools" in body
        assert len(body["tools"]) == 1
        assert body["tools"][0]["type"] == "function"
        assert body["tools"][0]["function"]["name"] == "bash"

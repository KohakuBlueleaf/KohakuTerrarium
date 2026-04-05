"""Tests for the user command system (slash commands).

Covers:
- Command registration and lookup (builtins, aliases)
- parse_slash_command parsing
- UI payload constructors (ui_notify, ui_select, ui_confirm, etc.)
- Command execution (/help, /exit, /clear, /status, /compact)
- BaseInputModule.try_user_command dispatch
"""

from unittest.mock import MagicMock

from kohakuterrarium.builtins.user_commands import (
    get_builtin_user_command,
    list_builtin_user_commands,
)
from kohakuterrarium.modules.user_command.base import (
    CommandLayer,
    UserCommandContext,
    parse_slash_command,
    ui_confirm,
    ui_info_panel,
    ui_list,
    ui_notify,
    ui_select,
    ui_text,
)

# ── parse_slash_command ──────────────────────────────────────────────


class TestParseSlashCommand:
    def test_simple(self):
        assert parse_slash_command("/help") == ("help", "")

    def test_with_args(self):
        assert parse_slash_command("/model claude-opus-4.6") == (
            "model",
            "claude-opus-4.6",
        )

    def test_with_multi_args(self):
        name, args = parse_slash_command("/model some long name here")
        assert name == "model"
        assert args == "some long name here"

    def test_case_insensitive(self):
        assert parse_slash_command("/HELP") == ("help", "")

    def test_leading_slashes_stripped(self):
        assert parse_slash_command("//double") == ("double", "")

    def test_empty(self):
        assert parse_slash_command("/") == ("", "")


# ── UI payload constructors ──────────────────────────────────────────


class TestUIPayloads:
    def test_ui_text(self):
        d = ui_text("hello")
        assert d["type"] == "text"
        assert d["message"] == "hello"

    def test_ui_notify(self):
        d = ui_notify("done", level="success")
        assert d["type"] == "notify"
        assert d["level"] == "success"

    def test_ui_notify_default_level(self):
        d = ui_notify("info msg")
        assert d["level"] == "info"

    def test_ui_confirm(self):
        d = ui_confirm("Are you sure?", action="clear", action_args="--force")
        assert d["type"] == "confirm"
        assert d["action"] == "clear"
        assert d["action_args"] == "--force"

    def test_ui_select(self):
        opts = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
        d = ui_select("Pick one", opts, current="a", action="model")
        assert d["type"] == "select"
        assert len(d["options"]) == 2
        assert d["current"] == "a"
        assert d["action"] == "model"

    def test_ui_info_panel(self):
        fields = [{"key": "Model", "value": "gpt-5"}]
        d = ui_info_panel("Status", fields)
        assert d["type"] == "info_panel"
        assert d["fields"] == fields

    def test_ui_list(self):
        items = [{"label": "/help", "description": "Show help"}]
        d = ui_list("Commands", items)
        assert d["type"] == "list"
        assert len(d["items"]) == 1


# ── Registration ─────────────────────────────────────────────────────


class TestRegistration:
    def test_builtins_registered(self):
        names = list_builtin_user_commands()
        assert "help" in names
        assert "exit" in names
        assert "model" in names
        assert "status" in names
        assert "clear" in names
        assert "compact" in names

    def test_get_by_name(self):
        cmd = get_builtin_user_command("help")
        assert cmd is not None
        assert cmd.name == "help"

    def test_get_by_alias(self):
        cmd = get_builtin_user_command("quit")
        assert cmd is not None
        assert cmd.name == "exit"

    def test_get_by_alias_h(self):
        cmd = get_builtin_user_command("h")
        assert cmd is not None
        assert cmd.name == "help"

    def test_get_by_alias_llm(self):
        cmd = get_builtin_user_command("llm")
        assert cmd is not None
        assert cmd.name == "model"

    def test_get_nonexistent(self):
        assert get_builtin_user_command("nonexistent") is None

    def test_command_layers(self):
        assert get_builtin_user_command("help").layer == CommandLayer.INPUT
        assert get_builtin_user_command("exit").layer == CommandLayer.INPUT
        assert get_builtin_user_command("model").layer == CommandLayer.AGENT
        assert get_builtin_user_command("status").layer == CommandLayer.AGENT


# ── Command execution ────────────────────────────────────────────────


class TestHelpCommand:
    async def test_help_output(self):
        registry = {
            n: get_builtin_user_command(n) for n in list_builtin_user_commands()
        }
        ctx = UserCommandContext(extra={"command_registry": registry})
        result = await get_builtin_user_command("help").execute("", ctx)
        assert result.success
        assert "/help" in result.output
        assert "/model" in result.output
        assert result.data["type"] == "list"
        assert len(result.data["items"]) == len(registry)


class TestExitCommand:
    async def test_exit_with_input_module(self):
        mock_input = MagicMock()
        mock_input._exit_requested = False
        ctx = UserCommandContext(input_module=mock_input)
        result = await get_builtin_user_command("exit").execute("", ctx)
        assert result.consumed
        assert mock_input._exit_requested is True

    async def test_exit_without_input_module(self):
        ctx = UserCommandContext()
        result = await get_builtin_user_command("exit").execute("", ctx)
        assert result.data["type"] == "confirm"
        assert result.data["action"] == "exit"


class TestClearCommand:
    async def test_clear_force(self):
        mock_conv = MagicMock()
        mock_agent = MagicMock()
        mock_agent.controller.conversation = mock_conv
        ctx = UserCommandContext(agent=mock_agent)
        result = await get_builtin_user_command("clear").execute("--force", ctx)
        assert result.success
        mock_conv.clear.assert_called_once()
        assert result.data["type"] == "notify"

    async def test_clear_with_input_module(self):
        mock_conv = MagicMock()
        mock_conv.get_messages.return_value = [1, 2, 3]
        mock_agent = MagicMock()
        mock_agent.controller.conversation = mock_conv
        ctx = UserCommandContext(agent=mock_agent, input_module=MagicMock())
        result = await get_builtin_user_command("clear").execute("", ctx)
        assert result.success
        mock_conv.clear.assert_called_once()

    async def test_clear_without_input_module(self):
        mock_conv = MagicMock()
        mock_conv.get_messages.return_value = [1, 2, 3]
        mock_agent = MagicMock()
        mock_agent.controller.conversation = mock_conv
        ctx = UserCommandContext(agent=mock_agent)
        result = await get_builtin_user_command("clear").execute("", ctx)
        assert result.data["type"] == "confirm"
        mock_conv.clear.assert_not_called()

    async def test_clear_no_agent(self):
        ctx = UserCommandContext()
        result = await get_builtin_user_command("clear").execute("", ctx)
        assert not result.success


class TestStatusCommand:
    async def test_status_output(self):
        mock_agent = MagicMock()
        mock_agent.config.name = "test-agent"
        mock_agent.llm.model = "gpt-5"
        mock_agent.controller.conversation.get_messages.return_value = list(range(10))
        mock_agent.registry.list_tools.return_value = ["bash", "read"]
        mock_agent.executor.get_running_jobs.return_value = []
        mock_agent.compact_manager.is_compacting = False

        ctx = UserCommandContext(agent=mock_agent)
        result = await get_builtin_user_command("status").execute("", ctx)
        assert result.success
        assert "test-agent" in result.output
        assert "gpt-5" in result.output
        assert result.data["type"] == "info_panel"
        assert any(f["key"] == "Model" for f in result.data["fields"])


class TestCompactCommand:
    async def test_compact_triggers(self):
        mock_mgr = MagicMock()
        mock_mgr.is_compacting = False
        mock_agent = MagicMock()
        mock_agent.compact_manager = mock_mgr
        ctx = UserCommandContext(agent=mock_agent)
        result = await get_builtin_user_command("compact").execute("", ctx)
        assert result.success
        mock_mgr.trigger_compact.assert_called_once()

    async def test_compact_already_running(self):
        mock_mgr = MagicMock()
        mock_mgr.is_compacting = True
        mock_agent = MagicMock()
        mock_agent.compact_manager = mock_mgr
        ctx = UserCommandContext(agent=mock_agent)
        result = await get_builtin_user_command("compact").execute("", ctx)
        assert "already" in result.output.lower()
        assert result.data["level"] == "warning"

    async def test_compact_no_manager(self):
        mock_agent = MagicMock()
        mock_agent.compact_manager = None
        ctx = UserCommandContext(agent=mock_agent)
        result = await get_builtin_user_command("compact").execute("", ctx)
        assert not result.success

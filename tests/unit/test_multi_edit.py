"""
Unit tests for the multi_edit tool.

Covers:
- Single and multiple sequential edits
- Atomicity on mid-sequence failure (file unchanged)
- replace_all behavior and ambiguity rejection
- Read-before-write guard
- Argument validation
- Diagnostic messages
"""

from pathlib import Path

from kohakuterrarium.builtins.tools.multi_edit import MultiEditTool
from kohakuterrarium.builtins.tools.read import ReadTool
from kohakuterrarium.modules.tool.base import ToolContext
from kohakuterrarium.utils.file_guard import FileReadState, PathBoundaryGuard


def _make_context(working_dir: Path) -> ToolContext:
    return ToolContext(
        agent_name="test_agent",
        session=None,
        working_dir=working_dir,
        file_read_state=FileReadState(),
        path_guard=PathBoundaryGuard(cwd=str(working_dir), mode="warn"),
    )


async def _read(target: Path, context: ToolContext) -> None:
    result = await ReadTool().execute({"path": str(target)}, context=context)
    assert result.success, f"read failed: {result.error}"


class TestMultiEditHappyPath:
    async def test_single_edit(self, tmp_path: Path):
        target = tmp_path / "code.py"
        target.write_text("def hello():\n    return 'world'\n")

        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": "return 'world'", "new": "return 'universe'"}],
            },
            context=context,
        )
        assert result.success, f"multi_edit failed: {result.error}"
        assert "universe" in target.read_text()
        assert "world" not in target.read_text()
        assert "1/1 edits applied" in result.output

    async def test_sequential_dependent_edits(self, tmp_path: Path):
        """Edit N should see the file as modified by edits 0..N-1."""
        target = tmp_path / "code.py"
        target.write_text("class OldName:\n    pass\n")

        context = _make_context(tmp_path)
        await _read(target, context)

        # After edit[0], the file contains "class NewName". Edit[1] depends on that.
        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [
                    {"old": "class OldName", "new": "class NewName"},
                    {
                        "old": "class NewName:\n    pass",
                        "new": "class NewName:\n    x = 1",
                    },
                ],
            },
            context=context,
        )
        assert result.success, f"multi_edit failed: {result.error}"
        content = target.read_text()
        assert "class NewName" in content
        assert "x = 1" in content
        assert "2/2 edits applied" in result.output

    async def test_replace_all_per_step(self, tmp_path: Path):
        target = tmp_path / "code.py"
        target.write_text("foo = 1\nfoo = 2\nfoo = 3\nbar = 4\n")

        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [
                    {"old": "foo", "new": "baz", "replace_all": True},
                    {"old": "bar = 4", "new": "bar = 40"},
                ],
            },
            context=context,
        )
        assert result.success, f"multi_edit failed: {result.error}"
        content = target.read_text()
        assert content.count("baz") == 3
        assert "foo" not in content
        assert "bar = 40" in content
        assert "replacements: 3, 1" in result.output

    async def test_empty_new_is_allowed(self, tmp_path: Path):
        target = tmp_path / "code.py"
        target.write_text("# TODO: remove\nreal_code()\n")

        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": "# TODO: remove\n", "new": ""}],
            },
            context=context,
        )
        assert result.success, f"multi_edit failed: {result.error}"
        assert target.read_text() == "real_code()\n"


class TestMultiEditAtomicity:
    async def test_mid_sequence_failure_leaves_file_unchanged(self, tmp_path: Path):
        """If any edit fails, the file on disk must not be modified."""
        target = tmp_path / "code.py"
        original = "alpha = 1\nbeta = 2\ngamma = 3\n"
        target.write_text(original)
        original_bytes = target.read_bytes()

        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [
                    {"old": "alpha = 1", "new": "alpha = 10"},  # ok
                    {"old": "beta = 2", "new": "beta = 20"},  # ok
                    {"old": "does_not_exist", "new": "whatever"},  # FAIL
                    {"old": "gamma = 3", "new": "gamma = 30"},  # skipped
                ],
            },
            context=context,
        )
        assert not result.success
        # File must be byte-identical to the original.
        assert target.read_bytes() == original_bytes
        # Diagnostic must identify the failing edit index.
        assert "edit[2]" in result.error
        assert "did not apply" in result.error
        # Prior successes should be reported.
        assert "edit[0] ok" in result.error
        assert "edit[1] ok" in result.error
        # And later edits reported as skipped.
        assert "1 later edit(s) skipped" in result.error

    async def test_first_edit_failure_also_atomic(self, tmp_path: Path):
        target = tmp_path / "code.py"
        original = "hello\n"
        target.write_text(original)
        original_bytes = target.read_bytes()

        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [
                    {"old": "nope", "new": "x"},
                    {"old": "hello", "new": "world"},
                ],
            },
            context=context,
        )
        assert not result.success
        assert target.read_bytes() == original_bytes
        assert "edit[0]" in result.error


class TestMultiEditAmbiguity:
    async def test_multiple_matches_without_replace_all_fails(self, tmp_path: Path):
        target = tmp_path / "code.py"
        original = "foo = 1\nfoo = 2\n"
        target.write_text(original)
        original_bytes = target.read_bytes()

        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": "foo", "new": "bar"}],
            },
            context=context,
        )
        assert not result.success
        assert target.read_bytes() == original_bytes
        assert "matches 2 locations" in result.error


class TestMultiEditGuards:
    async def test_blocks_when_file_not_read(self, tmp_path: Path):
        target = tmp_path / "code.py"
        target.write_text("hello\n")

        context = _make_context(tmp_path)
        # Intentionally skip reading the file.

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": "hello", "new": "goodbye"}],
            },
            context=context,
        )
        assert not result.success
        assert "has not been read yet" in result.error
        assert target.read_text() == "hello\n"

    async def test_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nope.py"
        context = _make_context(tmp_path)

        result = await MultiEditTool().execute(
            {
                "path": str(missing),
                "edits": [{"old": "a", "new": "b"}],
            },
            context=context,
        )
        assert not result.success
        assert "File not found" in result.error


class TestMultiEditArgValidation:
    async def test_missing_path(self, tmp_path: Path):
        context = _make_context(tmp_path)
        result = await MultiEditTool().execute(
            {"edits": [{"old": "a", "new": "b"}]},
            context=context,
        )
        assert not result.success
        assert "No path provided" in result.error

    async def test_missing_edits(self, tmp_path: Path):
        context = _make_context(tmp_path)
        result = await MultiEditTool().execute(
            {"path": str(tmp_path / "x.py")},
            context=context,
        )
        assert not result.success
        assert "edits must be a non-empty list" in result.error

    async def test_empty_edits_list(self, tmp_path: Path):
        context = _make_context(tmp_path)
        result = await MultiEditTool().execute(
            {"path": str(tmp_path / "x.py"), "edits": []},
            context=context,
        )
        assert not result.success
        assert "edits must be a non-empty list" in result.error

    async def test_empty_old_rejected(self, tmp_path: Path):
        target = tmp_path / "code.py"
        target.write_text("hello\n")
        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": "", "new": "x"}],
            },
            context=context,
        )
        assert not result.success
        assert "empty" in result.error

    async def test_non_string_old_rejected(self, tmp_path: Path):
        target = tmp_path / "code.py"
        target.write_text("hello\n")
        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": 123, "new": "x"}],
            },
            context=context,
        )
        assert not result.success
        assert "must be strings" in result.error


class TestMultiEditNoOp:
    async def test_all_edits_identity(self, tmp_path: Path):
        """If every edit is a no-op (old == new), result is reported cleanly."""
        target = tmp_path / "code.py"
        target.write_text("hello\n")
        context = _make_context(tmp_path)
        await _read(target, context)

        result = await MultiEditTool().execute(
            {
                "path": str(target),
                "edits": [{"old": "hello", "new": "hello"}],
            },
            context=context,
        )
        assert result.success, f"unexpected failure: {result.error}"
        assert "No changes made" in result.output
        assert target.read_text() == "hello\n"

"""
Multi-edit tool - apply multiple search/replace edits to one file atomically.

All edits are applied sequentially in memory; the file is written back only
if every edit succeeds. On any failure, the file on disk is left untouched
and the tool reports exactly which edit failed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles

from kohakuterrarium.builtins.tools.edit import EditTool
from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
    resolve_tool_path,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EditStep:
    """One step in a multi_edit sequence."""

    old: str
    new: str
    replace_all: bool = False


@dataclass
class EditOutcome:
    """Result of applying a single EditStep."""

    index: int
    ok: bool
    replacements: int = 0
    error: str | None = None


def _parse_edits(raw: Any) -> tuple[list[EditStep] | None, str | None]:
    """Parse and validate the ``edits`` argument."""
    if not isinstance(raw, list) or not raw:
        return None, "edits must be a non-empty list of {old, new, replace_all?}"
    steps: list[EditStep] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return None, f"edits[{i}] must be an object"
        old = item.get("old", "")
        new = item.get("new", "")
        if not isinstance(old, str) or not isinstance(new, str):
            return None, f"edits[{i}].old and .new must be strings"
        if old == "":
            return None, f"edits[{i}].old is empty; provide exact text to find"
        steps.append(
            EditStep(
                old=old,
                new=new,
                replace_all=bool(item.get("replace_all", False)),
            )
        )
    return steps, None


def _apply_one(
    content: str, step: EditStep, idx: int
) -> tuple[str | None, EditOutcome]:
    """Apply one EditStep to in-memory content. Returns (new_content, outcome)."""
    count = content.count(step.old)
    if count == 0:
        return None, EditOutcome(
            index=idx,
            ok=False,
            error=(
                "'old' not found in file after prior edits. "
                "An earlier edit may have rewritten this text - re-read the file."
            ),
        )
    if count > 1 and not step.replace_all:
        return None, EditOutcome(
            index=idx,
            ok=False,
            error=(
                f"'old' matches {count} locations; pass replace_all=true "
                "or add more surrounding context to make it unique."
            ),
        )
    if step.replace_all:
        new_content = content.replace(step.old, step.new)
        replaced = count
    else:
        new_content = content.replace(step.old, step.new, 1)
        replaced = 1
    return new_content, EditOutcome(index=idx, ok=True, replacements=replaced)


def _format_success(path: Path, outcomes: list[EditOutcome]) -> str:
    total = len(outcomes)
    reps = ", ".join(str(o.replacements) for o in outcomes)
    return f"Edited {path}\n  {total}/{total} edits applied\n  replacements: {reps}"


def _format_failure(outcomes: list[EditOutcome], total: int, failed_at: int) -> str:
    lines = [f"multi_edit failed: edit[{failed_at}] did not apply (file unchanged)"]
    for o in outcomes:
        if o.ok:
            lines.append(f"  edit[{o.index}] ok: {o.replacements} replacement(s)")
        else:
            lines.append(f"  edit[{o.index}] ERROR: {o.error}")
    skipped = total - len(outcomes)
    if skipped > 0:
        lines.append(f"  {skipped} later edit(s) skipped")
    return "\n".join(lines)


@register_builtin("multi_edit")
class MultiEditTool(BaseTool):
    """Apply an ordered list of search/replace edits to one file atomically.

    All edits are applied sequentially to an in-memory copy. The file on disk
    is only written once every edit has succeeded. On any failure the file is
    left untouched and the tool reports which edit failed.
    """

    needs_context = True
    require_manual_read = True

    @property
    def tool_name(self) -> str:
        return "multi_edit"

    @property
    def description(self) -> str:
        return (
            "Apply multiple search/replace edits to one file atomically "
            "(path, edits=[{old,new,replace_all?},...]). Use info(multi_edit) first."
        )

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        context = kwargs.get("context")
        path = args.get("path", "")
        if not path:
            return ToolResult(
                error="No path provided. Usage: multi_edit(path=..., edits=[...])"
            )

        steps, parse_err = _parse_edits(args.get("edits"))
        if parse_err:
            return ToolResult(error=parse_err)
        assert steps is not None

        file_path = resolve_tool_path(path, context)

        # Reuse edit tool's guard stack (binary / path_guard / read-before-write).
        guard_host = EditTool()
        guard = guard_host._check_guards(file_path, context)
        if guard:
            return guard

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")
        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
            original = content

            outcomes: list[EditOutcome] = []
            for i, step in enumerate(steps):
                new_content, outcome = _apply_one(content, step, i)
                outcomes.append(outcome)
                if not outcome.ok:
                    return ToolResult(
                        error=_format_failure(outcomes, len(steps), failed_at=i)
                    )
                assert new_content is not None
                content = new_content

            if content == original:
                return ToolResult(
                    output="No changes made (all edits produced identical content)",
                    exit_code=0,
                )

            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)

            guard_host._update_read_state(file_path, context)
            logger.debug(
                "multi_edit applied",
                file_path=str(file_path),
                edits=len(steps),
            )
            return ToolResult(output=_format_success(file_path, outcomes), exit_code=0)

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("multi_edit failed", error=str(e))
            return ToolResult(error=str(e))

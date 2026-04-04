"""
Read tool - read file contents (text and images).
"""

import base64
import os
import time
from pathlib import Path
from typing import Any

import aiofiles

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.llm.message import ImagePart, TextPart
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
)
from kohakuterrarium.utils.file_guard import is_binary_file
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("read")
class ReadTool(BaseTool):
    """
    Tool for reading file contents.

    Supports reading entire files or specific line ranges.
    """

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "Read file contents: text, images, PDFs (required before write/edit)"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        """Read file contents."""
        context = kwargs.get("context")

        path = args.get("path", "")
        if not path:
            return ToolResult(error="No path provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        # Image files: return as multimodal content
        if _is_image_file(file_path):
            return await self._read_image(file_path, path)

        # Binary file guard (non-image binaries)
        if is_binary_file(file_path):
            return ToolResult(
                error=f"Binary file detected ({file_path.suffix}). "
                "Use bash with xxd, file, or other tools to inspect binary files."
            )

        # Path boundary guard
        if context and context.path_guard:
            msg = context.path_guard.check(str(file_path))
            if msg:
                return ToolResult(error=msg)

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        # Get optional parameters
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 0))

        # Configurable output truncation
        max_output_bytes = int(self.config.extra.get("max_output_bytes", 200000))

        try:
            async with aiofiles.open(
                file_path, encoding="utf-8", errors="replace"
            ) as f:
                content = await f.read()
            lines = content.splitlines(keepends=True)

            total_lines = len(lines)

            # Apply offset and limit
            if offset > 0:
                lines = lines[offset:]
            if limit > 0:
                lines = lines[:limit]

            # Format with line numbers
            output_lines = []
            start_line = offset + 1
            for i, line in enumerate(lines):
                line_num = start_line + i
                # Remove trailing newline for cleaner output
                line_content = line.rstrip("\n\r")
                # Truncate individual long lines
                if len(line_content) > 2000:
                    total_chars = len(line_content)
                    line_content = (
                        line_content[:2000]
                        + f" ... (line truncated, {total_chars} chars)"
                    )
                output_lines.append(f"{line_num:6}→{line_content}")

            output = "\n".join(output_lines)

            # Add truncation notice if applicable
            if limit > 0 and offset + limit < total_lines:
                output += f"\n\n... (showing lines {offset + 1}-{offset + len(lines)} of {total_lines})"

            # Truncate total output if it exceeds max bytes
            if max_output_bytes > 0 and len(output.encode("utf-8")) > max_output_bytes:
                output = output.encode("utf-8")[:max_output_bytes].decode(
                    "utf-8", errors="ignore"
                )
                output += f"\n\n[Output truncated at {max_output_bytes} bytes. Use offset/limit to read specific sections.]"

            logger.debug(
                "File read",
                file_path=str(file_path),
                lines_read=len(lines),
            )

            # Record read to file_read_state
            if context and context.file_read_state:
                mtime_ns = os.stat(file_path).st_mtime_ns
                partial = bool(args.get("offset") or args.get("limit"))
                context.file_read_state.record_read(
                    str(file_path), mtime_ns, partial, time.time()
                )

            return ToolResult(output=output, exit_code=0)

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Read failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# read

Read file contents with optional line range.

## Supported file types

- **Text files**: source code, config, markdown, etc. (returned with line numbers)
- **Images**: png, jpg, gif, webp, svg, bmp, tiff, heif, avif (returned as visual input)
- **PDFs**: returned as text content + page images (coming soon)
- **Binary files**: other binary formats are rejected with a helpful message

## SAFETY

- You MUST read files before writing or editing them. The write and edit tools
  will error if you haven't read the file first.
- Lines longer than 2000 characters are truncated.
- Total output is capped at 200KB. Use offset/limit for large files.
- Images are capped at 20MB.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | string | Path to file (required) |
| offset | integer | Line to start from (0-based, default: 0, text files only) |
| limit | integer | Max lines to read (default: all, text files only) |

## Behavior

- **Text files**: returns contents with line numbers (`     1→content`).
  Use offset/limit for specific ranges.
- **Images**: returns the image for visual inspection. The model can see
  and describe the image content.
- **PDFs**: returns extracted text + rendered page images (coming soon).

## TIPS

- Use `glob` first to find files by pattern, then `read` to examine them.
- Use `grep` to locate relevant lines, then `read` with offset/limit to
  examine context.
- For large files, read in chunks with offset/limit.
- For images, just `read(path="screenshot.png")` to see the content.
"""

    async def _read_image(self, file_path: Path, original_path: str) -> ToolResult:
        """Read an image file and return as multimodal content."""
        if not file_path.exists():
            return ToolResult(error=f"File not found: {original_path}")

        max_image_bytes = 20 * 1024 * 1024  # 20 MB limit
        file_size = file_path.stat().st_size

        if file_size > max_image_bytes:
            return ToolResult(
                error=f"Image too large ({file_size // 1024}KB). "
                f"Max: {max_image_bytes // (1024 * 1024)}MB."
            )

        suffix = file_path.suffix.lower()
        mime = _IMAGE_MIME.get(suffix, "image/png")

        try:
            async with aiofiles.open(file_path, "rb") as f:
                data = await f.read()
            b64 = base64.b64encode(data).decode("ascii")
            data_url = f"data:{mime};base64,{b64}"

            logger.info(
                "Image read",
                file_path=str(file_path),
                size_kb=len(data) // 1024,
                mime=mime,
            )

            return ToolResult(
                output=[
                    TextPart(
                        text=f"Image: {original_path} ({len(data) // 1024}KB, {mime})"
                    ),
                    ImagePart(
                        url=data_url,
                        detail="auto",
                        source_type="file",
                        source_name=file_path.name,
                    ),
                ],
                exit_code=0,
            )
        except Exception as e:
            return ToolResult(error=f"Failed to read image: {e}")


# Image extensions and MIME types
_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".ico",
    ".svg",
    ".heif",
    ".heic",
    ".avif",
}

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".heif": "image/heif",
    ".heic": "image/heic",
    ".avif": "image/avif",
}


def _is_image_file(path: Path) -> bool:
    """Check if a file is a supported image format."""
    return path.suffix.lower() in _IMAGE_EXTENSIONS

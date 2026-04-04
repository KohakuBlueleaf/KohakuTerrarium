"""
Web search tool: search the web and return structured results.

Uses duckduckgo-search (optional dep, no API key needed).
"""

from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode, ToolResult
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

MAX_RESULTS = 10

_HAS_DDG = False
_DDG_MODULE = ""
try:
    from ddgs import DDGS  # noqa: F401

    _HAS_DDG = True
    _DDG_MODULE = "ddgs"
except ImportError:
    try:
        from duckduckgo_search import DDGS  # noqa: F401

        _HAS_DDG = True
        _DDG_MODULE = "duckduckgo_search"
    except ImportError:
        pass


@register_builtin("web_search")
class WebSearchTool(BaseTool):
    """Search the web and return structured results.

    Uses DuckDuckGo (no API key required).
    Install: pip install duckduckgo-search
    """

    @property
    def tool_name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web and return results with titles, URLs, and snippets"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(error="No query provided. Usage: web_search(query='...')")

        if not _HAS_DDG:
            return ToolResult(
                error="Web search not available. Install: pip install ddgs"
            )

        max_results = int(args.get("max_results", MAX_RESULTS))
        region = args.get("region", "")

        try:
            results = await _search_ddg(query, max_results, region)
        except Exception as e:
            return ToolResult(error=f"Search failed: {e}")

        if not results:
            return ToolResult(output="No results found.", exit_code=0)

        # Format results for LLM
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("href", r.get("url", ""))
            snippet = r.get("body", r.get("snippet", ""))
            lines.append(f"## {i}. {title}")
            lines.append(f"URL: {url}")
            if snippet:
                lines.append(snippet)
            lines.append("")

        logger.info("Web search complete", query=query[:50], results=len(results))
        return ToolResult(output="\n".join(lines), exit_code=0)

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# web_search

Search the web and return results with titles, URLs, and snippets.
Uses DuckDuckGo (no API key required).

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| query | string | Search query (required) |
| max_results | int | Max results to return (default: 10) |
| region | string | Region code (optional, e.g., "us-en") |

## Example

```
web_search(query="python asyncio tutorial")
web_search(query="KohakuTerrarium github", max_results=5)
```

## Output

Structured list with title, URL, and snippet for each result.
"""


async def _search_ddg(query: str, max_results: int, region: str) -> list[dict]:
    """Run DuckDuckGo search (sync library, run in executor)."""
    import asyncio

    if _DDG_MODULE == "ddgs":
        from ddgs import DDGS
    else:
        from duckduckgo_search import DDGS

    def _do_search():
        kwargs: dict[str, Any] = {"max_results": max_results}
        if region:
            kwargs["region"] = region
        with DDGS() as ddgs:
            return list(ddgs.text(query, **kwargs))

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_search)

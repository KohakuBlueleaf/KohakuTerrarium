"""HTTP tool - make HTTP requests."""

import json
from typing import Any

import httpx

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode, ToolResult
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

# Max response body size to return to the model
MAX_RESPONSE_SIZE = 50000


@register_builtin("http")
class HttpTool(BaseTool):
    """Make HTTP requests to APIs and web services."""

    @property
    def tool_name(self) -> str:
        return "http"

    @property
    def description(self) -> str:
        return "Make HTTP requests (GET, POST, etc.)"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute HTTP request."""
        method = args.get("method", "GET").upper()
        url = args.get("url", "")

        if not url:
            return ToolResult(error="URL is required")

        # Parse headers
        headers: dict[str, str] = {}
        raw_headers = args.get("headers", "")
        if raw_headers:
            try:
                headers = (
                    json.loads(raw_headers)
                    if isinstance(raw_headers, str)
                    else raw_headers
                )
            except json.JSONDecodeError:
                return ToolResult(error="Invalid headers JSON")

        # Get body
        body = args.get("body", "") or args.get("data", "")

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body if body else None,
                )

            # Format response
            response_body = response.text[:MAX_RESPONSE_SIZE]
            truncated = len(response.text) > MAX_RESPONSE_SIZE

            output_parts = [
                f"Status: {response.status_code}",
                f"Content-Type: {response.headers.get('content-type', 'unknown')}",
            ]

            if truncated:
                output_parts.append(
                    f"(Response truncated from {len(response.text)}"
                    f" to {MAX_RESPONSE_SIZE} chars)"
                )

            output_parts.append(f"\n{response_body}")

            logger.debug(
                "HTTP request completed",
                method=method,
                url=url,
                status=response.status_code,
            )

            return ToolResult(
                output="\n".join(output_parts),
                exit_code=0 if response.status_code < 400 else 1,
                metadata={"status_code": response.status_code},
            )

        except httpx.TimeoutException:
            return ToolResult(error=f"Request timed out: {url}")
        except httpx.RequestError as e:
            return ToolResult(error=f"Request failed: {e}")

    def get_full_documentation(self) -> str:
        return """# http

Make HTTP requests to APIs and web services.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| method | @@arg | HTTP method: GET, POST, PUT, DELETE, PATCH (default: GET) |
| url | @@arg | URL to request (required) |
| headers | @@arg | JSON object of headers |
| body | content | Request body |

## Examples

GET request:
```
[/http]
@@method=GET
@@url=https://api.example.com/status
[http/]
```

POST with JSON:
```
[/http]
@@method=POST
@@url=https://api.example.com/data
@@headers={"Content-Type": "application/json"}
{"key": "value"}
[http/]
```

## Output

Returns status code, content-type, and response body (truncated to 50KB).

## Mode

BACKGROUND - runs asynchronously, does not block other tools.
"""

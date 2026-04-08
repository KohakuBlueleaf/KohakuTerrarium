"""Plugin protocol and base class for KohakuTerrarium.

Two extension patterns:

**Pre/post hooks** — wrap existing methods via decoration at init time.
The manager runs pre_* hooks before the real call (can transform input
or block), then the real call, then post_* hooks (can transform output).
All plugins run linearly by priority, not nested.

**Callbacks** — fire-and-forget notifications with data.

Error handling:
  - PluginBlockError in pre_tool_execute: blocks execution, becomes tool result
  - Regular Exception: logged, plugin skipped, execution continues
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PluginBlockError(Exception):
    """Raised by a plugin to block tool/sub-agent execution.

    The error message is returned to the model as the tool result.
    Only meaningful in ``pre_tool_execute`` and ``pre_subagent_run``.
    """


@dataclass
class PluginContext:
    """Context provided to plugins on load."""

    agent_name: str = ""
    working_dir: Path = field(default_factory=Path.cwd)
    session_id: str = ""
    model: str = ""
    _agent: Any = field(default=None, repr=False)
    _plugin_name: str = field(default="", repr=False)

    def switch_model(self, name: str) -> str:
        """Switch the LLM model. Returns resolved model name."""
        if self._agent and hasattr(self._agent, "switch_model"):
            return self._agent.switch_model(name)
        return ""

    def inject_event(self, event: Any) -> None:
        """Push a trigger event into the agent's event queue."""
        if self._agent and hasattr(self._agent, "controller"):
            self._agent.controller.push_event_sync(event)

    def get_state(self, key: str) -> Any:
        """Read plugin-scoped state from session store."""
        if (
            self._agent
            and hasattr(self._agent, "session_store")
            and self._agent.session_store
        ):
            return self._agent.session_store.state.get(
                f"plugin:{self._plugin_name}:{key}"
            )
        return None

    def set_state(self, key: str, value: Any) -> None:
        """Write plugin-scoped state to session store."""
        if (
            self._agent
            and hasattr(self._agent, "session_store")
            and self._agent.session_store
        ):
            self._agent.session_store.state[f"plugin:{self._plugin_name}:{key}"] = value


class BasePlugin:
    """Base class for plugins. Override only what you need.

    Pre/post hooks run linearly by priority around real methods:
        pre_xxx  → real method → post_xxx

    Return None from pre/post to keep the value unchanged.
    Return a value to replace it for the next plugin in the chain.
    """

    name: str = "unnamed"
    priority: int = 50  # Lower = runs first in pre, last in post

    # ── Lifecycle ──

    async def on_load(self, context: PluginContext) -> None:
        """Called when plugin is loaded."""

    async def on_unload(self) -> None:
        """Called when agent shuts down."""

    # ── LLM hooks ──

    async def pre_llm_call(self, messages: list[dict], **kwargs) -> list[dict] | None:
        """Before LLM call. Return modified messages or None.

        kwargs: model (str), tools (list | None, native mode only)
        """
        return None

    async def post_llm_call(
        self, messages: list[dict], response: str, usage: dict, **kwargs
    ) -> None:
        """After LLM call. Observation — cannot modify response.

        kwargs: model (str)
        """

    # ── Tool hooks ──

    async def pre_tool_execute(self, args: dict, **kwargs) -> dict | None:
        """Before tool execution. Return modified args or None.

        kwargs: tool_name (str), job_id (str)
        Raise PluginBlockError to prevent execution.
        """
        return None

    async def post_tool_execute(self, result: Any, **kwargs) -> Any | None:
        """After tool execution. Return modified result or None.

        kwargs: tool_name (str), job_id (str), args (dict)
        """
        return None

    # ── Sub-agent hooks ──

    async def pre_subagent_run(self, task: str, **kwargs) -> str | None:
        """Before sub-agent run. Return modified task or None.

        kwargs: name (str), job_id (str), is_background (bool)
        Raise PluginBlockError to prevent execution.
        """
        return None

    async def post_subagent_run(self, result: Any, **kwargs) -> Any | None:
        """After sub-agent run. Return modified result or None.

        kwargs: name (str), job_id (str)
        """
        return None

    # ── Callbacks (fire-and-forget) ──

    async def on_agent_start(self) -> None:
        """Called after agent.start() completes."""

    async def on_agent_stop(self) -> None:
        """Called before agent.stop() begins."""

    async def on_event(self, event: Any) -> None:
        """Called on incoming trigger event. Observation only."""

    async def on_interrupt(self) -> None:
        """Called when user interrupts the agent."""

    async def on_task_promoted(self, job_id: str, tool_name: str) -> None:
        """Called when a direct task is promoted to background."""

    async def on_compact_start(self, context_length: int) -> None:
        """Called before context compaction."""

    async def on_compact_end(self, summary: str, messages_removed: int) -> None:
        """Called after context compaction."""

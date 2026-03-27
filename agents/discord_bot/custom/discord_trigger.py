"""
Discord-specific triggers for group chat bot.

Provides ping detection and idle/exploration triggers.
"""

import asyncio
from typing import Any

from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.modules.trigger import BaseTrigger
from kohakuterrarium.utils.logging import get_logger

from discord_client import get_client

logger = get_logger("kohakuterrarium.custom.discord_trigger")


class DiscordPingTrigger(BaseTrigger):
    """
    Trigger that fires when bot is mentioned in Discord.

    This trigger monitors the message context and fires when the bot
    is directly mentioned (@bot), forcing a reply.
    """

    def __init__(
        self,
        client: Any = None,
        client_name: str = "default",
        prompt: str | None = None,
        **options: Any,
    ):
        """
        Initialize ping trigger.

        Args:
            client: Discord client to monitor (optional, will look up from registry)
            client_name: Name to look up in shared client registry
            prompt: Prompt to use when ping is detected
            **options: Additional options
        """
        super().__init__(prompt=prompt, **options)
        self.client = client
        self.client_name = client_name
        self._pending_pings: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def set_client(self, client: Any) -> None:
        """Set Discord client (for delayed initialization)."""
        self.client = client

    def _ensure_client(self) -> Any:
        """Get client, looking up from registry if needed."""
        if self.client is None:
            self.client = get_client(self.client_name)
        return self.client

    def _on_context_update(self, context: dict[str, Any]) -> None:
        """
        Check context for mentions.

        Called by controller when new input arrives. If the message
        mentions the bot, queue a ping event.
        """
        # Check if this is a Discord message with mention
        if context.get("source") != "discord":
            return

        # Skip if this is already a ping event (avoid re-triggering loop)
        if context.get("force_reply"):
            return

        is_mention = context.get("is_mention", False)
        if is_mention:
            # Queue the ping for processing
            try:
                self._pending_pings.put_nowait(context)
            except asyncio.QueueFull:
                pass  # Skip if queue is full

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Wait for a ping event."""
        if not self._running:
            return None

        try:
            # Wait for ping with timeout
            ping_context = await asyncio.wait_for(
                self._pending_pings.get(),
                timeout=1.0,
            )

            return TriggerEvent(
                type="ping",
                content=self.prompt or "You were mentioned. Reply to this message.",
                context={
                    **ping_context,
                    "force_reply": True,
                },
                prompt_override=self.prompt,
                stackable=False,  # Ping events need immediate attention
            )
        except asyncio.TimeoutError:
            return None


class DiscordIdleTrigger(BaseTrigger):
    """
    Trigger that fires after a period of inactivity.

    Used for exploration/topic-starting behavior. The trigger
    can be configured to fire randomly within a time range.
    """

    def __init__(
        self,
        min_idle_seconds: float = 1800.0,  # 30 minutes
        max_idle_seconds: float = 7200.0,  # 2 hours
        exploration_chance: float = 0.3,  # 30% chance to actually explore
        prompt: str | None = None,
        **options: Any,
    ):
        """
        Initialize idle trigger.

        Args:
            min_idle_seconds: Minimum idle time before trigger can fire
            max_idle_seconds: Maximum idle time (random between min and max)
            exploration_chance: Probability of actually exploring (0.0 - 1.0)
            prompt: Prompt for exploration behavior
            **options: Additional options
        """
        super().__init__(prompt=prompt, **options)
        self.min_idle_seconds = min_idle_seconds
        self.max_idle_seconds = max_idle_seconds
        self.exploration_chance = exploration_chance
        self._last_activity = asyncio.get_event_loop().time()
        self._current_threshold: float | None = None
        self._check_count = 0  # For logging every N checks

    def _on_context_update(self, context: dict[str, Any]) -> None:
        """Reset idle timer on any activity."""
        import random

        self._last_activity = asyncio.get_event_loop().time()
        # Set new random threshold for next idle check
        self._current_threshold = random.uniform(
            self.min_idle_seconds,
            self.max_idle_seconds,
        )
        logger.debug(
            "Idle timer reset (activity detected)",
            extra={"new_threshold": int(self._current_threshold)},
        )

    async def _on_start(self) -> None:
        """Initialize threshold on start."""
        import random

        self._last_activity = asyncio.get_event_loop().time()
        self._current_threshold = random.uniform(
            self.min_idle_seconds,
            self.max_idle_seconds,
        )
        logger.info(
            "Idle trigger started",
            extra={
                "min_idle": int(self.min_idle_seconds),
                "max_idle": int(self.max_idle_seconds),
                "exploration_chance": f"{self.exploration_chance:.0%}",
                "initial_threshold": int(self._current_threshold),
            },
        )

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Wait for idle timeout."""
        import random

        if not self._running:
            return None

        # Check every 30 seconds
        await asyncio.sleep(30.0)

        if not self._running:
            return None

        current_time = asyncio.get_event_loop().time()
        idle_duration = current_time - self._last_activity

        # Log idle status every 10 checks (~5 minutes)
        self._check_count += 1
        if self._check_count >= 10:
            self._check_count = 0
            logger.debug(
                "Idle status",
                extra={
                    "idle_minutes": int(idle_duration / 60),
                    "threshold_minutes": (
                        int(self._current_threshold / 60)
                        if self._current_threshold
                        else None
                    ),
                },
            )

        # Check if we've been idle long enough
        if self._current_threshold and idle_duration >= self._current_threshold:
            # Roll for exploration chance
            roll = random.random()
            logger.info(
                "Idle threshold reached, rolling for exploration",
                extra={
                    "idle_seconds": int(idle_duration),
                    "threshold": int(self._current_threshold),
                    "roll": f"{roll:.2f}",
                    "chance": f"{self.exploration_chance:.2f}",
                    "will_trigger": roll < self.exploration_chance,
                },
            )

            if roll < self.exploration_chance:
                # Reset timer
                self._last_activity = current_time
                self._current_threshold = random.uniform(
                    self.min_idle_seconds,
                    self.max_idle_seconds,
                )

                logger.info("Idle trigger fired - starting exploration")

                return TriggerEvent(
                    type="idle",
                    content=self.prompt
                    or "Chat has been quiet. Consider starting a new topic.",
                    context={
                        "idle_duration": idle_duration,
                        "exploration": True,
                        "force_reply": False,  # Not forced, just suggested
                    },
                    prompt_override=self.prompt,
                    stackable=True,
                )
            else:
                # Didn't explore this time, reset threshold
                new_threshold = random.uniform(
                    self.min_idle_seconds,
                    self.max_idle_seconds,
                )
                logger.debug(
                    "Exploration skipped, new threshold set",
                    extra={"new_threshold": int(new_threshold)},
                )
                self._current_threshold = new_threshold

        return None


class DiscordActivityMonitor(BaseTrigger):
    """
    Monitors Discord activity and provides context to other triggers.

    This is a composite trigger that helps coordinate between
    the input module and specialized triggers.
    """

    def __init__(
        self,
        client: Any = None,
        client_name: str = "default",
        prompt: str | None = None,
        **options: Any,
    ):
        """
        Initialize activity monitor.

        Args:
            client: Discord client to monitor (optional, will look up from registry)
            client_name: Name to look up in shared client registry
            prompt: Default prompt (unused)
            **options: Additional options
        """
        super().__init__(prompt=prompt, **options)
        self.client = client
        self.client_name = client_name
        self._activity_callbacks: list[callable] = []

    def set_client(self, client: Any) -> None:
        """Set Discord client."""
        self.client = client

    def _ensure_client(self) -> Any:
        """Get client, looking up from registry if needed."""
        if self.client is None:
            self.client = get_client(self.client_name)
        return self.client

    def add_activity_callback(self, callback: callable) -> None:
        """Add callback for activity updates."""
        self._activity_callbacks.append(callback)

    def _on_context_update(self, context: dict[str, Any]) -> None:
        """Propagate activity to callbacks."""
        for callback in self._activity_callbacks:
            try:
                callback(context)
            except Exception:
                pass  # Don't let callback errors break the monitor

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Activity monitor doesn't produce events directly."""
        # Just sleep and check running state
        await asyncio.sleep(1.0)
        return None

"""
Termination conditions for agent execution.

Configurable conditions that stop the agent loop: max turns, max tokens,
max duration, idle timeout, and keyword detection.
"""

import time
from dataclasses import dataclass, field

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TerminationConfig:
    """
    Configuration for termination conditions.

    All conditions are optional. If multiple are set, ANY triggered condition stops the agent.
    """

    max_turns: int = 0  # Max controller turns (0 = unlimited)
    max_tokens: int = 0  # Total token budget (0 = unlimited) - reserved for future
    max_duration: float = 0  # Max duration in seconds (0 = unlimited)
    idle_timeout: float = 0  # No events for N seconds (0 = unlimited)
    keywords: list[str] = field(default_factory=list)  # Stop on output keyword


class TerminationChecker:
    """
    Checks termination conditions during agent execution.

    Usage:
        checker = TerminationChecker(config)
        checker.start()

        # In event loop:
        checker.record_turn()
        checker.record_activity()

        if checker.should_terminate(last_output="TASK_COMPLETE"):
            break
    """

    def __init__(self, config: TerminationConfig):
        self.config = config
        self._turn_count: int = 0
        self._start_time: float = 0.0
        self._last_activity: float = 0.0
        self._terminated: bool = False
        self._reason: str = ""

    def start(self) -> None:
        """Start tracking. Call at beginning of agent run."""
        self._start_time = time.monotonic()
        self._last_activity = self._start_time
        self._turn_count = 0
        self._terminated = False
        self._reason = ""
        logger.debug("Termination checker started", config=str(self.config))

    def record_turn(self) -> None:
        """Record a controller turn."""
        self._turn_count += 1
        self._last_activity = time.monotonic()

    def record_activity(self) -> None:
        """Record any activity (resets idle timer)."""
        self._last_activity = time.monotonic()

    def should_terminate(self, last_output: str = "") -> bool:
        """
        Check if any termination condition is met.

        Args:
            last_output: The last output text from the controller (for keyword check)

        Returns:
            True if agent should terminate
        """
        if self._terminated:
            return True

        now = time.monotonic()

        # Check max turns
        if self.config.max_turns > 0 and self._turn_count >= self.config.max_turns:
            self._terminated = True
            self._reason = f"Max turns reached ({self._turn_count})"
            logger.info("Termination: %s", self._reason)
            return True

        # Check max duration
        if self.config.max_duration > 0:
            elapsed = now - self._start_time
            if elapsed >= self.config.max_duration:
                self._terminated = True
                self._reason = f"Max duration reached ({elapsed:.1f}s)"
                logger.info("Termination: %s", self._reason)
                return True

        # Check idle timeout
        if self.config.idle_timeout > 0:
            idle_time = now - self._last_activity
            if idle_time >= self.config.idle_timeout:
                self._terminated = True
                self._reason = f"Idle timeout ({idle_time:.1f}s)"
                logger.info("Termination: %s", self._reason)
                return True

        # Check keywords in output
        if self.config.keywords and last_output:
            for keyword in self.config.keywords:
                if keyword in last_output:
                    self._terminated = True
                    self._reason = f"Keyword detected: {keyword}"
                    logger.info("Termination: %s", self._reason)
                    return True

        return False

    @property
    def reason(self) -> str:
        """Get termination reason (empty if not terminated)."""
        return self._reason

    @property
    def turn_count(self) -> int:
        """Get current turn count."""
        return self._turn_count

    @property
    def elapsed(self) -> float:
        """Get elapsed time since start."""
        if self._start_time == 0:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def is_active(self) -> bool:
        """Check if any termination condition is configured."""
        c = self.config
        return bool(
            c.max_turns
            or c.max_tokens
            or c.max_duration
            or c.idle_timeout
            or c.keywords
        )

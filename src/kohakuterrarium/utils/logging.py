"""
Custom logging module with colored output and comprehensive formatting.

Format: [HH:MM:SS] [module.name] [LEVEL] message
Colors: DEBUG=gray, INFO=green, WARNING=yellow, ERROR=red
"""

import logging
import sys
from typing import Any

# ANSI color codes
COLORS = {
    "DEBUG": "\033[90m",  # Gray
    "INFO": "\033[92m",  # Green
    "WARNING": "\033[93m",  # Yellow
    "ERROR": "\033[91m",  # Red
    "CRITICAL": "\033[95m",  # Magenta
    "RESET": "\033[0m",
}


# Check if terminal supports colors
def _supports_color() -> bool:
    """Check if the terminal supports ANSI colors."""
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    # Windows 10+ supports ANSI, but need to enable it
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # Enable ANSI escape sequences on Windows
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


SUPPORTS_COLOR = _supports_color()


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors and structured format."""

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color and SUPPORTS_COLOR

    def format(self, record: logging.LogRecord) -> str:
        # Time format: HH:MM:SS
        time_str = self.formatTime(record, "%H:%M:%S")

        # Module name: truncate if too long
        module = record.name
        if len(module) > 25:
            module = "..." + module[-22:]

        # Level name: pad to consistent width
        level = record.levelname

        # Base message
        message = record.getMessage()

        # Add any extra fields (passed via logger.info("msg", extra_field=value))
        extras = []
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
            ):
                extras.append(f"{key}={value}")

        if extras:
            message = f"{message} [{', '.join(extras)}]"

        # Format with colors
        if self.use_color:
            color = COLORS.get(level, "")
            reset = COLORS["RESET"]
            return f"{color}[{time_str}] [{module}] [{level}] {message}{reset}"
        else:
            return f"[{time_str}] [{module}] [{level}] {message}"

    def formatException(self, ei: Any) -> str:
        """Format exception with color if enabled."""
        result = super().formatException(ei)
        if self.use_color:
            return f"{COLORS['ERROR']}{result}{COLORS['RESET']}"
        return result


class KTLogger(logging.Logger):
    """Extended logger with extra field support."""

    def _log(
        self,
        level: int,
        msg: object,
        args: tuple[Any, ...],
        exc_info: Any = None,
        extra: dict[str, Any] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        **kwargs: Any,
    ) -> None:
        # Merge kwargs into extra for convenience
        # This allows: logger.info("message", field1=value1, field2=value2)
        if kwargs:
            if extra is None:
                extra = {}
            extra.update(kwargs)
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel + 1)


# Set custom logger class
logging.setLoggerClass(KTLogger)

# Global handler to avoid duplicates
_handler: logging.Handler | None = None


def get_logger(name: str, level: int | str = logging.DEBUG) -> logging.Logger:
    """
    Get a configured logger for a module.

    Args:
        name: Module name (typically __name__)
        level: Logging level (default: DEBUG)

    Returns:
        Configured Logger instance

    Usage:
        from kohakuterrarium.utils.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Starting process", task_id="123")
        logger.debug("Debug info")
        logger.warning("Something unusual")
        logger.error("Something went wrong")
    """
    global _handler

    logger = logging.getLogger(name)

    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.DEBUG)

    logger.setLevel(level)

    # Only add handler once (to root logger)
    if _handler is None:
        _handler = logging.StreamHandler(sys.stderr)
        _handler.setFormatter(ColoredFormatter(use_color=True))
        _handler.setLevel(logging.DEBUG)

        # Add to root logger for kohakuterrarium
        root_logger = logging.getLogger("kohakuterrarium")
        root_logger.addHandler(_handler)
        root_logger.setLevel(logging.DEBUG)
        # Prevent propagation to root logger (avoid duplicate logs)
        root_logger.propagate = False

    return logger


def set_level(level: int | str) -> None:
    """
    Set global logging level for all kohakuterrarium loggers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, or int)
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.DEBUG)

    root_logger = logging.getLogger("kohakuterrarium")
    root_logger.setLevel(level)
    if _handler:
        _handler.setLevel(level)


def disable_colors() -> None:
    """Disable colored output (useful for logging to files)."""
    if _handler:
        _handler.setFormatter(ColoredFormatter(use_color=False))

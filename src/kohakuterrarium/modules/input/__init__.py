"""
Input module - receive external input and produce TriggerEvents.

Exports:
- InputModule: Protocol for input modules
- BaseInputModule: Base class for input modules
- CLIInput: Terminal input implementation
- ASRModule, ASRConfig, ASRResult: ASR base classes
- WhisperASR, WhisperConfig: Whisper-based ASR (requires RealtimeSTT)
"""

from kohakuterrarium.modules.input.asr import ASRConfig, ASRModule, ASRResult
from kohakuterrarium.modules.input.base import BaseInputModule, InputModule
from kohakuterrarium.modules.input.cli import CLIInput, NonBlockingCLIInput

__all__ = [
    # Protocol and base
    "InputModule",
    "BaseInputModule",
    # CLI
    "CLIInput",
    "NonBlockingCLIInput",
    # ASR base
    "ASRModule",
    "ASRConfig",
    "ASRResult",
]

# Optional: WhisperASR (requires RealtimeSTT)
try:
    from kohakuterrarium.modules.input.whisper import (
        WhisperASR,
        WhisperConfig,
        create_whisper_asr,
    )

    __all__.extend(["WhisperASR", "WhisperConfig", "create_whisper_asr"])
except ImportError:
    pass  # RealtimeSTT not installed

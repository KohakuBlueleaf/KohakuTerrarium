"""
Whisper-based ASR module using RealtimeSTT.

Provides real-time speech-to-text with:
- Continuous microphone recording
- Voice Activity Detection (WebRTC + Silero VAD)
- Faster-Whisper transcription

Requires: pip install RealtimeSTT
"""

import asyncio
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from kohakuterrarium.modules.input.asr import ASRConfig, ASRModule, ASRResult
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WhisperConfig(ASRConfig):
    """
    Configuration for Whisper ASR.

    Attributes:
        model: Whisper model size ('tiny', 'base', 'small', 'medium', 'large-v2')
        device: 'cuda' or 'cpu'
        compute_type: Compute type for faster-whisper ('float16', 'int8', etc.)
        silero_sensitivity: Silero VAD sensitivity (0.0-1.0)
        webrtc_sensitivity: WebRTC VAD sensitivity (0-3)
        post_speech_silence: Silence duration to end utterance (seconds)
        realtime_preview: Enable real-time transcription preview
        realtime_model: Model for real-time preview ('tiny' recommended)
    """

    model: str = "base"
    device: str = "cuda"
    compute_type: str = "float16"
    silero_sensitivity: float = 0.6
    webrtc_sensitivity: int = 3
    post_speech_silence: float = 0.5
    realtime_preview: bool = False
    realtime_model: str = "tiny"


class WhisperASR(ASRModule):
    """
    Real-time Whisper ASR using RealtimeSTT.

    Uses continuous microphone recording with VAD-based segmentation.
    Audio is only sent to Whisper when speech is detected.

    Usage:
        asr = WhisperASR(WhisperConfig(model="base", device="cuda"))
        await asr.start()
        async for event in asr.listen():
            print(f"User said: {event.content}")
    """

    def __init__(self, config: WhisperConfig | None = None):
        """
        Initialize Whisper ASR.

        Args:
            config: Whisper configuration
        """
        super().__init__(config or WhisperConfig())
        self.whisper_config: WhisperConfig = self.config  # type: ignore

        self._recorder = None
        self._transcription_queue: Queue[ASRResult] = Queue()
        self._recording_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_realtime_text = ""

    async def _start_listening(self) -> None:
        """Start continuous audio recording with VAD."""
        try:
            from RealtimeSTT import AudioToTextRecorder
        except ImportError as e:
            raise ImportError(
                "RealtimeSTT not installed. Install with: pip install RealtimeSTT"
            ) from e

        # Build recorder configuration
        recorder_kwargs = self._build_recorder_kwargs()

        logger.info(
            "Starting Whisper ASR",
            model=self.whisper_config.model,
            device=self.whisper_config.device,
        )

        # Create recorder in a separate thread (it uses blocking I/O)
        self._stop_event.clear()
        self._recording_thread = threading.Thread(
            target=self._recording_loop,
            args=(AudioToTextRecorder, recorder_kwargs),
            daemon=True,
        )
        self._recording_thread.start()

    def _build_recorder_kwargs(self) -> dict[str, Any]:
        """Build kwargs for AudioToTextRecorder."""
        kwargs: dict[str, Any] = {
            # Model settings
            "model": self.whisper_config.model,
            "language": (
                self.whisper_config.language
                if self.whisper_config.language != "auto"
                else ""
            ),
            "device": self.whisper_config.device,
            "compute_type": self.whisper_config.compute_type,
            # VAD settings
            "silero_sensitivity": self.whisper_config.silero_sensitivity,
            "webrtc_sensitivity": self.whisper_config.webrtc_sensitivity,
            "post_speech_silence_duration": self.whisper_config.post_speech_silence,
            # Callbacks
            "on_recording_start": self._on_recording_start,
            "on_recording_stop": self._on_recording_stop,
        }

        # Real-time preview (optional)
        if self.whisper_config.realtime_preview:
            kwargs["enable_realtime_transcription"] = True
            kwargs["realtime_model_type"] = self.whisper_config.realtime_model
            kwargs["on_realtime_transcription_update"] = self._on_realtime_transcription

        return kwargs

    def _recording_loop(
        self,
        recorder_class: type,
        recorder_kwargs: dict[str, Any],
    ) -> None:
        """
        Main recording loop (runs in separate thread).

        Continuously listens for speech and puts transcriptions in queue.
        """
        try:
            logger.debug("Initializing AudioToTextRecorder...")
            recorder = recorder_class(**recorder_kwargs)
            self._recorder = recorder

            logger.info("Whisper ASR ready, listening for speech...")

            while not self._stop_event.is_set():
                try:
                    # This blocks until speech is detected and transcribed
                    text = recorder.text()

                    if text and text.strip():
                        result = ASRResult(
                            text=text.strip(),
                            language=self.whisper_config.language,
                            confidence=1.0,
                            is_final=True,
                        )
                        self._transcription_queue.put(result)
                        logger.debug("Transcription complete", text=text[:50])

                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error("Recording error", error=str(e))

        except Exception as e:
            logger.error("Recorder initialization failed", error=str(e))
        finally:
            if self._recorder:
                try:
                    self._recorder.shutdown()
                except Exception:
                    pass
                self._recorder = None

    def _on_recording_start(self) -> None:
        """Called when VAD detects speech start."""
        logger.debug("Speech detected, recording...")
        self._current_realtime_text = ""

    def _on_recording_stop(self) -> None:
        """Called when VAD detects speech end."""
        logger.debug("Speech ended, transcribing...")

    def _on_realtime_transcription(self, text: str) -> None:
        """Called during real-time transcription (preview)."""
        self._current_realtime_text = text
        logger.debug("Realtime preview", text=text[:30] if text else "")

    async def _stop_listening(self) -> None:
        """Stop audio recording."""
        self._stop_event.set()

        if self._recorder:
            try:
                self._recorder.shutdown()
            except Exception as e:
                logger.warning("Recorder shutdown error", error=str(e))
            self._recorder = None

        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=2.0)
            self._recording_thread = None

        logger.info("Whisper ASR stopped")

    async def _transcribe(self) -> ASRResult | None:
        """
        Get next transcription from queue.

        Blocks until speech is detected and transcribed.
        """
        # Poll the queue with timeout to allow checking stop condition
        while self._running:
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._transcription_queue.get(timeout=0.1),
                )
                return result
            except Empty:
                continue

        return None

    def get_realtime_text(self) -> str:
        """
        Get current real-time transcription preview.

        Only available if realtime_preview is enabled.
        """
        return self._current_realtime_text


# Factory function for config-based creation
def create_whisper_asr(options: dict[str, Any]) -> WhisperASR:
    """
    Create WhisperASR from config options.

    Args:
        options: Configuration dictionary

    Returns:
        Configured WhisperASR instance
    """
    config = WhisperConfig(
        language=options.get("language", "auto"),
        sample_rate=options.get("sample_rate", 16000),
        vad_enabled=options.get("vad_enabled", True),
        vad_threshold=options.get("vad_threshold", 0.5),
        min_speech_duration=options.get("min_speech_duration", 0.25),
        max_speech_duration=options.get("max_speech_duration", 30.0),
        silence_duration=options.get("silence_duration", 0.8),
        model=options.get("model", "base"),
        device=options.get("device", "cuda"),
        compute_type=options.get("compute_type", "float16"),
        silero_sensitivity=options.get("silero_sensitivity", 0.6),
        webrtc_sensitivity=options.get("webrtc_sensitivity", 3),
        post_speech_silence=options.get("post_speech_silence", 0.5),
        realtime_preview=options.get("realtime_preview", False),
        realtime_model=options.get("realtime_model", "tiny"),
    )
    return WhisperASR(config)

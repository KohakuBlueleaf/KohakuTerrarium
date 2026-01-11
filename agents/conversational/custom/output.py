"""
Custom TTS output for conversational agent.

For demo purposes, this prints to console with typing effect.
Replace with actual TTS (Fish Speech, etc.) for production.
"""

import asyncio
import sys
from typing import AsyncIterator

from kohakuterrarium.modules.output.tts import AudioChunk, TTSConfig, TTSModule


class StreamingTTS(TTSModule):
    """
    Console-based TTS for testing.

    Prints text with a typing effect, simulating speech.
    """

    def __init__(
        self,
        config: TTSConfig | None = None,
        char_delay: float = 0.02,
        word_delay: float = 0.05,
    ):
        super().__init__(config)
        self.char_delay = char_delay
        self.word_delay = word_delay

    async def _initialize(self) -> None:
        """Initialize console output."""
        print("\n[StreamingTTS] Ready for output")
        print("=" * 50)

    async def _cleanup(self) -> None:
        """Cleanup."""
        print("\n[StreamingTTS] Stopped")

    async def _synthesize(self, text: str) -> AsyncIterator[AudioChunk]:
        """Yield chunks for streaming output."""
        # Process word by word for more natural pacing
        words = text.split()

        for i, word in enumerate(words):
            if self._interrupted:
                break

            # Add space before word (except first)
            if i > 0:
                yield AudioChunk(data=b" ", text=" ")

            # Yield word
            yield AudioChunk(data=word.encode(), text=word)

        # Final chunk
        yield AudioChunk(data=b"", is_final=True, text="")

    async def _play_audio(self, chunk: AudioChunk) -> None:
        """Print with typing effect."""
        if chunk.is_final:
            # End of utterance
            sys.stdout.write("\n")
            sys.stdout.flush()
            return

        text = chunk.text
        if not text:
            return

        # Print character by character for typing effect
        for char in text:
            if self._interrupted:
                break
            sys.stdout.write(char)
            sys.stdout.flush()
            await asyncio.sleep(self.char_delay)

        # Pause after word
        if text and not text.isspace():
            await asyncio.sleep(self.word_delay)

    async def _stop_playback(self) -> None:
        """Handle interruption."""
        sys.stdout.write(" [...]\n")
        sys.stdout.flush()


class SimpleTTS(TTSModule):
    """
    Simple TTS that just prints text immediately.

    No typing effect, just instant output.
    """

    async def _synthesize(self, text: str) -> AsyncIterator[AudioChunk]:
        yield AudioChunk(data=text.encode(), text=text, is_final=True)

    async def _play_audio(self, chunk: AudioChunk) -> None:
        if chunk.text:
            print(f"[AI]: {chunk.text}")

    async def _stop_playback(self) -> None:
        print("[interrupted]")

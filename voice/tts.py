"""Text-to-speech adapters behind one port.

Both adapters stream :class:`TtsChunk` — a ~20ms frame *plus the words
it voices*. That per-chunk text mapping is the load-bearing design
choice: interruption handling needs to know exactly what the caller
heard, and it must work identically for real audio and simulated audio.

- :class:`OpenAITts` — production adapter: synthesizes the whole reply,
  then streams it out in frames with text distributed proportionally.
- :class:`SimulatedTts` — offline adapter with *honest timing*: frames
  of silence paced at a configurable speaking rate (~150 wpm), so
  barge-in tests and demo timelines exercise real durations.
"""

from __future__ import annotations

import re
from typing import Iterator, Protocol

from config.settings import Settings
from core.exceptions import ConfigurationError
from core.logging import get_logger
from voice.models import AudioFormat, AudioFrame, TtsChunk

logger = get_logger("voice.tts")

_WORD_RE = re.compile(r"\S+")
_FRAME_MS = 20.0


class TtsPort(Protocol):
    """Text -> stream of (frame, spoken text) chunks."""

    def synthesize_stream(self, text: str) -> Iterator[TtsChunk]: ...


class SimulatedTts:
    """Timing-accurate silent synthesis (demo/test adapter)."""

    def __init__(self, words_per_minute: float = 150.0, fmt: AudioFormat | None = None) -> None:
        self._wpm = words_per_minute
        self._format = fmt or AudioFormat()

    def synthesize_stream(self, text: str) -> Iterator[TtsChunk]:
        words = _WORD_RE.findall(text)
        if not words:
            return
        ms_per_word = 60_000.0 / self._wpm
        frame_bytes = int(self._format.bytes_per_ms * _FRAME_MS)
        silence = b"\x00" * frame_bytes
        for word in words:
            frames = max(1, round(ms_per_word / _FRAME_MS))
            for index in range(frames):
                spoken = word + " " if index == frames - 1 else ""
                yield TtsChunk(
                    frame=AudioFrame(pcm=silence, format=self._format),
                    text=spoken,
                )


class OpenAITts:
    """OpenAI speech synthesis, re-streamed as text-annotated frames."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ConfigurationError(
                "VOICE_PROVIDER=openai requires OPENAI_API_KEY for text-to-speech."
            )
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.tts_model
        self._voice = settings.tts_voice
        self._format = AudioFormat(sample_rate=24000)  # PCM output rate of the API

    def synthesize_stream(self, text: str) -> Iterator[TtsChunk]:
        response = self._client.audio.speech.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="pcm",
        )
        audio = response.content
        frame_bytes = int(self._format.bytes_per_ms * _FRAME_MS)
        total_frames = max(1, len(audio) // frame_bytes)
        words = _WORD_RE.findall(text)
        logger.info(
            "Synthesized %d char(s) -> %.1fs of audio", len(text), total_frames * _FRAME_MS / 1000
        )
        # Distribute words across frames proportionally so interruption
        # can attribute spoken text to elapsed playback time.
        for index in range(total_frames):
            start = index * frame_bytes
            spoken_upto = int(len(words) * (index + 1) / total_frames)
            spoken_before = int(len(words) * index / total_frames)
            spoken = " ".join(words[spoken_before:spoken_upto])
            yield TtsChunk(
                frame=AudioFrame(pcm=audio[start : start + frame_bytes], format=self._format),
                text=spoken + " " if spoken else "",
            )

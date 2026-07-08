"""Voice data contracts: audio frames, TTS chunks, session events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique


@dataclass(frozen=True, slots=True)
class AudioFormat:
    """PCM format shared across the pipeline (16-bit mono by default)."""

    sample_rate: int = 16000
    sample_width: int = 2  # bytes per sample (16-bit)
    channels: int = 1

    @property
    def bytes_per_ms(self) -> float:
        return self.sample_rate * self.sample_width * self.channels / 1000.0


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """One chunk of PCM audio (typically 20ms)."""

    pcm: bytes
    format: AudioFormat = field(default_factory=AudioFormat)

    @property
    def duration_ms(self) -> float:
        return len(self.pcm) / self.format.bytes_per_ms


@dataclass(frozen=True, slots=True)
class TtsChunk:
    """One synthesized frame plus the exact text it voices.

    Carrying text per frame is what makes interruption honest: when the
    caller barges in, the pipeline knows precisely which words were
    already spoken and rewrites the conversation memory to match.
    """

    frame: AudioFrame
    text: str


@unique
class VoiceEventType(str, Enum):
    SESSION_STARTED = "SESSION_STARTED"
    UTTERANCE_RECEIVED = "UTTERANCE_RECEIVED"
    REPLY_STARTED = "REPLY_STARTED"
    REPLY_INTERRUPTED = "REPLY_INTERRUPTED"
    REPLY_COMPLETED = "REPLY_COMPLETED"
    SESSION_ENDED = "SESSION_ENDED"


@dataclass(frozen=True, slots=True)
class VoiceEvent:
    """A timestamped session event (rendered into the voice timeline)."""

    at_offset_s: float
    type: VoiceEventType
    detail: str = ""

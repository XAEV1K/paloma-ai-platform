"""Voice Activity Detection: energy-based with hangover smoothing.

RMS energy over 16-bit PCM frames against a threshold, debounced in both
directions: speech must persist for ``min_speech_ms`` to count as started
(filters coughs and clicks) and silence must persist for ``hangover_ms``
to count as ended (protects natural mid-sentence pauses). This is the
same class of algorithm as WebRTC VAD's energy tier — deterministic,
dependency-free and unit-testable; a model-based VAD can replace it
behind the identical ``process`` contract.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import Enum, unique

from voice.models import AudioFrame


@unique
class VadSignal(str, Enum):
    NONE = "NONE"
    SPEECH_STARTED = "SPEECH_STARTED"
    SPEECH_ENDED = "SPEECH_ENDED"


@dataclass
class EnergyVad:
    """Stateful VAD: feed frames in order, receive edge signals."""

    threshold_rms: float = 500.0  # int16 scale; ambient room noise sits well below
    min_speech_ms: float = 60.0
    hangover_ms: float = 300.0

    _in_speech: bool = False
    _speech_ms: float = 0.0
    _silence_ms: float = 0.0

    def process(self, frame: AudioFrame) -> VadSignal:
        """Consume one frame, emit a state-edge signal when one occurs."""
        loud = self._rms(frame.pcm) >= self.threshold_rms
        duration = frame.duration_ms

        if not self._in_speech:
            if loud:
                self._speech_ms += duration
                if self._speech_ms >= self.min_speech_ms:
                    self._in_speech = True
                    self._silence_ms = 0.0
                    return VadSignal.SPEECH_STARTED
            else:
                self._speech_ms = 0.0
            return VadSignal.NONE

        if loud:
            self._silence_ms = 0.0
            return VadSignal.NONE
        self._silence_ms += duration
        if self._silence_ms >= self.hangover_ms:
            self._in_speech = False
            self._speech_ms = 0.0
            return VadSignal.SPEECH_ENDED
        return VadSignal.NONE

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def reset(self) -> None:
        self._in_speech = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0

    @staticmethod
    def _rms(pcm: bytes) -> float:
        if len(pcm) < 2:
            return 0.0
        count = len(pcm) // 2
        samples = struct.unpack(f"<{count}h", pcm[: count * 2])
        return math.sqrt(sum(s * s for s in samples) / count)

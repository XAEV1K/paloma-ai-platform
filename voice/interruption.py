"""Barge-in detection: the interruption state machine.

The controller watches the *microphone* through VAD while TTS playback
is active. The contract with the pipeline is cooperative and synchronous:
playback checks ``should_interrupt`` between frames, which keeps
cancellation deterministic (no thread races) and bounds the reaction
latency to one frame (~20ms).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.logging import get_logger
from voice.models import AudioFrame
from voice.vad import EnergyVad, VadSignal

logger = get_logger("voice.interruption")


@dataclass
class InterruptionController:
    """Detects caller speech during assistant playback."""

    vad: EnergyVad = field(default_factory=EnergyVad)
    _playing: bool = False
    _interrupt_requested: bool = False

    def playback_started(self) -> None:
        self._playing = True
        self._interrupt_requested = False
        self.vad.reset()

    def playback_finished(self) -> None:
        self._playing = False
        self._interrupt_requested = False

    def on_mic_frame(self, frame: AudioFrame) -> None:
        """Feed one microphone frame captured during playback."""
        if not self._playing:
            return
        if self.vad.process(frame) is VadSignal.SPEECH_STARTED:
            self._interrupt_requested = True
            logger.info("Barge-in detected: caller started speaking during playback")

    @property
    def should_interrupt(self) -> bool:
        return self._interrupt_requested

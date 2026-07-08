"""Voice gateway: session lifecycle + the transport seam.

The gateway is where a real media transport (SIP trunk, WebRTC peer,
telephony provider webhook) will terminate: it owns session creation and
feeds utterances into the pipeline. Until a transport is wired, the
gateway also provides ``run_scripted_call`` — a demo/test driver that
pushes synthetic utterances (with optional mid-reply barge-in) through
the *entire* production path: VAD, STT port, Conversation Runtime, TTS
streaming and interruption handling.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from core.logging import get_logger
from voice.models import AudioFormat, AudioFrame, VoiceEventType
from voice.pipeline import VoicePipeline
from voice.session import VoiceSession

logger = get_logger("voice.gateway")


@dataclass(frozen=True, slots=True)
class ScriptedUtterance:
    """One caller utterance in a scripted call.

    ``barge_in_after_frames`` > 0 simulates the caller speaking again
    that many playback frames into the assistant's reply.
    """

    text: str
    barge_in_after_frames: int = 0


@dataclass
class ScriptedCall:
    """A whole scripted conversation for the demo driver."""

    utterances: list[ScriptedUtterance] = field(default_factory=list)
    restaurant_id: str | None = None


class VoiceGateway:
    """Creates sessions and routes utterances into the voice pipeline."""

    def __init__(self, pipeline: VoicePipeline, fmt: AudioFormat | None = None) -> None:
        self._pipeline = pipeline
        self._format = fmt or AudioFormat()

    def start_session(self, conversation_id: str | None = None) -> VoiceSession:
        session = VoiceSession(
            conversation_id=conversation_id or f"call-{uuid.uuid4().hex[:8]}"
        )
        session.record(VoiceEventType.SESSION_STARTED)
        logger.info("Voice session %s started (conversation %s)",
                    session.session_id, session.conversation_id)
        return session

    def end_session(self, session: VoiceSession) -> None:
        session.record(VoiceEventType.SESSION_ENDED)
        logger.info(
            "Voice session %s ended: %d event(s), %d interruption(s)",
            session.session_id,
            len(session.events),
            session.interruptions,
        )

    # ------------------------------------------------------------------
    # demo/test driver (the transport seam's loopback implementation)
    # ------------------------------------------------------------------
    def run_scripted_call(self, call: ScriptedCall) -> VoiceSession:
        """Drive a full call through the production pipeline."""
        session = self.start_session()
        for utterance in call.utterances:
            frames = [self._speech_frame()] * 10  # ~200ms of caller audio
            mic_during_reply = (
                self._barge_in_stream(utterance.barge_in_after_frames)
                if utterance.barge_in_after_frames > 0
                else ()
            )
            self._pipeline.handle_utterance(session, frames, mic_during_reply)
        self.end_session(session)
        return session

    def _speech_frame(self, loud: bool = True) -> AudioFrame:
        """A 20ms synthetic frame (square wave = clearly above VAD threshold)."""
        samples = int(self._format.sample_rate * 0.02)
        amplitude = 6000 if loud else 0
        pcm = b"".join(
            (amplitude if i % 2 == 0 else -amplitude).to_bytes(2, "little", signed=True)
            for i in range(samples)
        )
        return AudioFrame(pcm=pcm, format=self._format)

    def _barge_in_stream(self, quiet_frames: int):
        """Silence for N playback frames, then sustained caller speech."""
        for _ in range(quiet_frames):
            yield self._speech_frame(loud=False)
        while True:
            yield self._speech_frame(loud=True)

"""Voice pipeline: utterance in → grounded reply → interruptible playback.

Flow per utterance::

    mic frames ──STT──► text ──ConversationRuntime──► reply text
        reply ──TTS──► frames ──playback──► caller
                          ▲
                mic frames during playback ──VAD──► barge-in?

On barge-in the pipeline stops emitting frames, computes exactly which
words were delivered (TTS chunks carry their text), rewrites conversation
memory through ``runtime.register_interruption`` and publishes a domain
event. The caller's new utterance then proceeds normally — with the
memory reflecting reality, not intention.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Sequence

from core.logging import get_logger
from channels.local_api import LocalApiChannel
from events.bus import EventBus
from events.events import VoiceInterruptionOccurred
from voice.interruption import InterruptionController
from voice.models import AudioFrame, TtsChunk, VoiceEventType
from voice.session import VoiceSession
from voice.stt import SttPort
from voice.tts import TtsPort

logger = get_logger("voice.pipeline")


class VoicePipeline:
    """Binds STT, the Conversation Runtime, TTS and barge-in control."""

    name = "voice"

    def __init__(
        self,
        stt: SttPort,
        tts: TtsPort,
        interruption: InterruptionController,
        channel: LocalApiChannel,
        event_bus: EventBus,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._interruption = interruption
        self._channel = channel
        self._event_bus = event_bus

    def handle_utterance(
        self,
        session: VoiceSession,
        frames: Sequence[AudioFrame],
        mic_during_reply: Iterable[AudioFrame] = (),
    ) -> tuple[str, list[TtsChunk]]:
        """Process one caller utterance end-to-end.

        Args:
            session: The active voice session.
            frames: The caller's utterance audio (VAD-segmented upstream).
            mic_during_reply: Microphone frames captured while the reply
                plays — the barge-in signal source. In a live transport
                this is the real mic stream; in demos it is scripted.

        Returns:
            ``(delivered_text, emitted_chunks)`` — what the caller
            actually heard, which equals the full reply unless interrupted.
        """
        transcript = self._stt.transcribe(frames)
        session.record(VoiceEventType.UTTERANCE_RECEIVED, transcript[:80])
        logger.info("Utterance (%s): %r", session.session_id, transcript[:80])

        result = self._channel.respond(session.conversation_id, transcript)
        session.record(VoiceEventType.REPLY_STARTED, f"agent={result.agent_display_name}")

        delivered, chunks, interrupted = self._play(
            reply=result.reply, mic_during_reply=iter(mic_during_reply)
        )
        if interrupted:
            session.record(
                VoiceEventType.REPLY_INTERRUPTED, f"{len(delivered)} char(s) delivered"
            )
            self._channel._runtime.register_interruption(session.conversation_id, delivered)
            self._event_bus.publish(
                VoiceInterruptionOccurred(
                    request_id=session.session_id,
                    conversation_id=session.conversation_id,
                    spoken_chars=len(delivered),
                )
            )
        else:
            session.record(VoiceEventType.REPLY_COMPLETED, f"{len(delivered)} char(s)")
        return delivered, chunks

    # ------------------------------------------------------------------
    def _play(
        self, reply: str, mic_during_reply: Iterator[AudioFrame]
    ) -> tuple[str, list[TtsChunk], bool]:
        """Emit TTS chunks, checking the mic between frames (cooperative cancel)."""
        self._interruption.playback_started()
        spoken_parts: list[str] = []
        emitted: list[TtsChunk] = []
        interrupted = False
        try:
            for chunk in self._tts.synthesize_stream(reply):
                mic_frame = next(mic_during_reply, None)
                if mic_frame is not None:
                    self._interruption.on_mic_frame(mic_frame)
                if self._interruption.should_interrupt:
                    interrupted = True
                    break
                emitted.append(chunk)
                if chunk.text:
                    spoken_parts.append(chunk.text)
        finally:
            self._interruption.playback_finished()
        return "".join(spoken_parts).strip(), emitted, interrupted

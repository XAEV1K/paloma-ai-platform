"""Speech-to-text adapters behind one port.

- :class:`OpenAIWhisperStt` — production adapter: PCM is wrapped into an
  in-memory WAV and sent to the transcription API per utterance
  (utterance-batch STT; a streaming-partials provider slots in behind
  the same port).
- :class:`ScriptedStt` — deterministic adapter for demos/tests: returns
  pre-scripted transcripts in order. The pipeline, VAD and interruption
  logic run for real; only the acoustic model is substituted.
"""

from __future__ import annotations

import io
import wave
from typing import Protocol, Sequence

from config.settings import Settings
from core.exceptions import ConfigurationError
from core.logging import get_logger
from voice.models import AudioFormat, AudioFrame

logger = get_logger("voice.stt")


class SttPort(Protocol):
    """One utterance of audio -> transcript."""

    def transcribe(self, frames: Sequence[AudioFrame]) -> str: ...


class ScriptedStt:
    """Returns scripted transcripts in order (demo/test adapter)."""

    def __init__(self, transcripts: Sequence[str]) -> None:
        self._queue = list(transcripts)

    def transcribe(self, frames: Sequence[AudioFrame]) -> str:
        if not self._queue:
            raise ConfigurationError("ScriptedStt exhausted: no transcript left for utterance")
        text = self._queue.pop(0)
        logger.debug("Scripted transcript: %r", text[:60])
        return text


class OpenAIWhisperStt:
    """Whisper transcription over in-memory WAV."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ConfigurationError(
                "VOICE_PROVIDER=openai requires OPENAI_API_KEY for speech-to-text."
            )
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.stt_model

    def transcribe(self, frames: Sequence[AudioFrame]) -> str:
        if not frames:
            return ""
        wav_bytes = _frames_to_wav(frames)
        buffer = io.BytesIO(wav_bytes)
        buffer.name = "utterance.wav"  # the SDK infers format from the name
        response = self._client.audio.transcriptions.create(model=self._model, file=buffer)
        text = (response.text or "").strip()
        logger.info("Transcribed %.1fs of audio -> %d char(s)",
                    sum(f.duration_ms for f in frames) / 1000, len(text))
        return text


def _frames_to_wav(frames: Sequence[AudioFrame]) -> bytes:
    fmt: AudioFormat = frames[0].format
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(fmt.channels)
        wav.setsampwidth(fmt.sample_width)
        wav.setframerate(fmt.sample_rate)
        wav.writeframes(b"".join(frame.pcm for frame in frames))
    return buffer.getvalue()

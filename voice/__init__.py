"""Voice Platform: streaming audio in/out over the Conversation Runtime.

Voice is *just another channel*: the pipeline transcribes an utterance,
hands text to the same runtime that serves chat, and streams the reply
through TTS frame by frame. What makes it a platform rather than
"STT + TTS glued together":

- **VAD** (energy-based, hangover-smoothed) decides where utterances
  start and end;
- **interruption handling** is first-class: a caller barging in stops
  playback between frames, and the conversation memory is rewritten to
  exactly the words that were actually spoken;
- **timing honesty** — the simulated adapters reproduce real speech
  timing, so barge-in logic, session timelines and tests exercise the
  same state machine that production providers will drive.
"""

from voice.gateway import VoiceGateway
from voice.interruption import InterruptionController
from voice.models import AudioFormat, AudioFrame, TtsChunk, VoiceEvent, VoiceEventType
from voice.pipeline import VoicePipeline
from voice.session import VoiceSession
from voice.stt import OpenAIWhisperStt, ScriptedStt, SttPort
from voice.tts import OpenAITts, SimulatedTts, TtsPort
from voice.vad import EnergyVad

__all__ = [
    "AudioFormat",
    "AudioFrame",
    "EnergyVad",
    "InterruptionController",
    "OpenAITts",
    "OpenAIWhisperStt",
    "ScriptedStt",
    "SimulatedTts",
    "SttPort",
    "TtsChunk",
    "TtsPort",
    "VoiceEvent",
    "VoiceEventType",
    "VoiceGateway",
    "VoicePipeline",
    "VoiceSession",
]

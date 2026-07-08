"""Voice Platform: VAD, barge-in state machine, full pipeline with interruption."""

from __future__ import annotations

from typing import Iterator

import pytest

from channels.local_api import LocalApiChannel
from conversation.intents import RuleBasedIntentClassifier
from conversation.memory import InMemoryConversationStore
from conversation.router import AgentRouter
from conversation.runtime import ConversationRuntime
from config.settings import Settings
from crew.prompts import PromptRepository
from events.bus import InMemoryEventBus
from events.events import VoiceInterruptionOccurred
from llm.routing import AgentRole
from services.restaurant_service import CsvMetricsRepository, RestaurantService
from voice.gateway import ScriptedCall, ScriptedUtterance, VoiceGateway
from voice.interruption import InterruptionController
from voice.models import AudioFormat, AudioFrame, VoiceEventType
from voice.pipeline import VoicePipeline
from voice.stt import ScriptedStt
from voice.tts import SimulatedTts
from voice.vad import EnergyVad, VadSignal

_FORMAT = AudioFormat()


def _frame(loud: bool) -> AudioFrame:
    samples = int(_FORMAT.sample_rate * 0.02)
    amplitude = 6000 if loud else 50
    pcm = b"".join(
        (amplitude if i % 2 == 0 else -amplitude).to_bytes(2, "little", signed=True)
        for i in range(samples)
    )
    return AudioFrame(pcm=pcm, format=_FORMAT)


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def stream(self, role: AgentRole, messages: list[dict]) -> Iterator[str]:
        yield self.reply


def _pipeline(settings: Settings, transcripts: list[str], reply: str):
    store = InMemoryConversationStore()
    bus = InMemoryEventBus()
    runtime = ConversationRuntime(
        store=store,
        classifier=RuleBasedIntentClassifier(),
        router=AgentRouter(),
        llm=FakeLLM(reply),
        prompts=PromptRepository(settings.prompts_dir, "v1"),
        context_builder=None,  # ungrounded is fine for voice mechanics tests
        restaurant_service=RestaurantService(CsvMetricsRepository(settings.restaurants_csv)),
        event_bus=bus,
    )
    pipeline = VoicePipeline(
        stt=ScriptedStt(transcripts),
        tts=SimulatedTts(words_per_minute=600),  # fast speech keeps tests quick
        interruption=InterruptionController(),
        channel=LocalApiChannel(runtime),
        event_bus=bus,
    )
    return pipeline, store, bus


# --- VAD -----------------------------------------------------------------------
def test_vad_detects_speech_edges() -> None:
    vad = EnergyVad(min_speech_ms=40, hangover_ms=100)
    signals = [vad.process(_frame(loud=False)) for _ in range(3)]
    assert set(signals) == {VadSignal.NONE}

    edge = [vad.process(_frame(loud=True)) for _ in range(3)]
    assert VadSignal.SPEECH_STARTED in edge

    trailing = [vad.process(_frame(loud=False)) for _ in range(8)]
    assert VadSignal.SPEECH_ENDED in trailing


def test_vad_ignores_short_blips() -> None:
    vad = EnergyVad(min_speech_ms=60, hangover_ms=100)
    assert vad.process(_frame(loud=True)) is VadSignal.NONE  # 20ms blip < 60ms
    assert vad.process(_frame(loud=False)) is VadSignal.NONE
    assert not vad.in_speech


# --- interruption controller ---------------------------------------------------------
def test_no_barge_in_on_silence() -> None:
    controller = InterruptionController(vad=EnergyVad(min_speech_ms=40))
    controller.playback_started()
    for _ in range(10):
        controller.on_mic_frame(_frame(loud=False))
    assert controller.should_interrupt is False


def test_barge_in_on_sustained_speech() -> None:
    controller = InterruptionController(vad=EnergyVad(min_speech_ms=40))
    controller.playback_started()
    for _ in range(4):
        controller.on_mic_frame(_frame(loud=True))
    assert controller.should_interrupt is True

    controller.playback_finished()
    assert controller.should_interrupt is False


def test_mic_ignored_when_not_playing() -> None:
    controller = InterruptionController(vad=EnergyVad(min_speech_ms=40))
    for _ in range(4):
        controller.on_mic_frame(_frame(loud=True))
    assert controller.should_interrupt is False


# --- pipeline ------------------------------------------------------------------------
def test_uninterrupted_reply_is_fully_delivered(settings: Settings) -> None:
    reply = "The dispatch board assigns the nearest idle courier automatically."
    pipeline, store, _ = _pipeline(settings, ["how does dispatch work?"], reply)
    session_gateway = VoiceGateway(pipeline)

    session = session_gateway.run_scripted_call(
        ScriptedCall(utterances=[ScriptedUtterance(text="how does dispatch work?")])
    )

    types = [event.type for event in session.events]
    assert VoiceEventType.REPLY_COMPLETED in types
    assert VoiceEventType.REPLY_INTERRUPTED not in types
    state = store.load(session.conversation_id)
    assert state.turns[-1].content == reply
    assert state.turns[-1].interrupted is False


def test_barge_in_truncates_reply_and_memory(settings: Settings) -> None:
    reply = (
        "First we check the marketplace token, then the venue status, then the "
        "local network, and finally we re-authorise the integration completely."
    )
    pipeline, store, bus = _pipeline(settings, ["orders not working"], reply)
    interruption_events: list = []
    bus.subscribe(VoiceInterruptionOccurred, interruption_events.append)

    session = VoiceGateway(pipeline).run_scripted_call(
        ScriptedCall(
            utterances=[ScriptedUtterance(text="orders not working", barge_in_after_frames=6)]
        )
    )

    types = [event.type for event in session.events]
    assert VoiceEventType.REPLY_INTERRUPTED in types
    assert session.interruptions == 1
    assert len(interruption_events) == 1

    state = store.load(session.conversation_id)
    last = state.turns[-1]
    assert last.interrupted is True
    assert last.content != reply and reply.startswith(last.content[: len(last.content) // 2])


def test_multi_utterance_call_keeps_one_conversation(settings: Settings) -> None:
    pipeline, store, _ = _pipeline(
        settings, ["first question", "second question"], "Short answer."
    )
    session = VoiceGateway(pipeline).run_scripted_call(
        ScriptedCall(
            utterances=[
                ScriptedUtterance(text="first question"),
                ScriptedUtterance(text="second question"),
            ]
        )
    )
    state = store.load(session.conversation_id)
    assert len(state.turns) == 4  # 2 user + 2 assistant
    assert "Voice Timeline" in session.timeline()

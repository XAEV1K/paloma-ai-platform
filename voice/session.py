"""Voice session: identity, event log and the voice timeline."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from voice.models import VoiceEvent, VoiceEventType


@dataclass
class VoiceSession:
    """One call: links a transport session to a conversation."""

    conversation_id: str
    session_id: str = field(default_factory=lambda: f"voice-{uuid.uuid4().hex[:8]}")
    events: list[VoiceEvent] = field(default_factory=list)
    _t0: float = field(default_factory=time.monotonic)

    def record(self, event_type: VoiceEventType, detail: str = "") -> None:
        self.events.append(
            VoiceEvent(
                at_offset_s=round(time.monotonic() - self._t0, 3),
                type=event_type,
                detail=detail,
            )
        )

    @property
    def interruptions(self) -> int:
        return sum(1 for e in self.events if e.type is VoiceEventType.REPLY_INTERRUPTED)

    def timeline(self) -> str:
        """ASCII voice timeline, matching the platform's other timelines."""
        lines = [f"Voice Timeline · session {self.session_id}"]
        for event in self.events:
            detail = f"  {event.detail}" if event.detail else ""
            lines.append(f"{event.at_offset_s:7.2f}s ├─ {event.type.value:<20}{detail}")
        return "\n".join(lines)

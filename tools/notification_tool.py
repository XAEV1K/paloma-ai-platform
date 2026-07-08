"""Notification tool: durable outbound messaging for agents."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from core.logging import get_logger
from services.notification_service import NotificationService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.notification")


class NotificationInput(BaseModel):
    channel: Literal["email", "sms", "slack"] = Field(description="Delivery channel.")
    recipient: str = Field(min_length=3, description="Address/number/channel name.")
    message: str = Field(min_length=1, max_length=2000)


@register_tool
class NotificationTool(InstrumentedTool):
    """Queues a notification into the durable outbox (never sends inline)."""

    name: str = "send_notification"
    description: str = (
        "Queue an outbound notification (email/sms/slack) for a recipient. "
        "Delivery is asynchronous via the platform outbox — this call returns "
        "a notification id immediately and never blocks on external services."
    )
    args_schema: type[BaseModel] = NotificationInput

    notification_service: NotificationService

    def _execute(self, channel: str, recipient: str, message: str) -> str:
        notification_id = self.notification_service.queue(channel, recipient, message)
        return json.dumps({"notification_id": notification_id, "status": "QUEUED"})

"""Green API HTTP client — transport plumbing only.

Wraps the official Green API REST surface (send, notification queue,
instance state) behind typed methods. Concerns handled here and only
here: URL construction, timeouts, bounded retry with exponential backoff
on transient faults (network errors, 5xx, 429), and credential-safe
logging (the token never appears in logs). No message semantics — the
WhatsApp adapter owns those.

Both Green API consumption modes are supported:
- **polling** (``receive_notification``/``delete_notification``) — works
  from any machine without a public URL; used by the live listener;
- **webhook** payloads are parsed by the adapter, so a future FastAPI
  receiver reuses everything here unchanged.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from config.settings import Settings
from core.exceptions import ConfigurationError, PalomaError
from core.logging import get_logger

logger = get_logger("communication.green_api")

_RETRIES = 3
_BACKOFF_BASE_S = 0.5
_TIMEOUT_S = 12.0
#: ReceiveNotification long-polls server-side; give it headroom.
_RECEIVE_TIMEOUT_S = 25.0


class GreenApiError(PalomaError):
    """A Green API call failed after all retries."""


class GreenApiClient:
    """Typed, retrying client for one Green API instance."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if not settings.whatsapp_configured:
            raise ConfigurationError(
                "WhatsApp requires GREEN_API_INSTANCE_ID and GREEN_API_TOKEN in .env "
                "(from your Green API console)."
            )
        self._base = (
            f"{settings.green_api_url.rstrip('/')}"
            f"/waInstance{settings.green_api_instance_id}"
        )
        self._token = settings.green_api_token
        self._client = httpx.Client(timeout=_TIMEOUT_S, transport=transport)
        self._instance_id = settings.green_api_instance_id

    # ------------------------------------------------------------------
    # REST surface
    # ------------------------------------------------------------------
    def send_message(self, chat_id: str, text: str) -> str:
        """Send a text message; returns Green API's idMessage."""
        payload = {"chatId": chat_id, "message": text}
        data = self._request("POST", "sendMessage", json=payload)
        message_id = str((data or {}).get("idMessage", ""))
        logger.info("WhatsApp message sent to %s (id=%s, %d chars)",
                    chat_id, message_id or "?", len(text))
        return message_id

    def receive_notification(self, receive_timeout_s: int = 20) -> dict[str, Any] | None:
        """Pop the next queued notification (None when the queue is empty).

        ``receiveTimeout`` long-polls server-side (5–60s per Green API docs),
        so an idle listener makes ~3 requests/minute instead of hammering.
        """
        data = self._request(
            "GET",
            "receiveNotification",
            params={"receiveTimeout": receive_timeout_s},
            timeout=receive_timeout_s + 10.0,
            # Observed in production: some instances answer an EMPTY queue
            # with HTTP 404 (docs promise null). Same meaning — no messages.
            treat_404_as_empty=True,
        )
        return data  # {'receiptId': int, 'body': {...}} or None

    def delete_notification(self, receipt_id: int) -> None:
        """Acknowledge a consumed notification so the queue advances."""
        self._request("DELETE", f"deleteNotification/{receipt_id}", path_has_suffix=True)

    def get_state_instance(self) -> str:
        """Instance state: 'authorized' means the WhatsApp account is live."""
        data = self._request("GET", "getStateInstance")
        return str((data or {}).get("stateInstance", "unknown"))

    def get_settings(self) -> dict[str, Any]:
        """Current instance settings (webhook URL, notification toggles)."""
        return self._request("GET", "getSettings") or {}

    def set_settings(self, settings: dict[str, Any]) -> None:
        """Update instance settings. Green API applies changes for up to ~1 min."""
        self._request("POST", "setSettings", json=settings)

    def ensure_polling_mode(self) -> str:
        """Make the notification QUEUE usable and return a status detail.

        Green API routes notifications EITHER to a custom webhook URL OR to
        the polling queue — with a webhook configured, ``receiveNotification``
        answers 404 ("clear webhook url for instance"). New instances often
        ship with a webhook preset, so the platform normalises the instance
        itself instead of sending the operator to the console:

        - clears ``webhookUrl`` when one is set,
        - enables ``incomingWebhook`` so inbound messages enter the queue.
        """
        settings = self.get_settings()
        webhook_url = str(settings.get("webhookUrl") or "").strip()
        incoming_enabled = str(settings.get("incomingWebhook") or "").lower() == "yes"

        if not webhook_url and incoming_enabled:
            return "notification queue active (no webhook, incoming enabled)"

        changes: dict[str, Any] = {}
        if webhook_url:
            changes["webhookUrl"] = ""
            changes["webhookUrlToken"] = ""
        if not incoming_enabled:
            changes["incomingWebhook"] = "yes"
        logger.warning(
            "Instance not in polling mode (webhookUrl=%r, incomingWebhook=%s) — "
            "updating settings: %s",
            webhook_url[:60],
            settings.get("incomingWebhook"),
            sorted(changes),
        )
        self.set_settings(changes)
        return (
            "instance settings updated (webhook cleared, incoming notifications "
            "enabled) — Green API applies changes for up to ~1 minute"
        )

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float | None = None,
        path_has_suffix: bool = False,
        treat_404_as_empty: bool = False,
    ) -> dict[str, Any] | None:
        # Green API path shape: /waInstance{ID}/{method}/{TOKEN}[/{suffix}]
        if path_has_suffix:
            head, _, suffix = endpoint.partition("/")
            url = f"{self._base}/{head}/{self._token}/{suffix}"
        else:
            url = f"{self._base}/{endpoint}/{self._token}"
        safe_name = endpoint.split("/")[0]

        last_error: Exception | None = None
        for attempt in range(1, _RETRIES + 1):
            try:
                response = self._client.request(
                    method, url, json=json, params=params, timeout=timeout
                )
                if treat_404_as_empty and response.status_code == 404:
                    return None
                if response.status_code in (429,) or response.status_code >= 500:
                    raise GreenApiError(
                        f"Green API {safe_name}: HTTP {response.status_code}"
                    )
                if response.status_code >= 400:
                    # 4xx (bad credentials, bad chatId) will not improve on retry.
                    raise GreenApiError(
                        f"Green API {safe_name}: HTTP {response.status_code} — "
                        f"{response.text[:200]}"
                    ) from None
                if not response.content or response.text.strip() in ("", "null"):
                    return None
                return response.json()
            except (httpx.TransportError, GreenApiError) as exc:
                if isinstance(exc, GreenApiError) and "HTTP 4" in str(exc):
                    raise  # permanent fault: fail fast
                last_error = exc
                if attempt < _RETRIES:
                    delay = _BACKOFF_BASE_S * (2 ** (attempt - 1))
                    logger.warning(
                        "Green API %s attempt %d/%d failed (%s) — retrying in %.1fs",
                        safe_name, attempt, _RETRIES, exc, delay,
                    )
                    time.sleep(delay)
        raise GreenApiError(
            f"Green API {safe_name} failed after {_RETRIES} attempts: {last_error}"
        ) from last_error

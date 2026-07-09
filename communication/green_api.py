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

    def receive_notification(self) -> dict[str, Any] | None:
        """Pop the next queued notification (None when the queue is empty)."""
        data = self._request("GET", "receiveNotification", timeout=_RECEIVE_TIMEOUT_S)
        return data  # {'receiptId': int, 'body': {...}} or None

    def delete_notification(self, receipt_id: int) -> None:
        """Acknowledge a consumed notification so the queue advances."""
        self._request("DELETE", f"deleteNotification/{receipt_id}", path_has_suffix=True)

    def get_state_instance(self) -> str:
        """Instance state: 'authorized' means the WhatsApp account is live."""
        data = self._request("GET", "getStateInstance")
        return str((data or {}).get("stateInstance", "unknown"))

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        timeout: float | None = None,
        path_has_suffix: bool = False,
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
                response = self._client.request(method, url, json=json, timeout=timeout)
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

"""Channel adapters: one file per transport, all behind TransportPort.

Voice already runs as a channel through the Voice Platform; Telegram and
Email are future siblings of the WhatsApp adapter — an adapter file and
a router registration, zero core changes.
"""

from communication.channels.webchat import WebChatTransport
from communication.channels.whatsapp import WhatsAppTransport

__all__ = ["WebChatTransport", "WhatsAppTransport"]

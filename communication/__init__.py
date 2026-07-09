"""Communication Platform: transports over the Conversation Runtime.

The corporate messaging layer of the AI Operating Platform. A message
travels::

    WhatsApp / WebChat / (Telegram, Email — future adapters)
        └► Transport adapter (pure transport, zero business logic)
             └► MessageDispatcher
                  └► SessionManager (address → conversation, restaurant binding)
                       └► Conversation Runtime (intent → memory → RAG → LLM)
                            └► ResponseBuilder (per-channel formatting)
                                 └► Transport.send ──► the customer

Adding a channel = one adapter file implementing :class:`TransportPort`
plus one router registration; the core never changes.
"""

from communication.dispatcher import MessageDispatcher, MessageReport
from communication.response_builder import ResponseBuilder
from communication.router import ChannelRouter
from communication.session import CommunicationSession, SessionManager
from communication.transport import InboundMessage, OutboundMessage, TransportPort

__all__ = [
    "ChannelRouter",
    "CommunicationSession",
    "InboundMessage",
    "MessageDispatcher",
    "MessageReport",
    "OutboundMessage",
    "ResponseBuilder",
    "SessionManager",
    "TransportPort",
]

"""Channel adapters: transports over the Conversation Runtime.

A channel is deliberately thin — receive text, stream tokens back,
nothing else. The runtime carries all intelligence, so WhatsApp,
Telegram or e-mail become new adapters here without touching the core.
"""

from channels.base import ChannelAdapter
from channels.chat_cli import ChatCliChannel
from channels.local_api import LocalApiChannel

__all__ = ["ChannelAdapter", "ChatCliChannel", "LocalApiChannel"]

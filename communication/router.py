"""Channel router: name → transport, nothing else.

The dispatcher asks "how do I reach channel X" and gets a transport.
Registration happens in the composition root; an unregistered channel is
a configuration fault reported precisely.
"""

from __future__ import annotations

from core.exceptions import ConfigurationError
from core.logging import get_logger
from communication.transport import TransportPort

logger = get_logger("communication.router")


class ChannelRouter:
    """Registry of live transports keyed by channel name."""

    def __init__(self) -> None:
        self._transports: dict[str, TransportPort] = {}

    def register(self, transport: TransportPort) -> None:
        if transport.name in self._transports:
            raise ConfigurationError(f"Channel '{transport.name}' registered twice")
        self._transports[transport.name] = transport
        logger.info("Channel registered: %s", transport.name)

    def resolve(self, channel: str) -> TransportPort:
        transport = self._transports.get(channel)
        if transport is None:
            raise ConfigurationError(
                f"No transport for channel '{channel}' "
                f"(registered: {', '.join(sorted(self._transports)) or 'none'})"
            )
        return transport

    def channels(self) -> list[str]:
        return sorted(self._transports)

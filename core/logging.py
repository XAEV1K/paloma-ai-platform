"""Centralised logging configuration.

Every component obtains its logger via :func:`get_logger` so the whole
platform shares one namespace (``paloma.*``) and one handler policy.
The observability story of a demo run looks like::

    [18:42:01] INFO    paloma.crew: Architect started
    [18:42:02] INFO    paloma.services.restaurant: Loading metrics for R-001
    [18:42:05] INFO    paloma.tools.roi: ROI Tool executed (roi=142.3%)
    [18:42:08] INFO    paloma.engines.validator: Validation passed (0 issues)
    [18:42:09] INFO    paloma.services.report: Report generated -> reports/R-001.md

TODO: swap the stream handler for structured JSON logging (structlog /
OpenTelemetry) when the platform is deployed behind a log collector.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

ROOT_LOGGER_NAME: Final[str] = "paloma"

_LOG_FORMAT: Final[str] = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT: Final[str] = "%H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    """Configure the ``paloma`` logger tree exactly once.

    Idempotent by design: repeated calls (tests, notebooks) do not stack
    duplicate handlers.

    Args:
        level: Standard logging level name (``DEBUG``, ``INFO``, ...).
    """
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(level.upper())

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    if not root.handlers:  # idempotency guard
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    # Do not propagate into the (possibly noisy) global root logger.
    root.propagate = False

    # Third-party libraries (CrewAI logs provider errors via logging.error on
    # the ROOT logger) would otherwise print unformatted "ERROR:root:" lines.
    # Give the global root the same format, warnings and above only.
    global_root = logging.getLogger()
    if not global_root.handlers:
        third_party = logging.StreamHandler(stream=sys.stdout)
        third_party.setFormatter(formatter)
        global_root.addHandler(third_party)
    global_root.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``paloma`` namespace.

    Args:
        name: Dotted suffix, e.g. ``services.restaurant`` or ``engines.roi``.
    """
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")

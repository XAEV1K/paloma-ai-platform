"""Process-level runtime configuration.

Must run before any CrewAI import: third-party frameworks read their
environment at import time, so this is the one place where import order
legitimately matters. ``main.py`` calls :func:`configure_runtime` as its
first statement.

Responsibilities:
- disable CrewAI's interactive tracing prompt and telemetry (a demo or a
  CI run must never block on a [y/N] question);
- enable ANSI escape processing on legacy Windows consoles (otherwise
  CrewAI's colored output prints as ``←[32m`` garbage);
- force UTF-8 stdout (timeline boxes are UTF-8; Windows defaults to a
  legacy codepage);
- silence the known-benign CrewAI warning about closure callbacks (we do
  not use crew checkpointing).
"""

from __future__ import annotations

import os
import sys
import warnings


def configure_runtime() -> None:
    """Prepare the process for a clean, non-interactive platform run."""
    # CrewAI: no interactive trace prompts, no telemetry phone-home.
    os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

    # We intentionally pass closures as task callbacks (they carry the
    # ExecutionContext); we never use checkpointing, so the warning is noise.
    warnings.filterwarnings(
        "ignore", message="function callbacks cannot be serialized"
    )

    if sys.platform == "win32":
        os.system("")  # enables VT100/ANSI processing on legacy consoles

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

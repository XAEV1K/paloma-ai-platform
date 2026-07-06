"""Paloma AI Platform — CLI entry point.

Usage::

    python main.py --restaurant-id R-001      # run the full pipeline
    python main.py --list-restaurants          # show available demo data

The CLI is intentionally thin: parse args, build the container, run the
pipeline, print a human summary. All real behaviour lives in the layers
below and is reachable programmatically (future FastAPI surface reuses
the exact same ``Container``).
"""

from __future__ import annotations

# Runtime bootstrap MUST precede any CrewAI import (frameworks read their
# environment at import time) — hence the unconventional import order.
from core.bootstrap import configure_runtime

configure_runtime()

import argparse  # noqa: E402
import sys  # noqa: E402

from config.settings import get_settings  # noqa: E402
from core.container import Container  # noqa: E402
from core.exceptions import PalomaError  # noqa: E402
from core.logging import configure_logging, get_logger  # noqa: E402
from metrics.report import render_summary, render_timeline  # noqa: E402

logger = get_logger("main")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="paloma-ai-platform",
        description="Agentic decision-support platform for Paloma365 restaurants.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--restaurant-id", help="Restaurant to analyse, e.g. R-001")
    group.add_argument(
        "--list-restaurants",
        action="store_true",
        help="List restaurant ids available in the data source.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else settings.log_level)

    try:
        container = Container.build(settings)

        if args.list_restaurants:
            for restaurant_id in container.restaurant_service.list_restaurants():
                print(restaurant_id)
            return 0

        # Fail fast on credentials for every model in the routing table —
        # before the first agent runs, not in the middle of a demo.
        container.llm_router.validate()

        result = container.pipeline.run(args.restaurant_id)

        print("\n" + "=" * 60)
        print(f"  Restaurant   : {result.offer.restaurant_id}")
        print(f"  Offer        : {result.offer.offer_id}")
        print(f"  Modules      : {', '.join(c.value for c in result.offer.module_codes)}")
        print(f"  ROI          : {result.offer.roi.roi_pct:.1f}%")
        print(f"  Validation   : {result.validation.status.value}")
        print(f"  Report       : {result.report_path}")
        print("=" * 60)

        execution = result.execution
        print()
        print(render_timeline(execution.tracer.spans))
        print()
        print(
            render_summary(
                execution.request_id, execution.restaurant_id, execution.metrics.snapshot()
            )
        )
        return 0

    except PalomaError as exc:
        logger.error("Pipeline aborted: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

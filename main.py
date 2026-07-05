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

import argparse
import sys

from config.settings import get_settings
from core.container import Container
from core.exceptions import PalomaError
from core.logging import configure_logging, get_logger
from metrics.report import render_summary, render_timeline

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
    # Windows consoles often default to a legacy codepage (cp1251/cp866);
    # the timeline/summary boxes are UTF-8, so upgrade stdout defensively.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)

    try:
        container = Container.build(settings)

        if args.list_restaurants:
            for restaurant_id in container.restaurant_service.list_restaurants():
                print(restaurant_id)
            return 0

        container.llm_provider.validate()  # fail fast before any agent runs

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

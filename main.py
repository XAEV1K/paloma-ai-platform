"""Paloma AI Platform — CLI entry point.

Usage::

    python main.py --restaurant-id R-001              # full pipeline run
    python main.py --restaurant-id R-005 --open-report # + open HTML proposal
    python main.py --demo                              # demo mode (clean output)
    python main.py --list-restaurants                  # available scenarios

The CLI is intentionally thin: parse args, build the container, run the
pipeline, print the decision funnel. All real behaviour lives in the
layers below and is reachable programmatically (a future FastAPI surface
reuses the exact same ``Container``).
"""

from __future__ import annotations

# Runtime bootstrap MUST precede any CrewAI import (frameworks read their
# environment at import time) — hence the unconventional import order.
from core.bootstrap import configure_runtime

configure_runtime()

import argparse  # noqa: E402
import sys  # noqa: E402
import webbrowser  # noqa: E402

from config.settings import get_settings  # noqa: E402
from core.container import Container  # noqa: E402
from core.exceptions import PalomaError  # noqa: E402
from core.logging import configure_logging, get_logger  # noqa: E402
from metrics.report import render_summary, render_timeline  # noqa: E402
from presentation import ReportContext  # noqa: E402
from presentation.console import render_flow  # noqa: E402

logger = get_logger("main")

_DEMO_RESTAURANT = "R-001"

_EPILOG = """\
demo scenarios (data/restaurants.csv):
  R-001  Dastarkhan Lounge      dine-in venue: retention + delivery + kitchen issues
  R-002  Bella Napoli Pizzeria  pizzeria: retention, slow kitchen, small ticket
  R-003  Coffee & Crumbs        coffee shop: small ticket; delivery was declined before
  R-004  Sakura Sushi House     sushi: healthy, single retention gap (minimal offer)
  R-005  Ghost Kitchen KZ       dark kitchen: overloaded kitchen, weak retention
  R-006  Tandoor Palace Group   4-location group: the full-problem flagship demo

examples:
  python main.py --demo
  python main.py --restaurant-id R-006 --open-report
  python main.py --restaurant-id R-005 --quiet
"""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="paloma-ai-platform",
        description=(
            "Paloma365 AI Decision Platform — agentic analysis, ROI-backed module "
            "recommendations and validated commercial proposals for restaurants."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--restaurant-id", metavar="ID", help="Restaurant to analyse, e.g. R-001")
    parser.add_argument(
        "--list-restaurants",
        action="store_true",
        help="List restaurant ids available in the data source.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=f"Demo mode: run {_DEMO_RESTAURANT} with clean product-style output "
        "and auto-open the HTML proposal.",
    )
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="Open the HTML proposal in the default browser after the run.",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose", action="store_true", help="DEBUG logging + full agent traces."
    )
    verbosity.add_argument(
        "--quiet", action="store_true", help="Warnings only + no agent traces."
    )
    args = parser.parse_args(argv)

    if not (args.restaurant_id or args.list_restaurants or args.demo):
        parser.error("choose one of: --restaurant-id ID, --demo, --list-restaurants")
    return args


def _print_failure(message: str) -> None:
    print()
    print("─" * 60)
    print("  ✖ Run aborted")
    print(f"    {message}")
    print("    Check the log lines above and your .env configuration.")
    print("─" * 60)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    settings = get_settings()
    if args.demo or args.quiet:
        # Demo/quiet: hide agent internals, keep the product narrative.
        settings = settings.model_copy(update={"agent_verbose": False})

    if args.verbose:
        log_level = "DEBUG"
    elif args.quiet:
        log_level = "WARNING"
    else:
        log_level = "DEBUG" if settings.debug else settings.log_level
    configure_logging(log_level)

    restaurant_id = args.restaurant_id or _DEMO_RESTAURANT
    open_report = args.open_report or args.demo

    try:
        container = Container.build(settings)

        if args.list_restaurants:
            for rid in container.restaurant_service.list_restaurants():
                print(rid)
            return 0

        # Fail fast on credentials for every model in the routing table —
        # before the first agent runs, not in the middle of a demo.
        container.llm_router.validate()

        result = container.pipeline.run(restaurant_id)

        execution = result.execution
        context = ReportContext(
            business_case=result.business_case,
            offer=result.offer,
            validation=result.validation,
            metrics=result.metrics,
        )
        print()
        print(render_flow(context, execution.request_id, result.report_path, result.html_report_path))
        print()
        print(render_timeline(execution.tracer.spans))
        print()
        print(
            render_summary(
                execution.request_id, execution.restaurant_id, execution.metrics.snapshot()
            )
        )

        if open_report and result.html_report_path is not None:
            webbrowser.open(result.html_report_path.resolve().as_uri())
            logger.info("Opened HTML proposal in the default browser")
        return 0

    except PalomaError as exc:
        logger.error("Pipeline aborted: %s", exc)
        _print_failure(str(exc))
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001 — the user must never see a traceback
        logger.error("Unexpected failure: %s: %s", type(exc).__name__, exc)
        logger.debug("Full traceback follows", exc_info=True)  # visible with --verbose
        _print_failure(f"Unexpected {type(exc).__name__}: {str(exc)[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

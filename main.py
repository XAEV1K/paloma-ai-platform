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
            "Paloma365 AI Operations Platform — one AI core, many scenarios: "
            "business analysis with validated ROI proposals, RAG-grounded support "
            "and sales conversations, and a voice channel with interruption handling."
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
        "--ingest",
        action="store_true",
        help="(Re)index the knowledge base: knowledge_docs/ -> chunks -> embeddings -> vector store.",
    )
    parser.add_argument(
        "--ask",
        metavar="QUESTION",
        help="One-shot grounded answer from the Support Agent (RAG + streaming).",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Interactive multi-agent chat (support/sales/analyst/technical routing).",
    )
    parser.add_argument(
        "--voice-demo",
        action="store_true",
        help="Scripted voice call through the full pipeline, including barge-in interruption.",
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

    modes = (
        args.restaurant_id,
        args.list_restaurants,
        args.demo,
        args.ingest,
        args.ask,
        args.chat,
        args.voice_demo,
    )
    if not any(modes):
        parser.error(
            "choose one of: --restaurant-id ID, --demo, --chat, --ask QUESTION, "
            "--ingest, --voice-demo, --list-restaurants"
        )
    return args


def _run_ingest(container: Container) -> int:
    """Reindex the knowledge base and print the ingestion report."""
    report = container.ingestion_service.ingest_directory(
        container.settings.knowledge_docs_dir
    )
    from events.events import KnowledgeIngested

    container.event_bus.publish(
        KnowledgeIngested(
            request_id="ingest",
            files=report.files,
            chunks=report.chunks,
            duration_ms=report.duration_ms,
        )
    )
    print()
    print("─" * 60)
    print("  Knowledge base indexed")
    print(f"    files    : {report.files}")
    print(f"    chunks   : {report.chunks}")
    print(f"    duration : {report.duration_ms:.0f}ms")
    if report.skipped:
        print(f"    skipped  : {', '.join(report.skipped)}")
    print("─" * 60)
    return 0


def _run_ask(container: Container, question: str) -> int:
    """One-shot grounded answer with full retrieval observability."""
    import uuid

    print("\nai > ", end="", flush=True)
    result = container.conversation_runtime.process_turn(
        conversation_id=f"ask-{uuid.uuid4().hex[:8]}",
        user_text=question,
        channel="api",
        on_token=lambda token: print(token, end="", flush=True),
    )
    print("\n")
    print("─" * 60)
    print(f"  agent   : {result.agent_display_name} (intent {result.intent})")
    print(f"  latency : {result.latency_ms / 1000:.1f}s")
    if result.context is not None:
        metrics = result.context.metrics
        print(
            f"  retrieval: {metrics.total_ms:.0f}ms "
            f"(embed {metrics.embedding_ms:.0f} / search {metrics.search_ms:.0f} "
            f"/ rerank {metrics.rerank_ms:.0f}), "
            f"{metrics.returned}/{metrics.candidates} chunk(s)"
        )
        for position, item in enumerate(result.context.chunks, start=1):
            heading = item.chunk.metadata.get("heading", "")
            print(
                f"    [S{position}] {item.chunk.source} · {heading} · "
                f"score {item.score:.3f} ({'+'.join(item.channels)})"
            )
    else:
        print("  retrieval: none (run --ingest first to index knowledge_docs/)")
    print("─" * 60)
    return 0


def _run_voice_demo(container: Container) -> int:
    """Scripted call through the full voice pipeline, with barge-in."""
    from channels.local_api import LocalApiChannel
    from voice.gateway import ScriptedCall, ScriptedUtterance, VoiceGateway
    from voice.interruption import InterruptionController
    from voice.pipeline import VoicePipeline
    from voice.stt import ScriptedStt
    from voice.tts import SimulatedTts

    script = ScriptedCall(
        utterances=[
            ScriptedUtterance(text="Hi! Delivery orders are not showing up in our kitchen queue."),
            ScriptedUtterance(
                text="Wait, actually — it says the marketplace token expired, how do I fix that?",
                barge_in_after_frames=120,  # caller barges in ~6 words into the reply
            ),
            ScriptedUtterance(text="Got it, thanks. And what does the delivery module cost monthly?"),
        ]
    )
    pipeline = VoicePipeline(
        stt=ScriptedStt([utterance.text for utterance in script.utterances]),
        tts=SimulatedTts(),
        interruption=InterruptionController(),
        channel=LocalApiChannel(container.conversation_runtime),
        event_bus=container.event_bus,
    )
    session = VoiceGateway(pipeline).run_scripted_call(script)
    print()
    print(session.timeline())
    print(
        f"\n  {len(script.utterances)} utterance(s), "
        f"{session.interruptions} interruption(s) — conversation memory reflects "
        f"exactly what the caller heard."
    )
    return 0


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

        if args.ingest:
            return _run_ingest(container)
        if args.ask:
            return _run_ask(container, args.ask)
        if args.chat:
            from channels.chat_cli import ChatCliChannel

            return ChatCliChannel(container.conversation_runtime).run()
        if args.voice_demo:
            return _run_voice_demo(container)

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

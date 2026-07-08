"""Knowledge ingestion: parsers + pipeline idempotency."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import DataSourceError
from rag.chunking import ChunkingService
from rag.embeddings import HashingEmbedder
from rag.ingestion import IngestionService
from rag.parsers import parse_file
from rag.vector_store import InMemoryVectorStore


@pytest.fixture()
def service() -> tuple[IngestionService, InMemoryVectorStore]:
    store = InMemoryVectorStore()
    return IngestionService(ChunkingService(), HashingEmbedder(), store), store


def test_markdown_and_text_and_html_are_parsed(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Title\n\nBody text.", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Plain text body.", encoding="utf-8")
    (tmp_path / "c.html").write_text(
        "<html><body><h1>Heading</h1><p>Paragraph one.</p>"
        "<script>ignored()</script></body></html>",
        encoding="utf-8",
    )
    assert parse_file(tmp_path / "a.md")[0] == "markdown"
    assert "Plain text body." in parse_file(tmp_path / "b.txt")[1]
    html_text = parse_file(tmp_path / "c.html")[1]
    assert "Paragraph one." in html_text and "ignored" not in html_text
    assert "# Heading" in html_text


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    weird = tmp_path / "data.xyz"
    weird.write_text("?", encoding="utf-8")
    with pytest.raises(DataSourceError, match="Unsupported"):
        parse_file(weird)


def test_directory_ingestion_reports_and_indexes(service, tmp_path: Path) -> None:
    ingestion, store = service
    (tmp_path / "manual.md").write_text(
        "# Manual\n\n## Dispatch\n\nCouriers are dispatched from the board.",
        encoding="utf-8",
    )
    (tmp_path / "faq.txt").write_text("Loyalty points expire after 90 days.", encoding="utf-8")

    report = ingestion.ingest_directory(tmp_path)

    assert report.files == 2
    assert report.chunks == store.count() > 0
    assert report.skipped == []


def test_reingestion_is_idempotent(service, tmp_path: Path) -> None:
    ingestion, store = service
    (tmp_path / "manual.md").write_text("# Manual\n\nDispatch text.", encoding="utf-8")

    ingestion.ingest_directory(tmp_path)
    first_count = store.count()
    ingestion.ingest_directory(tmp_path)

    assert store.count() == first_count


def test_real_knowledge_corpus_ingests(service) -> None:
    """The shipped knowledge_docs/ corpus must always index cleanly."""
    from config.settings import Settings

    ingestion, store = service
    report = ingestion.ingest_directory(Settings(_env_file=None).knowledge_docs_dir)  # type: ignore[call-arg]

    assert report.files >= 4
    assert store.count() >= 10

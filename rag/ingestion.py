"""Knowledge ingestion pipeline: files → chunks → embeddings → vector store.

One deterministic write path for the entire knowledge base. Re-ingesting
a file replaces its chunks (stable ``doc_id`` from the source path), so
the pipeline is idempotent — run it on every deploy or on a schedule.

Future connectors (CRM notes, Wiki, Confluence) implement the same
contract: produce ``(Document, text)`` pairs and call ``ingest_text``;
nothing downstream changes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from core.exceptions import DataSourceError
from core.logging import get_logger
from rag.chunking import ChunkingService
from rag.embeddings import EmbeddingPort
from rag.models import Document
from rag.parsers import SUPPORTED_EXTENSIONS, parse_file
from rag.vector_store import VectorStorePort

logger = get_logger("rag.ingestion")


@dataclass(frozen=True, slots=True)
class IngestionReport:
    """Observability artifact for one ingestion run."""

    files: int
    chunks: int
    skipped: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class IngestionService:
    """Loads, chunks, embeds and stores knowledge documents."""

    def __init__(
        self,
        chunking: ChunkingService,
        embedder: EmbeddingPort,
        store: VectorStorePort,
    ) -> None:
        self._chunking = chunking
        self._embedder = embedder
        self._store = store

    def ingest_directory(self, directory: Path) -> IngestionReport:
        """Ingest every supported file under ``directory`` (recursive)."""
        if not directory.is_dir():
            raise DataSourceError(f"Knowledge directory not found: {directory}")
        started = time.monotonic()
        files = sorted(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        total_chunks = 0
        skipped: list[str] = []
        for path in files:
            try:
                total_chunks += self.ingest_file(path)
            except DataSourceError as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
                skipped.append(path.name)
        report = IngestionReport(
            files=len(files) - len(skipped),
            chunks=total_chunks,
            skipped=skipped,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
        )
        logger.info(
            "Ingestion complete: %d file(s), %d chunk(s) in %.0fms (%d skipped)",
            report.files,
            report.chunks,
            report.duration_ms,
            len(report.skipped),
        )
        return report

    def ingest_file(self, path: Path) -> int:
        """Ingest a single file; returns the number of chunks stored."""
        media_type, text = parse_file(path)
        document = Document(
            doc_id=Document.make_id(str(path)),
            source=path.name,
            title=self._title_from(path, text),
            media_type=media_type,
        )
        return self.ingest_text(document, text)

    def ingest_text(self, document: Document, text: str) -> int:
        """The connector-facing entry point: any (Document, text) pair."""
        chunks = self._chunking.split(document, text)
        if not chunks:
            logger.warning("Document '%s' produced no chunks — empty content?", document.title)
            return 0
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        self._store.add(chunks, vectors)
        logger.info("Ingested '%s': %d chunk(s)", document.title, len(chunks))
        return len(chunks)

    @staticmethod
    def _title_from(path: Path, text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
            if stripped:
                break
        return path.stem.replace("-", " ").replace("_", " ").title()

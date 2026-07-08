"""RAG subsystem: chunking, embeddings, stores, hybrid retrieval, context."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.chunking import ChunkingService
from rag.context_builder import ContextBuilder
from rag.embeddings import HashingEmbedder
from rag.models import Document
from rag.retrieval import RerankerService, RetrievalService
from rag.vector_store import InMemoryVectorStore

_DOCS = {
    "delivery": (
        "# Delivery Module\n\n## Courier dispatch\n\n"
        "Couriers are assigned from the dispatch board with live GPS tracking. "
        "Auto-assign picks the nearest idle courier for each delivery order.\n\n"
        "## Zones\n\nDelivery zones are polygons with per-zone fees."
    ),
    "loyalty": (
        "# Loyalty Program\n\n## Cashback\n\n"
        "Guests earn bonus points as cashback on every order. Points expire "
        "after ninety days to encourage repeat visits and retention."
    ),
    "kitchen": (
        "# Kitchen Display\n\n## Timers\n\n"
        "Each station screen shows preparation timers; overdue tickets flash "
        "so the expeditor can react before food gets cold."
    ),
}


def _document(name: str) -> Document:
    return Document(
        doc_id=Document.make_id(name),
        source=f"{name}.md",
        title=name.title(),
        media_type="markdown",
    )


@pytest.fixture()
def populated_store() -> tuple[InMemoryVectorStore, HashingEmbedder]:
    chunker = ChunkingService(max_chars=400, overlap_chars=60)
    embedder = HashingEmbedder()
    store = InMemoryVectorStore()
    for name, text in _DOCS.items():
        chunks = chunker.split(_document(name), text)
        store.add(chunks, embedder.embed([chunk.text for chunk in chunks]))
    return store, embedder


def _retrieval(store: InMemoryVectorStore, embedder: HashingEmbedder) -> RetrievalService:
    return RetrievalService(embedder, store, RerankerService(), top_k=3, candidate_pool=10)


# --- chunking ---------------------------------------------------------------
def test_chunks_respect_max_size_and_carry_headings() -> None:
    chunker = ChunkingService(max_chars=300, overlap_chars=50)
    text = "# Guide\n\n## Section A\n\n" + ("Sentence about dispatch. " * 40)
    chunks = chunker.split(_document("guide"), text)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 300 + 100 for chunk in chunks)  # heading prefix allowance
    assert all("Section A" in chunk.text for chunk in chunks)


def test_chunking_is_deterministic() -> None:
    chunker = ChunkingService()
    first = chunker.split(_document("delivery"), _DOCS["delivery"])
    second = chunker.split(_document("delivery"), _DOCS["delivery"])
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


# --- embeddings ----------------------------------------------------------------
def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    embedder = HashingEmbedder(dimension=128)
    first, second = embedder.embed(["courier dispatch board"] * 2)
    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6


def test_different_topics_get_different_vectors() -> None:
    embedder = HashingEmbedder()
    delivery, loyalty = embedder.embed(["courier delivery zones", "loyalty cashback points"])
    similarity = sum(a * b for a, b in zip(delivery, loyalty))
    assert similarity < 0.5


# --- store & retrieval -----------------------------------------------------------
def test_vector_search_finds_the_right_document(populated_store) -> None:
    store, embedder = populated_store
    results, metrics = _retrieval(store, embedder).retrieve("courier GPS dispatch")

    assert results, "retrieval must return chunks"
    assert results[0].chunk.source == "delivery.md"
    assert metrics.returned == len(results)
    assert metrics.total_ms >= 0


def test_hybrid_channels_are_reported(populated_store) -> None:
    store, embedder = populated_store
    results, _ = _retrieval(store, embedder).retrieve("cashback points expire")

    top = results[0]
    assert top.chunk.source == "loyalty.md"
    assert set(top.channels) <= {"vector", "keyword"} and top.channels


def test_reingestion_replaces_not_duplicates(populated_store) -> None:
    store, embedder = populated_store
    before = store.count()
    chunker = ChunkingService(max_chars=400, overlap_chars=60)
    chunks = chunker.split(_document("delivery"), _DOCS["delivery"])
    store.add(chunks, embedder.embed([c.text for c in chunks]))
    assert store.count() == before


def test_store_persistence_roundtrip(populated_store, tmp_path: Path) -> None:
    store, embedder = populated_store
    persisted = InMemoryVectorStore(persist_path=tmp_path / "index.json")
    chunker = ChunkingService()
    chunks = chunker.split(_document("delivery"), _DOCS["delivery"])
    persisted.add(chunks, embedder.embed([c.text for c in chunks]))

    reloaded = InMemoryVectorStore(persist_path=tmp_path / "index.json")
    assert reloaded.count() == persisted.count()
    hits = reloaded.vector_search(embedder.embed(["courier dispatch"])[0], k=1)
    assert hits and hits[0][0].source == "delivery.md"


# --- context builder ----------------------------------------------------------------
def test_context_package_is_budgeted_and_cited(populated_store) -> None:
    store, embedder = populated_store
    builder = ContextBuilder(_retrieval(store, embedder), char_budget=600)

    package = builder.build("how does courier dispatch work")

    assert not package.is_empty
    assert package.char_count <= 600
    assert "[S1]" in package.text
    assert "delivery.md" in package.sources


def test_empty_store_yields_empty_package() -> None:
    embedder = HashingEmbedder()
    builder = ContextBuilder(_retrieval(InMemoryVectorStore(), embedder), char_budget=1000)
    package = builder.build("anything")
    assert package.is_empty and package.text == ""

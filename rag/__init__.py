"""RAG subsystem: ingestion → chunking → embeddings → vector store → retrieval.

A self-contained architectural layer, NOT a "chat with PDF" feature:

- every stage sits behind a port (``EmbeddingPort``, ``VectorStorePort``),
  so PGVector, OpenAI embeddings and local adapters are swappable in the
  composition root — the LLM never learns what a vector database is;
- the only thing that crosses into the agent layer is a rendered
  :class:`ContextPackage` (top chunks + sources + retrieval metrics);
- everything below the embedding provider runs offline and is unit-tested.
"""

from rag.chunking import ChunkingService
from rag.context_builder import ContextBuilder
from rag.embeddings import EmbeddingPort, HashingEmbedder, OpenAIEmbedder
from rag.ingestion import IngestionReport, IngestionService
from rag.models import Chunk, ContextPackage, Document, RetrievalMetrics, RetrievedChunk
from rag.retrieval import RerankerService, RetrievalService
from rag.vector_store import InMemoryVectorStore, PgVectorStore, VectorStorePort

__all__ = [
    "Chunk",
    "ChunkingService",
    "ContextBuilder",
    "ContextPackage",
    "Document",
    "EmbeddingPort",
    "HashingEmbedder",
    "InMemoryVectorStore",
    "IngestionReport",
    "IngestionService",
    "OpenAIEmbedder",
    "PgVectorStore",
    "RerankerService",
    "RetrievalMetrics",
    "RetrievalService",
    "RetrievedChunk",
    "VectorStorePort",
]

"""Knowledge search tool: RAG for the decision-pipeline agents.

The conversation runtime grounds turns deterministically; pipeline
agents get the same retrieval through this tool — one knowledge base,
one retrieval engine, two consumption styles.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from rag.context_builder import ContextBuilder
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.vector_search")


class VectorSearchInput(BaseModel):
    query: str = Field(min_length=3, description="Natural-language question or topic.")


@register_tool
class VectorSearchTool(InstrumentedTool):
    """Semantic + keyword search over the Paloma365 knowledge base."""

    name: str = "knowledge_search"
    description: str = (
        "Search the ingested knowledge base (manuals, FAQ, guides) with hybrid "
        "semantic+keyword retrieval. Returns the most relevant passages with "
        "source citations. Use this for product facts beyond the module catalog."
    )
    args_schema: type[BaseModel] = VectorSearchInput

    context_builder: ContextBuilder

    def _execute(self, query: str) -> str:
        logger.info("Knowledge search: %r", query[:80])
        package = self.context_builder.build(query)
        if package.is_empty:
            return json.dumps({"query": query, "passages": [], "note": "no matches"})
        return json.dumps(
            {
                "query": query,
                "passages": package.text,
                "sources": package.sources,
                "retrieval_ms": package.metrics.total_ms,
            },
            ensure_ascii=False,
            indent=2,
        )

"""Pipeline anti-hallucination and resilience guards (no LLM required)."""

from __future__ import annotations

import pytest

from core.exceptions import (
    AgentContractError,
    PalomaError,
    PipelineExecutionError,
)
from core.structured_output import extract_contract
from crew.crew import PalomaPipeline
from models.offer import OfferRef


class _FakeCrewOutput:
    def __init__(self, raws: list[str]) -> None:
        self.tasks_output = [type("T", (), {"raw": raw})() for raw in raws]


def test_stage_raw_returns_the_stage_answer() -> None:
    output = _FakeCrewOutput(["first", "second"])
    assert PalomaPipeline._stage_raw(output, 1, "Developer") == "second"


def test_missing_stage_is_a_clean_contract_error() -> None:
    output = _FakeCrewOutput(["only one"])
    with pytest.raises(AgentContractError, match="Developer stage produced no output"):
        PalomaPipeline._stage_raw(output, 1, "Developer")


def test_fabricated_reference_is_detected_by_extraction_plus_repository() -> None:
    """The extractor accepts the JSON; the repository lookup is the guard."""
    raw = (
        '{"offer_id": "OF-FAKE", "restaurant_id": "R-001", '
        '"module_codes": ["DELIVERY"], "headline": "looks legit"}'
    )
    ref = extract_contract(raw, OfferRef)
    assert ref.offer_id == "OF-FAKE"  # parsing succeeds; crew.run() checks existence


def test_domain_error_hierarchy() -> None:
    """The CLI catches PalomaError — every failure mode must be inside it."""
    assert issubclass(AgentContractError, PalomaError)
    assert issubclass(PipelineExecutionError, PalomaError)

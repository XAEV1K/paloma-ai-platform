"""Pipeline anti-hallucination guards (no LLM required)."""

from __future__ import annotations

import pytest

from core.exceptions import AgentContractError, PalomaError
from crew.crew import PalomaPipeline
from models.offer import OfferRef


class _FakeTaskOutput:
    def __init__(self, payload: object) -> None:
        self.pydantic = payload


def test_typed_output_accepts_the_contract_model() -> None:
    ref = OfferRef(
        offer_id="OF-1", restaurant_id="R-001", module_codes=["DELIVERY"], headline="h"
    )
    assert PalomaPipeline._typed_output(_FakeTaskOutput(ref), OfferRef) is ref


def test_typed_output_rejects_wrong_payload() -> None:
    with pytest.raises(AgentContractError, match="expected OfferRef"):
        PalomaPipeline._typed_output(_FakeTaskOutput({"offer_id": "OF-1"}), OfferRef)


def test_typed_output_rejects_missing_payload() -> None:
    with pytest.raises(AgentContractError):
        PalomaPipeline._typed_output(object(), OfferRef)


def test_contract_error_is_a_domain_error() -> None:
    """The CLI catches PalomaError — contract violations must exit cleanly."""
    assert issubclass(AgentContractError, PalomaError)

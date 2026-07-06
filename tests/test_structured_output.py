"""Deterministic contract extraction — the CrewAI-converter replacement.

Every case here reproduces a real production behaviour observed in logs:
draft-then-correction answers, markdown fences, wrapper keys, prose.
"""

from __future__ import annotations

import pytest

from core.exceptions import AgentContractError
from core.structured_output import extract_contract
from models.offer import OfferRef
from models.validation import ValidationReport

_VALID_REF = (
    '{"offer_id": "OF-1", "restaurant_id": "R-001", '
    '"module_codes": ["DELIVERY"], "headline": "ok"}'
)


def test_plain_json() -> None:
    ref = extract_contract(_VALID_REF, OfferRef)
    assert ref.offer_id == "OF-1"


def test_markdown_fenced_json() -> None:
    ref = extract_contract(f"```json\n{_VALID_REF}\n```", OfferRef)
    assert ref.offer_id == "OF-1"


def test_prose_around_json() -> None:
    ref = extract_contract(f"Here is the result you asked for:\n{_VALID_REF}\nDone!", OfferRef)
    assert ref.offer_id == "OF-1"


def test_draft_then_correction_takes_the_last_blob() -> None:
    """Production log: the Architect emitted a draft, prose, then a fix."""
    draft = _VALID_REF.replace("OF-1", "OF-DRAFT")
    corrected = _VALID_REF.replace("OF-1", "OF-FINAL")
    raw = f"{draft}\n\nLet me correct and provide the complete answer:\n\n{corrected}"

    assert extract_contract(raw, OfferRef).offer_id == "OF-FINAL"


def test_invalid_last_blob_falls_back_to_earlier_valid_one() -> None:
    corrected_but_broken = '{"offer_id": "OF-2"}'  # missing required fields
    raw = f"{_VALID_REF}\nActually:\n{corrected_but_broken}"

    assert extract_contract(raw, OfferRef).offer_id == "OF-1"


def test_single_key_wrapper_is_unwrapped() -> None:
    """Production log: a cost-tier model wrapped the report in an extra key."""
    raw = (
        '{"offer_validation_response": {"offer_id": "OF-3", "status": "PASSED", '
        '"issues": [], "rules_checked": 5, '
        '"created_at": "2026-07-06T07:10:47Z"}}'
    )
    report = extract_contract(raw, ValidationReport)
    assert report.offer_id == "OF-3"
    assert report.is_approved


def test_empty_answer_is_a_contract_error() -> None:
    with pytest.raises(AgentContractError, match="empty"):
        extract_contract("   ", OfferRef)


def test_garbage_is_a_contract_error_with_detail() -> None:
    with pytest.raises(AgentContractError, match="OfferRef"):
        extract_contract("I could not complete the task, sorry.", OfferRef)


def test_wrong_schema_reports_closest_failure() -> None:
    with pytest.raises(AgentContractError, match="validation error"):
        extract_contract('{"foo": 1}', OfferRef)

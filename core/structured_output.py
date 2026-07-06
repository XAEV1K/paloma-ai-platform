"""Deterministic contract extraction from LLM text.

Replaces CrewAI's ``output_pydantic`` converter entirely. The converter
proved fragile in production: when an answer is not one clean JSON blob
it re-calls the LLM with a provider-specific JSON schema — which failed
with 400s (Anthropic rejects ``maxItems``), burned three retry calls and
crashed the run. This module is the architectural replacement:

- pure Python, zero LLM calls, zero provider coupling;
- tolerates markdown fences, prose around the JSON, multiple JSON blobs
  (models often self-correct — the LAST valid blob wins), and single-key
  wrapper objects (``{"response": {...}}`` — observed from a cost-tier
  model);
- fails with a precise :class:`AgentContractError`, never a traceback.
"""

from __future__ import annotations

import json
import re
from typing import Iterator, TypeVar

from pydantic import BaseModel, ValidationError

from core.exceptions import AgentContractError
from core.logging import get_logger

logger = get_logger("core.structured_output")

TModel = TypeVar("TModel", bound=BaseModel)

_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*")
#: How deep to unwrap single-key wrapper objects.
_MAX_UNWRAP_DEPTH = 2


def extract_contract(raw: str, model: type[TModel]) -> TModel:
    """Extract and validate a ``model`` instance from an agent's raw answer.

    Candidates are tried **last-to-first**: when a model emits a draft,
    then a correction, the correction is the one we want.

    Raises:
        AgentContractError: When no JSON candidate validates against the
            contract. The message summarises what was found.
    """
    if not raw or not raw.strip():
        raise AgentContractError(
            f"Cannot extract {model.__name__}: the agent returned an empty answer."
        )

    text = _FENCE_RE.sub("", raw)
    candidates = list(_json_objects(text))
    last_error: ValidationError | None = None

    for index, candidate in enumerate(reversed(candidates)):
        for payload in _payload_variants(candidate):
            try:
                instance = model.model_validate(payload)
            except ValidationError as exc:
                last_error = exc
                continue
            logger.debug(
                "%s extracted from candidate %d/%d (from the end)",
                model.__name__,
                index + 1,
                len(candidates),
            )
            return instance

    detail = ""
    if last_error is not None:
        first = last_error.errors()[0]
        detail = (
            f" Closest candidate failed with {last_error.error_count()} "
            f"validation error(s); first: {first.get('loc')} — {first.get('msg')}."
        )
    raise AgentContractError(
        f"Could not extract a valid {model.__name__} from the agent's answer: "
        f"{len(candidates)} JSON object(s) found, none matched the contract.{detail}"
    )


def _json_objects(text: str) -> Iterator[dict]:
    """Yield every top-level JSON object embedded in ``text``, in order."""
    decoder = json.JSONDecoder()
    index = 0
    while True:
        start = text.find("{", index)
        if start == -1:
            return
        try:
            parsed, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(parsed, dict):
            yield parsed
        index = end


def _payload_variants(candidate: dict) -> Iterator[dict]:
    """Yield the candidate itself, then progressively unwrapped inner objects.

    Handles answers like ``{"offer_validation_response": {...actual...}}``.
    """
    current: dict = candidate
    yield current
    for _ in range(_MAX_UNWRAP_DEPTH):
        if len(current) == 1:
            (inner,) = current.values()
            if isinstance(inner, dict):
                current = inner
                yield current
                continue
        return

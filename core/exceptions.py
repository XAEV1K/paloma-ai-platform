"""Application exception hierarchy.

A single root (:class:`PalomaError`) lets callers distinguish domain
failures from programming errors: ``except PalomaError`` at the pipeline
boundary catches everything the platform can reasonably recover from,
while ``TypeError``/``ValueError`` bugs still surface loudly.
"""

from __future__ import annotations


class PalomaError(Exception):
    """Base class for all domain-level errors raised by the platform."""


class ConfigurationError(PalomaError):
    """Raised when settings are missing or inconsistent (e.g. no API key)."""


class DataSourceError(PalomaError):
    """Raised when a data source (CSV/SQLite/API) cannot be read or parsed."""


class RestaurantNotFoundError(DataSourceError):
    """Raised when a restaurant id is absent from the metrics repository."""

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(f"Restaurant '{restaurant_id}' not found in data source")
        self.restaurant_id = restaurant_id


class UnknownModuleError(PalomaError):
    """Raised when a Paloma365 module code is not present in the catalog."""

    def __init__(self, module_code: str) -> None:
        super().__init__(f"Unknown Paloma365 module code: '{module_code}'")
        self.module_code = module_code


class OfferNotFoundError(PalomaError):
    """Raised when an offer id is absent from the offer repository."""

    def __init__(self, offer_id: str) -> None:
        super().__init__(f"Offer '{offer_id}' not found in offer repository")
        self.offer_id = offer_id


class PipelineExecutionError(PalomaError):
    """Raised when the agent crew fails to execute (provider outage, 4xx,
    timeout, framework fault). Wraps the underlying cause into a clean
    domain failure so the CLI never shows a third-party traceback.
    """


class AgentContractError(PalomaError):
    """Raised when an LLM agent's output violates a pipeline contract.

    This is the firewall against hallucinated artifacts: a fabricated
    offer id, an answer that does not parse into the stage's Pydantic
    contract, or an unexpected payload type. The pipeline converts these
    into a clean domain failure instead of a raw traceback.
    """

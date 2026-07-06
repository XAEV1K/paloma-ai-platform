"""Typed application settings (single source of configuration truth).

Built on ``pydantic-settings`` so every value is validated at startup and
can be overridden via environment variables or ``.env`` — no scattered
``os.getenv`` calls and no mutable global state. Access goes through
:func:`get_settings` (cached), which keeps the object injectable in tests
via ``get_settings.cache_clear()`` + monkeypatched environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The repository root: config/settings.py -> config/ -> <root>
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration for the Paloma AI Platform.

    Every field maps 1:1 to an environment variable of the same name
    (case-insensitive). See ``.env.example`` for the documented surface.
    """

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # We intentionally use MODEL_ARCHITECT / MODEL_DEVELOPER / MODEL_VALIDATOR
        # env vars; disable pydantic's "model_" protected namespace for them.
        protected_namespaces=(),
    )

    # --- Application -----------------------------------------------------
    app_name: str = Field(default="Paloma AI Decision Platform")
    environment: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug: bool = Field(
        default=False,
        description="True forces DEBUG logging regardless of LOG_LEVEL.",
    )

    # --- LLM routing -------------------------------------------------------
    llm_provider: str = Field(
        default="openai",
        description="Default vendor for model ids without a known prefix.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Fallback model for any role without an explicit MODEL_<ROLE>.",
    )
    # Per-role model assignments (full LiteLLM ids; with openrouter write the
    # complete catalog path, e.g. 'openrouter/anthropic/claude-sonnet-5').
    model_architect: str | None = Field(
        default=None, description="Strong reasoning model for diagnosis."
    )
    model_developer: str | None = Field(
        default=None, description="Fast, reliable tool-calling model."
    )
    model_validator: str | None = Field(
        default=None,
        description="Cheapest/fastest model — it only relays a machine verdict.",
    )
    llm_temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Global override; unset -> per-role defaults (0.2/0.1/0.0).",
    )
    # Credentials are all optional so offline tooling/tests still import;
    # the selected provider fails fast in validate() if its key is missing.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    ollama_base_url: str = Field(default="http://localhost:11434")

    # Optional per-1M-token prices for cost estimation (prices change too
    # often to hardcode — the operator owns them).
    llm_price_input_per_1m: float | None = Field(default=None, ge=0)
    llm_price_output_per_1m: float | None = Field(default=None, ge=0)

    # --- Prompts ---------------------------------------------------------
    prompt_version: str = Field(
        default="v3",
        description="Which prompts/<agent>_<version>.md files the agents load.",
    )

    # --- Feature flags ---------------------------------------------------
    use_validator_agent: bool = Field(
        default=True,
        description="False = skip the Validator agent; ValidatorEngine still runs in Python.",
    )
    use_cache: bool = Field(
        default=True,
        description="Wrap the metrics repository in a TTL cache (one read per restaurant).",
    )
    use_sqlite: bool = Field(
        default=False,
        description="Use the SQLite metrics backend instead of CSV (roadmap).",
    )
    use_business_memory: bool = Field(
        default=True,
        description="Give agents the business_memory tool and record runs to history.",
    )
    cache_ttl_seconds: float = Field(default=300.0, gt=0)

    # --- Orchestration -------------------------------------------------
    agent_verbose: bool = Field(
        default=True,
        description="Stream CrewAI agent traces to stdout (great for demos).",
    )
    agent_max_iterations: int = Field(
        default=6,
        ge=1,
        description="Hard cap on tool-use loops per agent — protects the token budget.",
    )

    # --- Observability --------------------------------------------------
    log_level: str = Field(default="INFO")

    # --- Paths (derived, not env-driven) --------------------------------
    project_root: Path = _PROJECT_ROOT

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def prompts_dir(self) -> Path:
        return self.project_root / "prompts"

    @property
    def reports_dir(self) -> Path:
        return self.project_root / "reports"

    @property
    def restaurants_csv(self) -> Path:
        return self.data_dir / "restaurants.csv"

    @property
    def modules_json(self) -> Path:
        return self.data_dir / "modules.json"

    @property
    def prices_json(self) -> Path:
        return self.data_dir / "prices.json"

    @property
    def memory_json(self) -> Path:
        return self.data_dir / "memory.json"

    @property
    def sqlite_db(self) -> Path:
        return self.data_dir / "restaurants.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance (lazily created, cached)."""
    return Settings()

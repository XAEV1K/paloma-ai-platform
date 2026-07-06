# Paloma AI Platform

**Agentic decision-support platform for restaurant businesses, built on Paloma365 data.**

`python 3.12+` · `crewai 1.x` · `pydantic v2` · **prompt version: v3** · multi-model routing (OpenAI / Anthropic / Gemini / OpenRouter / Ollama)

The platform analyses a restaurant's real performance metrics, diagnoses growth
bottlenecks, selects the right Paloma365 product modules, computes the financial
effect deterministically, and produces a validated, client-ready commercial
offer — in minutes instead of hours.

> **Core engineering principle: LLM thinks. Python works.**
>
> The LLM never calculates ROI, never parses CSV, never touches SQL and never
> invents prices. Every number in the system is produced by deterministic,
> unit-tested Python engines. The LLM contributes exactly what it is good at:
> analysis, prioritisation, decision-making and business narrative.

---

## Architecture

```
                              USER
                                │
                                ▼
                     ┌─────────────────────┐
                     │  CrewAI Orchestrator │        crew/
                     └─────────┬───────────┘
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐    ┌─────────────┐     ┌─────────────┐
   │ AI Architect │──▶│ AI Developer │──▶ │ AI Validator │
   └──────┬──────┘    └──────┬──────┘     └──────┬──────┘
          │  BusinessCase    │  OfferRef         │  ValidationReport
          │                  │                   │
          ▼                  ▼                   ▼
   ┌────────────────────────────────────────────────────┐
   │                     Tool Layer                     │   tools/
   │  analytics · crm · recommendations · knowledge     │
   │  roi_calculator · offer_generator · validation     │
   └───────────────────────────┬────────────────────────┘
                               ▼
   ┌────────────────────────────────────────────────────┐
   │           Services & Deterministic Engines         │   services/ engines/
   │  RestaurantService · KnowledgeService · CrmService │
   │  OfferService · ReportService                      │
   │  ROIEngine · RecommendationEngine · ValidatorEngine│
   └───────────────────────────┬────────────────────────┘
                               ▼
   ┌────────────────────────────────────────────────────┐
   │                  Data Sources Layer                │   data/
   │      CSV · JSON catalog · SQLite (planned) · API   │
   └────────────────────────────────────────────────────┘
```

Key properties:

- **Agents never exchange free text.** Every hand-off is a strict Pydantic
  contract (`BusinessCase` → `OfferRef` → `ValidationReport`) enforced by
  CrewAI's `output_pydantic`.
- **Large payloads never enter the LLM context.** The full offer lives in an
  `OfferRepository`; agents pass a token-cheap `OfferRef` (id + headline).
- **Dependencies point inwards.** `crew → tools → services/engines → models`.
  The composition root (`core/container.py`) is the only place where the
  object graph is assembled — swapping CSV for SQLite or the mock CRM for the
  real API is a one-line change there.
- **The Validator is deterministic.** An offer cannot reach a client with an
  implausible ROI, an invented module or a tampered price: `ValidatorEngine`
  re-checks everything against the catalog. Even with the Validator *agent*
  disabled (`USE_VALIDATOR_AGENT=false`), the engine still runs in Python.
- **Event-driven core.** The pipeline publishes typed domain events
  (`BusinessCaseCreated`, `OfferCreated`, `ValidationCompleted`,
  `ReportGenerated`) to an event bus. A Slack notifier, analytics sink or
  CRM sync agent extends the platform by *subscribing* — pipeline code
  never changes.
- **Business memory.** The platform remembers past diagnoses, offers and
  their outcomes per restaurant. Agents check history before recommending:
  a module the client rejected six months ago is not re-pitched without
  new evidence — and when it is, the offer explicitly says what changed.
- **Full observability.** Every run gets an `ExecutionContext` (request id,
  token counts, tool-call spans). The CLI ends with an execution timeline
  and a cost/latency summary box.

## Installation

```bash
git clone <repo-url> paloma-ai-platform
cd paloma-ai-platform

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
copy .env.example .env          # then set OPENAI_API_KEY
```

Requires **Python 3.12+**.

## Quick Start

```bash
# See which demo restaurants are available
python main.py --list-restaurants

# Run the full pipeline for one restaurant
python main.py --restaurant-id R-001
```

A successful run streams the agent trace and finishes with:

```
[18:42:01] INFO    paloma.crew.pipeline: Pipeline started for restaurant R-001 (request 3f2a9c41d0be)
[18:42:02] INFO    paloma.services.restaurant: Loaded metrics for R-001 from restaurants.csv
[18:42:03] INFO    paloma.services.restaurant: Cache hit: metrics for R-001
[18:42:04] INFO    paloma.engines.recommendation: Recommendation engine fired 4 rule(s) ...
[18:42:05] INFO    paloma.engines.roi: ROI computed for R-001: roi=142.3%, payback=2.1 months
[18:42:07] INFO    paloma.engines.validator: Validation PASSED for offer OF-3F2A9C41 ...
[18:42:08] INFO    paloma.events.handlers: AUDIT ValidationCompleted {"offer_id": ...}
[18:42:08] INFO    paloma.services.report: Report generated -> reports/R-001-20260705-124208.md

Execution Timeline
   0.00s ├─ Architect stage                     4.21s
   0.31s │    • business_memory                 0.01s
   0.52s │    • restaurant_analytics            0.02s
   1.90s │    • crm_insights                    0.01s
   4.21s ├─ Developer stage                     6.87s
   ...
┌──────────────────────────────────────────┐
│  Run finished                            │
├──────────────────────────────────────────┤
│  Duration     : 12.40s                   │
│  LLM requests : 6                        │
│  Tokens       : 9,412 (8,102 in / 1,310 out)
│  Tool calls   : 8                        │
│  Est. cost    : $0.0132                  │
└──────────────────────────────────────────┘
```

The engines, services and data layer are fully testable **without any API key**:

```bash
pytest
```

## Directory Structure

```
paloma-ai-platform/
├── main.py                  # CLI entry point (thin: parse → container → run)
├── config/
│   └── settings.py          # Typed settings + feature flags (pydantic-settings)
├── core/
│   ├── container.py         # Composition root — all DI wiring & flag resolution
│   ├── context.py           # ExecutionContext (request id, metrics, trace)
│   ├── cache.py             # Cache protocol + in-memory TTL implementation
│   ├── exceptions.py        # Domain exception hierarchy
│   └── logging.py           # Unified observability (paloma.* logger tree)
├── models/                  # Strict Pydantic contracts (the agent protocol)
│   ├── restaurant.py        #   RestaurantMetrics
│   ├── business_case.py     #   BusinessCase, BusinessProblem, DeveloperTask
│   ├── offer.py             #   Offer, OfferRef, RoiProjection, line items
│   ├── validation.py        #   ValidationReport, ValidationIssue
│   ├── knowledge.py         #   PalomaModule, ModulePrice, KnowledgeBase
│   ├── memory.py            #   RestaurantHistory, PastOffer, PastAnalysis
│   ├── crm.py               #   CrmSnapshot
│   └── enums.py             #   Closed domain vocabularies
├── engines/                 # Deterministic computation (no I/O, no LLM)
│   ├── roi_engine.py        #   ROI / payback / revenue projections
│   ├── recommendation_engine.py  # Rule-based expert system
│   └── validator_engine.py  #   Anti-hallucination rule set
├── services/                # All I/O behind protocol-typed facades
│   ├── restaurant_service.py     # MetricsRepository: CSV / SQLite / cached
│   ├── knowledge_service.py      # Product catalog (JSON, versioned)
│   ├── offer_service.py          # Offer assembly + OfferRepository
│   ├── memory_service.py         # Business memory (engagement history)
│   ├── crm_service.py            # CRM signals (mock now, REST API next)
│   └── report_service.py         # Markdown report rendering
├── events/                  # Domain events + bus + subscribers
│   ├── events.py            #   BusinessCaseCreated, OfferCreated, ...
│   ├── bus.py               #   EventBus protocol + InMemoryEventBus
│   └── handlers.py          #   AuditLogHandler, Slack stub (extension point)
├── llm/
│   └── providers.py         # BaseLLMProvider: OpenAI/Anthropic/Gemini/OpenRouter/Ollama
├── metrics/                 # Token/cost/latency collection + console trace
│   ├── collector.py         #   MetricsCollector, RunMetrics
│   ├── tracer.py            #   Execution spans (stages + tool calls)
│   └── report.py            #   Timeline & summary rendering
├── tools/                   # Tool plugins (auto-discovered, DI-instantiated)
│   ├── base.py              #   InstrumentedTool + @register_tool
│   └── registry.py          #   ToolRegistry: discover() + create_all()
├── crew/                    # Orchestration only: agents, tasks, pipeline
│   └── prompts.py           #   Versioned PromptRepository
├── prompts/                 # Versioned backstories: <agent>_v<N>.md
├── data/                    # restaurants.csv, modules.json, prices.json, memory.json
├── reports/                 # Generated business proposals
├── tests/                   # Offline unit/integration tests (no API key needed)
└── docs/                    # architecture.md, sequence.md
```

## Agents

| Agent | Input | Tools | Output contract |
|---|---|---|---|
| **AI Architect** | `restaurant_id` | `restaurant_analytics`, `crm_insights`, `business_memory` | `BusinessCase` |
| **AI Developer** | `BusinessCase` | `module_recommendations`, `paloma365_knowledge`, `roi_calculator`, `offer_generator`, `business_memory` | `OfferRef` |
| **AI Validator** | `OfferRef` | `offer_validation` | `ValidationReport` |

Each agent gets a **least-privilege tool belt** — it can only see the tools its
role requires, which reduces both prompt size and failure surface. Backstories
are versioned files (`prompts/<agent>_v<N>.md`); the active version is the
`PROMPT_VERSION` config value, currently **v3** (grounded benchmarks, explicit
anti-fabrication rules, hard length limits). Contract enforcement is layered:
tool inputs are re-validated by the tool base class, agent outputs must parse
into `output_pydantic` contracts, and the pipeline verifies that a returned
`OfferRef` points at an offer that actually exists — a fabricated reference
fails the run with a clean `AgentContractError`, never a raw traceback.

## Tools

| Tool | Delegates to | Responsibility |
|---|---|---|
| `restaurant_analytics` | `RestaurantService` | Real metrics from the data source |
| `crm_insights` | `CrmService` | NPS, complaints, loyalty signals |
| `business_memory` | `BusinessMemoryService` | Past analyses, offers, rejections |
| `module_recommendations` | `RecommendationEngine` | Rule-based module suggestions |
| `paloma365_knowledge` | `KnowledgeService` | Verified product facts & prices |
| `roi_calculator` | `ROIEngine` | Deterministic financial projections |
| `offer_generator` | `OfferService` | Priced offer assembly & persistence |
| `offer_validation` | `ValidatorEngine` | ROI bounds, price & catalog checks |

Tools are **plugins**: each derives from `InstrumentedTool` (timing, tracing
and metrics for free), self-registers via `@register_tool`, and is discovered
and dependency-injected by `ToolRegistry` at startup. Adding a capability =
one file in `tools/` + one name in an agent's belt.

## Feature Flags

| Flag | Default | Effect |
|---|---|---|
| `USE_VALIDATOR_AGENT` | `true` | `false` skips the Validator LLM agent; `ValidatorEngine` still runs in Python (cheaper, same safety) |
| `USE_CACHE` | `true` | TTL cache over the metrics repository — one data-source read per restaurant per run |
| `USE_BUSINESS_MEMORY` | `true` | Engagement-history tool + run recording |
| `USE_SQLITE` | `false` | SQLite metrics backend instead of CSV (roadmap) |

## Multi-Model Routing

Different pipeline roles have different model requirements — pinning all
agents to one model wastes either money or quality. The `LLMRouter`
(`llm/routing.py`) maps each role to its own model via config:

| Role | Env var | Why | Temperature |
|---|---|---|---|
| Architect | `MODEL_ARCHITECT` | The diagnosis *is* the product — strongest reasoner in budget | 0.2 |
| Developer | `MODEL_DEVELOPER` | A tool-calling loop over structured data — fast, cheap, reliable | 0.1 |
| Validator | `MODEL_VALIDATOR` | Relays one deterministic verdict — cheapest model available | 0.0 |

Any role without an explicit model falls back to `LLM_MODEL`, so the
platform runs single-model out of the box and becomes multi-model with
three lines of config. Model ids are full LiteLLM paths; the vendor is
resolved by prefix (`openrouter/`, `anthropic/`, `gemini/`, `ollama/`),
unprefixed ids go to `LLM_PROVIDER`. LLM handles are built **lazily** —
commands that never call a model (`--list-restaurants`, tests) never
need a credential — and `validate()` checks every distinct vendor's key
before the first agent runs. The resolved routing table is logged at
startup.

Recommended OpenRouter setup (one key, every frontier model):

```env
LLM_PROVIDER=openrouter
LLM_MODEL=openrouter/openai/gpt-4o-mini
MODEL_ARCHITECT=openrouter/anthropic/claude-sonnet-5
MODEL_DEVELOPER=openrouter/openai/gpt-4o-mini
MODEL_VALIDATOR=openrouter/google/gemini-2.5-flash
OPENROUTER_API_KEY=sk-or-...
```

## Projection Economics

The ROI engine refuses to produce slideware numbers. Raw uplift is
discounted through three auditable levers that ship inside every
projection (`RoiAssumptions`): **gross margin** (only profit counts,
default 30%), **attribution** (only part of the uplift is credibly the
modules' doing, default 60%) and a **linear adoption ramp** (default
3 months). Combined module growth is capped at 25%. The validator
additionally enforces a hard 500% ROI credibility bound.

## Data Flow

```
restaurant_id
   → Architect  ── analytics + CRM + memory ─►  BusinessCase (typed)
   → Developer  ── rules + knowledge + ROI ──►  Offer (persisted in Python)
                                                OfferRef (returned to LLM)
   → Validator  ── narration only ───────────►  consistency-checked, never load-bearing
   → ValidatorEngine (Python) ───────────────►  authoritative ValidationReport
   → ReportService ──────────────────────────►  reports/<id>-<ts>.md + .html
```

**The verdict is never an LLM relay.** The Validator agent narrates the
machine-made report for the demo, but the pipeline always recomputes the
authoritative `ValidationReport` with `ValidatorEngine` — a model that
wraps or reshapes the JSON cannot abort or alter the outcome (observed
in production with a cost-tier model; the run now survives it with a
logged warning).

## Demo Output

Every run ends with a product-style decision funnel, an execution
timeline and a cost summary:

```
══════════════════════════════════════════════════════════════════
  PALOMA AI DECISION PIPELINE · R-001 · request 6d9ba2d5e50d
══════════════════════════════════════════════════════════════════
  RESTAURANT
    Dastarkhan Lounge — Almaty
    Revenue 13,020,000 KZT/mo · 3,100 orders · avg ticket 4,200
        ▼
  BUSINESS ANALYSIS       "Dine-in dependent venue with weak retention..."
        ▼
  PROBLEMS DIAGNOSED (4)  [HIGH] LOW_RETENTION 0.18 vs benchmark 0.25 ...
        ▼
  RECOMMENDED MODULES (2) Paloma365 Delivery · Paloma365 Kitchen Display
        ▼
  PROJECTED ROI           299.1% · payback 3.8 mo · +263,421 KZT profit/mo
        ▼
  VALIDATION              ✅ PASSED (5 rules, 0 issues)
        ▼
  REPORTS                 reports/R-001-<ts>.md · reports/R-001-<ts>.html
══════════════════════════════════════════════════════════════════
```

Two artifacts per run: a diffable **Markdown** report for analysts and a
self-contained, styled **HTML** proposal for the client (inline CSS, no
external assets, all LLM-authored text HTML-escaped).

See [docs/architecture.md](docs/architecture.md) and
[docs/sequence.md](docs/sequence.md) for the detailed diagrams.

## Roadmap

- [ ] SQLite/PostgreSQL metrics backend (`SqliteMetricsRepository` is stubbed)
- [ ] Real Paloma365 CRM API client behind the existing `CrmService` contract
- [ ] Offer outcome feedback loop (`BusinessMemoryService.record_outcome`) —
      accepted/rejected status flowing back from the sales team into memory
- [ ] Slack / e-mail subscribers on the event bus (`SlackNotificationHandler` stub exists)
- [ ] PDF offer rendering (`ReportService` extension point)
- [ ] FastAPI surface reusing the same `Container` (REST + async jobs)
- [ ] Offer revision loop: Validator failure → Developer retry with feedback
- [ ] Multi-restaurant batch mode & portfolio-level analytics

## Future Improvements

- **Observability**: export `Tracer` spans to OpenTelemetry (the span model
  maps 1:1); structured JSON logs behind a collector
- **Cost control**: per-run token budget with hard abort thresholds, on top of
  the existing per-run cost estimation
- **Event transport**: swap `InMemoryEventBus` for Kafka/RabbitMQ behind the
  same `EventBus` protocol when subscribers move out of process
- **Benchmarks**: per-city/per-segment thresholds in `RecommendationThresholds`,
  loaded from the knowledge base instead of constants
- **Human-in-the-loop**: review UI over persisted offers before sending

## License

See [LICENSE](LICENSE).

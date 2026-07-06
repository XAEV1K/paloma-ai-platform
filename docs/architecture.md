# Architecture

## 1. Design philosophy

The platform is built around one rule:

```
┌───────────────────────────────────────────────┐
│              LLM THINKS. PYTHON WORKS.        │
├───────────────────────┬───────────────────────┤
│         LLM           │        Python         │
│  analysis             │  ROI / payback math   │
│  prioritisation       │  CSV / JSON / SQL I/O │
│  decision making      │  business rules       │
│  business narrative   │  validation           │
│                       │  report rendering     │
└───────────────────────┴───────────────────────┘
```

Consequences:

- Deterministic outputs: the same restaurant always yields the same numbers.
- No numeric hallucinations: the LLM can only *quote* tool output; the
  Validator re-derives everything against the catalog.
- Minimal token spend: agents carry references (`OfferRef`), not payloads.

## 2. Layered architecture

Dependencies point strictly downwards. No layer imports from a layer above it.

```
┌──────────────────────────────────────────────────────────────┐
│  Entry Points                    main.py (CLI, thin)         │
├──────────────────────────────────────────────────────────────┤
│  Orchestration (crew/)           Agents · Tasks · Pipeline   │
│    the ONLY layer importing CrewAI orchestration primitives  │
├──────────────────────────────────────────────────────────────┤
│  Tool Layer (tools/)             CrewAI BaseTool adapters    │
│    validate LLM input → delegate → return compact JSON       │
├──────────────────────────────────────────────────────────────┤
│  Services (services/)            all I/O behind Protocols    │
│  Engines  (engines/)             pure deterministic compute  │
├──────────────────────────────────────────────────────────────┤
│  Domain Models (models/)         strict Pydantic contracts   │
│  Core (core/)                    logging · exceptions · DI   │
├──────────────────────────────────────────────────────────────┤
│  Data (data/)                    CSV · JSON · SQLite (next)  │
└──────────────────────────────────────────────────────────────┘
```

## 3. Component map

```
                       core/container.py  (composition root)
                                │  builds everything, injects downwards
        ┌───────────────────────┼──────────────────────────┐
        ▼                       ▼                          ▼
  PalomaPipeline          PipelineTools               Services
  (crew/crew.py)      (7 single-purpose tools)           │
        │                       │            ┌────────────┼────────────┐
        │                       │            ▼            ▼            ▼
        │                       │     RestaurantService  Knowledge  OfferService
        │                       │      (CSV repo, swap    Service    (assembly +
        │                       │       point: SQLite)   (catalog)   repository)
        │                       ▼
        │                    Engines (pure, no I/O)
        │            ┌──────────┼──────────────┐
        │            ▼          ▼              ▼
        │        ROIEngine  Recommendation  ValidatorEngine
        │                   Engine (rules)  (rule firewall)
        ▼
   Agents (Architect / Developer / Validator)
   built by AgentFactory from prompts/*.md
```

## 4. Contracts as the agent protocol

Agents do not chat. Each pipeline stage has a typed output enforced by
CrewAI's `output_pydantic`:

| Stage | Contract | Producer of the numbers |
|---|---|---|
| Analysis | `BusinessCase` | analytics/CRM tools (Python) |
| Development | `OfferRef` (full `Offer` stays in Python) | `OfferService` + `ROIEngine` |
| Validation | `ValidationReport` — **recomputed by `ValidatorEngine` in the pipeline**; the agent's relay is narration, consistency-checked but never load-bearing | `ValidatorEngine` |

The `OfferRef` pattern matters: the complete offer (prices, line items, ROI)
is persisted in the `OfferRepository` and never serialised into the LLM
context. Agents move an id, Python moves the data.

## 5. Event-driven core

The pipeline publishes typed domain events at every stage boundary:

```
Architect done ──► BusinessCaseCreated ──┐
Developer done ──► OfferCreated ─────────┼──► EventBus ──► AuditLogHandler (wildcard)
Validation done ─► ValidationCompleted ──┤              ├─► SlackNotificationHandler (stub)
Report written ──► ReportGenerated ──────┘              └─► <your integration here>
```

Handlers are isolated (a failing subscriber is logged and skipped, never
breaks the pipeline) and the `EventBus` protocol hides the transport —
`InMemoryEventBus` today, Kafka/RabbitMQ tomorrow, same subscribers.

## 6. Business memory

`data/memory.json` stores per-restaurant engagement history: past
diagnoses, past offers, outcomes and *explicitly rejected modules*.
Agents consult it through the `business_memory` tool (prompt v2 requires
it), so the Developer will not re-pitch a rejected module without new
evidence — and when it does, the executive summary must acknowledge the
earlier rejection and say what changed. Every pipeline run appends to
the history; the outcome feedback loop (`record_outcome`) is a roadmap
extension point.

## 7. Extension points

| Change | Where | Effort |
|---|---|---|
| CSV → SQLite/API metrics | implement `MetricsRepository`, swap in `Container.build` | 1 class |
| New tool for agents | file in `tools/` + `@register_tool` + name in a belt | 1 class |
| New pipeline subscriber | handler class + `subscribe` in `Container.build` | 1 class |
| New business rule | new `RecommendationRule` strategy, register in `DEFAULT_RULES` | 1 class |
| New validation check | new `ValidationRule` strategy, register in `DEFAULT_RULES` | 1 class |
| New Paloma365 module | add entries to `modules.json` / `prices.json` + `ModuleCode` | data + 1 enum |
| New prompt iteration | add `prompts/<agent>_v<N+1>.md`, bump `PROMPT_VERSION` | 0 code |
| Different model per agent | `.env`: `MODEL_ARCHITECT` / `MODEL_DEVELOPER` / `MODEL_VALIDATOR` | 0 code |
| Different LLM provider | `.env`: `LLM_PROVIDER` + key (`llm/providers.py` registry) | 0 code |
| PDF reports | new renderer in `ReportService` | 1 method |
| REST API surface | FastAPI app reusing `Container` | additive |

## 8. Error handling & observability

- Single exception root (`PalomaError`) with specific subtypes
  (`RestaurantNotFoundError`, `UnknownModuleError`, `OfferNotFoundError`,
  `DataSourceError`, `ConfigurationError`) — the CLI catches the root,
  bugs still crash loudly.
- Unified logger tree `paloma.*` configured once (`core/logging.py`);
  every meaningful step logs at INFO so a demo run reads like a timeline.
- Every run owns an **`ExecutionContext`** (request id, `MetricsCollector`,
  `Tracer`) propagated via `contextvars` — tools record spans and timings
  without signature pollution, async-safe by construction.
- The CLI ends with an **execution timeline** (stage + tool spans) and a
  **run summary box** (duration, LLM requests, tokens, tool calls,
  estimated cost).
- Source data is validated by Pydantic **at the boundary** (CSV row →
  `RestaurantMetrics`), so bad data fails fast with a precise message.

## 9. Multi-model routing

One model for all agents wastes either money or quality. Each role is
routed independently (``llm/routing.py``):

```
Architect  ──►  strongest reasoner        (MODEL_ARCHITECT,  T=0.2)
Developer  ──►  fast tool-caller          (MODEL_DEVELOPER,  T=0.1)
Validator  ──►  cheapest relay            (MODEL_VALIDATOR,  T=0.0)
                       │
                       ▼
        provider resolved by model-id prefix
   (openrouter/ · anthropic/ · gemini/ · ollama/ · default)
```

LLM handles are built lazily (no credential needed until a model is
actually called) and validated eagerly before the first agent runs.
The economics of every projection are governed by ``RoiAssumptions``
(gross margin, attribution, adoption ramp) so no agent — and no naive
formula — can produce a 4945% ROI again.

## 10. Cost model

Token spend is bounded by design:

1. Agents receive compact JSON (metrics snapshot ≈ 300 tokens, not a CSV dump).
2. Heavy artifacts (offers, reports) never enter the context window.
3. `max_iter` caps tool-use loops per agent.
4. Metrics reads are cached (`USE_CACHE`): the Developer's re-fetch of what
   the Architect already read is served from the TTL cache.
5. The Validator *agent* is optional (`USE_VALIDATOR_AGENT=false` keeps the
   deterministic firewall, drops the LLM narration around it).
6. Cost is measured, not guessed: each run reports tokens and — when the
   operator configures `LLM_PRICE_*` — an estimated dollar cost.

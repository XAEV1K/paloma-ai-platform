# Sequence: one full pipeline run

`python main.py --restaurant-id R-001`

```
 USER      main.py     Container   Pipeline    Architect   Developer   Validator   Services/Engines
  │           │            │           │           │           │           │              │
  │ run R-001 │            │           │           │           │           │              │
  ├──────────►│  build()   │           │           │           │           │              │
  │           ├───────────►│ wire DI   │           │           │           │              │
  │           │◄───────────┤           │           │           │           │              │
  │           │ run(R-001) │           │           │           │           │              │
  │           ├───────────────────────►│ kickoff   │           │           │              │
  │           │            │           ├──────────►│           │           │              │
  │           │            │           │           │ restaurant_analytics(R-001)          │
  │           │            │           │           ├─────────────────────────────────────►│ CSV → RestaurantMetrics
  │           │            │           │           │◄─────────────────────────────────────┤ (validated JSON)
  │           │            │           │           │ crm_insights(R-001)                  │
  │           │            │           │           ├─────────────────────────────────────►│ CrmSnapshot
  │           │            │           │           │◄─────────────────────────────────────┤
  │           │            │           │           │ ✦ reasons, diagnoses ✦               │
  │           │            │           │◄──────────┤ BusinessCase (output_pydantic)       │
  │           │            │           ├──────────────────────►│                          │
  │           │            │           │           │           │ module_recommendations   │
  │           │            │           │           │           ├─────────────────────────►│ rule engine fires
  │           │            │           │           │           │◄─────────────────────────┤ [DELIVERY, CRM_LOYALTY, ...]
  │           │            │           │           │           │ paloma365_knowledge      │
  │           │            │           │           │           ├─────────────────────────►│ catalog facts (JSON)
  │           │            │           │           │           │◄─────────────────────────┤
  │           │            │           │           │           │ roi_calculator(bundle)   │
  │           │            │           │           │           ├─────────────────────────►│ ROIEngine: math
  │           │            │           │           │           │◄─────────────────────────┤ RoiProjection
  │           │            │           │           │           │ ✦ selects bundle,        │
  │           │            │           │           │           │   writes summary ✦       │
  │           │            │           │           │           │ offer_generator(...)     │
  │           │            │           │           │           ├─────────────────────────►│ OfferService: price,
  │           │            │           │           │           │                          │ project, persist
  │           │            │           │           │           │◄─────────────────────────┤ OfferRef (id only!)
  │           │            │           │◄──────────────────────┤ OfferRef (output_pydantic)
  │           │            │           ├──────────────────────────────────────►│         │
  │           │            │           │           │           │  offer_validation(id)    │
  │           │            │           │           │           │           ├─────────────►│ ValidatorEngine:
  │           │            │           │           │           │           │              │ 5 deterministic rules
  │           │            │           │           │           │           │◄─────────────┤ ValidationReport
  │           │            │           │◄──────────────────────────────────────┤         │
  │           │            │           │ get_offer(offer_id)   │           │              │
  │           │            │           ├─────────────────────────────────────────────────►│ full Offer (from Python,
  │           │            │           │◄─────────────────────────────────────────────────┤  never through the LLM)
  │           │            │           │ render(case, offer, report)                      │
  │           │            │           ├─────────────────────────────────────────────────►│ ReportService → .md
  │           │◄───────────────────────┤ PipelineResult        │           │              │
  │◄──────────┤ summary + report path  │           │           │           │              │
```

`✦ ... ✦` marks the only places where the LLM actually thinks. Everything
else is deterministic Python.

## Events published along the way

Each stage boundary emits a typed domain event onto the `EventBus`
(consumed today by the audit log; tomorrow by Slack/analytics/CRM
subscribers — zero pipeline changes):

```
Architect done  ─► BusinessCaseCreated(request_id, restaurant_id, headline, problem_count)
Developer done  ─► OfferCreated(request_id, offer_id, module_codes, roi_pct)
Validation done ─► ValidationCompleted(request_id, offer_id, status, issue_count)
Report written  ─► ReportGenerated(request_id, offer_id, report_path)
```

After `ReportGenerated`, the run is appended to the business memory
(`data/memory.json`) so the next engagement with this restaurant starts
with full history: prior problems, prior offers, rejected modules.

## Failure paths

| Failure | Detected by | Outcome |
|---|---|---|
| Unknown restaurant id | `CsvMetricsRepository` | `RestaurantNotFoundError` → CLI exit 1 with a clear message |
| Malformed CSV row | Pydantic at load time | `DataSourceError` before any agent runs |
| Agent invents a module | `RoiInput`/`OfferInput` enum validation | Tool call rejected, agent must correct itself |
| Agent invents a price | `ValidatorEngine.PriceConsistencyRule` | `ValidationReport: FAILED`, offer blocked |
| Implausible ROI | `ValidatorEngine.RoiBoundsRule` | `ValidationReport: FAILED`, offer blocked |
| Agent output ≠ contract | `output_pydantic` + `_typed_output` | Pipeline aborts loudly (no silent garbage) |

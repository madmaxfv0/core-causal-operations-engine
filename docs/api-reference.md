# API reference

All routes are defined in `backend/api/main.py` and return JSON unless noted. There is no authentication; see [configuration.md](configuration.md) for the optional shared password and public-demo mode. Interactive OpenAPI documentation is served by FastAPI at `/docs` on a running instance.

Example payloads below were captured from a local run on the bundled synthetic data set and shortened.

## Conventions

- Errors are returned as `{"detail": "..."}` or `{"error": "..."}` with a 4xx status. Tracebacks are never sent to the client.
- In public-demo mode, blocked requests return `403` with `{"error": "...", "demo_mode": true}`.
- Long operations return a job id; poll `GET /api/jobs/{job_id}` until `COMPLETE` or `FAILED`.
- Monetary and rate fields that are estimates come with `_lo` / `_hi` bounds and a `confidence` label.

## Endpoints

### Service and context

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness check (always open) |
| GET | `/api/meta` | Product, model version, active data set, settings |
| GET | `/api/data/context` | Active data set, its counts and which domains are available |
| GET, POST | `/api/data/mode` | Read or switch between synthetic and real data mode |
| GET | `/api/jobs/{job_id}` | Background job status |
| GET, PUT | `/api/settings` | Read or update settings (economics, causal, portfolio) |
| POST | `/api/settings/reset` | Restore default settings |
| GET | `/api/search` | Search wells, interventions and documents |

### Field, wells and causal analysis

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/overview` | Field KPIs, trend and review queue |
| GET | `/api/wells` | Well list |
| GET | `/api/wells/{well_id}` | One well: production, baseline, jobs, documents |
| GET | `/api/wells/{well_id}/causal` | Counterfactual analysis for an event (`pre_end`, `post_start`, optional `model`, windows) |
| POST | `/api/wells/{well_id}/causal/run` | Run an analysis with chosen parameters |
| POST | `/api/wells/{well_id}/donors` | Force or exclude comparison wells |
| GET | `/api/eligibility-rules` | Rules for comparison-well eligibility |
| GET | `/api/interventions` | All analysed jobs with naive and causal gains |
| GET | `/api/interventions/{intervention_id}` | One job with its evidence |
| GET, POST | `/api/intervention-outcomes` | Recorded outcomes of approved jobs |
| GET | `/api/idle`, `/api/idle/{well_id}` | Idle-well screen and detail |
| GET | `/api/ghost`, `/api/ghost/{well_id}` | Underperformance screen and detail |
| GET | `/api/water` | Water economics and facility utilisation |
| POST | `/api/water/shutoff-scenario` | Evaluate a water shut-off scenario |
| GET | `/api/network` | Facility network layout |
| GET | `/api/quality` | Data-quality report |

### Portfolio

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/portfolio/candidates` | Candidate jobs |
| POST | `/api/portfolio/optimise` | Solve the programme under the given constraints |
| POST | `/api/portfolio/compare` | Compare the optimised plan with baseline rules |
| POST | `/api/portfolio/sensitivity` | Sensitivity (tornado) of the plan |
| POST | `/api/portfolio/plan-state` | Lock, remove or move jobs |
| POST | `/api/portfolio/manual-job` | Add a manual job |
| POST | `/api/portfolio/scenarios` | Save a scenario |
| DELETE | `/api/portfolio/scenarios/{scenario_id}` | Delete a scenario |

### Decisions, notes and runs

| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/api/decisions` | Decision log (accept, modify, reject, defer) |
| GET | `/api/decisions/model-vs-engineer` | Where the engineer and the model disagreed |
| GET | `/api/decisions/export.csv` | Decision log as CSV |
| POST | `/api/notes/{entity_id}` | Attach a note |
| POST | `/api/reviewed/{entity_id}` | Mark as reviewed |
| GET | `/api/runs`, `/api/runs/{analysis_id}` | Cached causal runs with parameters and versions |
| GET | `/api/export/analysis/{analysis_id}.json` | One analysis as JSON |
| GET | `/api/export/well/{well_id}/report.pdf` | Well report (PDF) |

### Validation and copilot

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/validation/{name}` | `planted-truth`, `blind-test`, `placebo`, `calibration`, `reason-accuracy`, `model-cards`, `sensitivity` |
| GET | `/api/pilot/scorecard` | Pilot scorecard |
| POST | `/api/copilot/ask` | Explain a ranking or recommendation |

### Document archive

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/archive/documents`, `/api/archive/documents/{doc_id}` | Documents and their extractions |
| POST | `/api/archive/upload` | Upload a document |
| POST | `/api/archive/documents/{doc_id}/extract` | Run extraction |
| POST | `/api/archive/documents/{doc_id}/review` | Approve, edit, reject or mark unreadable |
| GET | `/api/archive/search` | Search extracted text with citations |
| GET | `/api/archive/records` | Approved structured records |
| GET | `/api/archive/file/{doc_id}` | Original file |

### Data management

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/data/connectors` | Available connectors and their state |
| POST | `/api/data/connectors/{cid}/{action}` | Run a connector action |
| GET | `/api/data/sample-schema.csv` | Sample import schema |
| POST | `/api/data/import/preview`, `/validate`, `/ingest`, `/interventions` | CSV / XLSX import steps |
| POST | `/api/data/activate/{name}` | Make a data set active |
| POST | `/api/evidence/rebuild` | Rebuild the evidence base (background job) |
| POST | `/api/demo/reset` | Restore demo state |
| GET | `/api/demo/script` | Data for the guided walkthrough |

### Alberta map and telemetry

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/alberta/status` | Which public sources are installed |
| POST | `/api/alberta/sync/{kind}` | Download or refresh a source (background job) |
| GET | `/api/map/summary` | Headline counts |
| GET | `/api/map/wells` | Wells or clusters for a viewport |
| GET | `/api/map/overlays/{kind}` | Facilities or pipelines |
| GET | `/api/map/search` | Find a well by identifier, location or operator |
| GET | `/api/map/wells/{record_id}` | One well |
| GET | `/api/map/provenance/{record_id}` | Where each field of that record came from |
| GET | `/api/map/wells/{record_id}/calculator-inputs` | Inputs for the scenario calculator |
| POST | `/api/map/wells/{record_id}/scenario` | Evaluate a scenario for that well |
| GET | `/api/map/join-report` | How many wells were linked to reported volumes, and why others were not |
| GET | `/api/scada/status` | Whether a telemetry gateway is connected |
| GET | `/api/scada/wells/{well_id}/telemetry` | Telemetry for a well, when connected |

## Examples

### One intervention

`GET /api/interventions/INT-002` → `row`:

```json
{
  "intervention_id": "INT-002",
  "well_id": "SYN-008",
  "date": "2021-01",
  "type": "workover",
  "cost": 170400.0,
  "cost_source": "RECORD",
  "pre_rate_bpd": 19.75,
  "post_rate_bpd": 36.06,
  "naive_gain_bpd": 16.31,
  "causal_gain_bpd": 11.8,
  "gain_lo_bpd": 7.11,
  "gain_hi_bpd": 16.49,
  "payback_months": 9,
  "confidence": "HIGH CONFIDENCE",
  "model": "synthetic_control",
  "donor_count": 25,
  "pre_r2": 0.713,
  "analysis_id": "run_2fb1133733f7fcf9"
}
```

The before/after gain is 16.31 bbl/d; the causal estimate is 11.8 (7.11 to 16.49). On synthetic data the response also carries the planted truth for that job (12.38 bbl/d here) so the interface can show it in the Model lab.

### Optimise a programme

`POST /api/portfolio/optimise`

```json
{ "budget": 200000 }
```

Optional fields: `crews`, `rigs`, `horizon_months`, `max_concurrent`, `min_npv`, `risk_tolerance`, `objective` (default `"npv"`). Omitted fields take the values in Settings.

Response (shortened):

```json
{
  "status": "Optimal",
  "objective": "npv",
  "quarters": 4,
  "kpi": {
    "available": 62,
    "eligible": 27,
    "budget": 200000.0,
    "selected": 8,
    "investment": 200000.0,
    "expected_oil_bpd": 152.9,
    "expected_value": 3497412.0,
    "value_lo": 2174885.0,
    "value_hi": 4329201.0
  },
  "selected": [
    {
      "candidate_id": "IDLE-SYN-050",
      "well_id": "SYN-050",
      "module": "idle",
      "action": "pump_replacement",
      "cost": 45000.0,
      "npv": 927860.0,
      "npv_lo": 571311.0,
      "npv_hi": 1040767.0,
      "oil_bpd": 35.3,
      "crew_type": "rigless",
      "risk": 0.12,
      "confidence": "HIGH CONFIDENCE",
      "quarter": 0,
      "locked": false
    }
  ],
  "excluded": [],
  "not_selected": []
}
```

`excluded` entries carry an `excluded_reason`.

### Ask the copilot

`POST /api/copilot/ask`

```json
{ "question": "Why is SYN-050 ranked first?" }
```

```json
{
  "well_id": "SYN-050",
  "recommendation": "ACT — pump replacement; expected 35.3 bbl/d (range 23.3–39.1), expected NPV 936,669.",
  "evidence": [
    "8 comparable historical restarts",
    "estimated shut-in reason MECHANICAL (STRONG INFERENCE)",
    "operating hours fell to 266 h in the final month (avg 720 h)"
  ],
  "uncertainty": "HIGH CONFIDENCE; restart sustain probability 88% from analogues",
  "economic_assumptions": "Illustrative public assumptions (oil price, netback, intervention costs) — editable in Settings.",
  "mode": "deterministic"
}
```

`mode` is `deterministic` unless LLM rephrasing is switched on.

### Validation

`GET /api/validation/planted-truth` → `metrics`:

```json
{
  "core":  { "mae": 2.18, "bias": 1.0,  "coverage_80": 0.91, "spearman": 0.801 },
  "naive": { "mae": 3.14, "bias": 1.64, "coverage_80": null, "spearman": 0.765 },
  "zero_effect_jobs": { "n": 19, "core_mean": 0.56, "naive_mean": 0.54 }
}
```

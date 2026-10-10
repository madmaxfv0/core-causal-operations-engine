# Configuration

CORE needs no configuration to run the bundled demo. Everything below is optional and read from the environment; [`.env.example`](../.env.example) lists the same variables.

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `CORE_DATA_DIR` | `./data` | Root of all data and state. |
| `LLM_PROVIDER` | `mock` | Who structures uploaded documents: `mock`, `anthropic`, `openai` or `local`. |
| `ANTHROPIC_API_KEY` | — | Required for `anthropic`. |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model used for extraction. |
| `OPENAI_API_KEY` | — | Required for `openai`. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for extraction. |
| `LOCAL_LLM_URL` | — | Required for `local`: an OpenAI-compatible chat-completions URL. |
| `LOCAL_LLM_MODEL` | `llama3` | Model name sent to the local endpoint. |
| `COPILOT_LLM` | `0` | `1` lets Anthropic rephrase the copilot's answer (needs `ANTHROPIC_API_KEY`). |
| `SCADA_HTTP_URL` | — | Base URL of an operator telemetry gateway. |
| `SCADA_PROVIDER` | — | Label shown for that source. |
| `CORE_PUBLIC_DEMO` | off | `1` blocks the endpoints that reset, rebuild, ingest or re-point shared data. |
| `CORE_ACCESS_PASSWORD` | — | Puts the whole app behind one shared password (HTTP Basic, any user name). |
| `AER_WELL_LICENCE_URL`, `AER_ABANDONED_URL`, `AER_CASING_FAILURES_URL`, `AER_VENT_FLOW_URL`, `AER_ST37_CRS` | built-in | Overrides for individual Alberta public-data sources. |
| `PORT` | `8000` | Used by `scripts/start_demo.sh`. |

API keys are read from the environment only. They are never written to disk or returned by the API.

## Language models: what is and is not used

CORE does not include a trained or fine-tuned model of its own. Language models are an optional integration with two narrow jobs.

| Use | Default | With a provider configured |
|---|---|---|
| Document extraction (`backend/archive/providers.py`) | `mock`: regular-expression patterns for Russian, Azerbaijani and English report layouts. Works offline. A field it cannot read stays empty. | The document text is sent to the chosen provider with a fixed system prompt and must come back as JSON matching the extraction schema. |
| Copilot (`backend/core/copilot.py`) | Deterministic text assembled from the evidence base. | With `COPILOT_LLM=1`, Anthropic rephrases that text. It is instructed not to add or change numbers. |

The model has no tools and no access to the data store. It sees only the text of one document, or one prepared evidence summary. Every economic figure in CORE is computed by the engine.

Only the offline `mock` provider is covered by the test suite.

## OCR

Scanned documents go through Tesseract. Languages are requested as `rus+aze+eng`; a missing language pack degrades to manual review. The Docker image installs all three packs.

## Public-demo mode

With `CORE_PUBLIC_DEMO=1` these requests return `403` with an explanatory message:

- `POST /api/demo/reset`
- `POST /api/evidence/rebuild`
- `POST /api/alberta/sync/{kind}`
- `POST /api/data/mode`, `POST /api/data/activate/{name}`
- `POST /api/data/connectors/{id}/{action}`
- `POST /api/data/import/{preview|validate|ingest|interventions}`
- `POST /api/archive/upload`, `POST /api/archive/documents/{id}/{extract|review}`

`GET /healthz` always answers without credentials.

## Telemetry gateway

Disconnected by default. With `SCADA_HTTP_URL` set, CORE calls `GET /health` and `GET /wells/{well_id}/telemetry` on the gateway. If the health check fails, values show as unavailable. See [scada-integration.md](scada-integration.md).

## Deployment

`Dockerfile`, `fly.toml` and `deploy/deploy_fly.sh` package CORE as one container on Fly.io with `CORE_PUBLIC_DEMO=1`. The image contains the built interface, the processed data and the Alberta cache, and installs dependencies from `deploy/requirements.lock`. The demo machine stops when idle and wakes on the next request.

The Docker build was not re-run when this repository was prepared; no Docker runtime was available.

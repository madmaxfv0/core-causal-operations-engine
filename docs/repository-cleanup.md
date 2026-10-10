# Repository cleanup

What changed when the working folder was turned into this repository. The working folder had no git history.

## Choosing the baseline

Two copies existed: the `core` folder and an archive of it made a day earlier. The folder is the newer of the two and already contained the deployment files, so it is the baseline.

## Renamed

| Before | After |
|---|---|
| `docs/ALBERTA_MAP.md` | `docs/alberta-map.md` |
| `docs/CLOSED_LOOP_LEARNING.md` | `docs/closed-loop-learning.md` |
| `docs/DATA_SOURCES.md` | `docs/data-sources.md` |
| `docs/REAL_DATASET_CHOICE.md` | `docs/real-dataset-choice.md` |
| `docs/SCADA_INTEGRATION.md` | `docs/scada-integration.md` |
| `docs/button_audit.md` | `docs/button-audit.md` |
| `CORE_DATA_QA_GUIDE.txt` | `docs/data-qa-guide.md` (headings converted to Markdown) |

References updated: `backend/data/alberta.py` (docstring), `docs/alberta-map.md` (link), `scripts/button_audit.py` (output path).

Python modules, React components and data files kept their names. Downloaded data keeps its original file names.

## Left out

| Item | Reason |
|---|---|
| `.venv/`, `frontend/node_modules/`, `__pycache__/`, `.pytest_cache/` | Environments and generated files. |
| `data/raw/` (Petrinex monthly archives, about 120 MB) | Re-downloadable with `scripts/fetch_petrinex.py`; already git-ignored. |
| `data/alberta/raw/`, `data/alberta/cache/` (about 200 MB) | Re-downloadable with `scripts/update_alberta_data.py`; already git-ignored. |
| `data/processed/cache/run_*.json` (over 2,000 files) | Per-run cache, regenerated on demand; already git-ignored. |
| `deploy/.app_name` | Local deployment state; already git-ignored. |
| `docs/LINKEDIN_DESCRIPTION.md` | A social-media draft, not project documentation. |

Nothing was deleted from the original folder.

## Code changes

`frontend/smoke.mjs`:

- reads the API address from `SMOKE_BASE` (default unchanged: `http://127.0.0.1:8000`);
- exits with a non-zero status when a route fails, so CI can use it.

`backend/archive/extraction.py`, `backend/api/main.py`, `data/demo/documents/registry.json`:

- **Bug fix.** The bundled document registry stored the absolute path of each file on the machine it was created on, so opening or re-extracting a bundled document failed anywhere else. `stored_file()` now falls back to looking the file up by name in the document folders, the file endpoint returns 404 instead of an error when a file is missing, and the registry's paths are relative. Covered by `backend/tests/test_archive_paths.py`.

## Added

- `README.md` rewritten; `docs/architecture.md`, `docs/api-reference.md`, `docs/configuration.md`.
- `docs/screenshots/` — eleven screenshots taken from a local run.
- `.env.example`, `.github/workflows/ci.yml`, `backend/tests/test_archive_paths.py`.

## Figures corrected against the running engine

The earlier README quoted some figures from an older build. They were replaced with the current output:

| Figure | Earlier text | Current output |
|---|---|---|
| Tests | 68 | 100 (97 existing, 3 added) |
| Interactive controls audited | 240 | 249 |
| Smoke-test routes | 35 | 36 |
| Placebo wells | n = 850, mean 0.04, sd 3.47 | n = 870, mean −0.04, sd 4.20 |
| Blind-test cut-off | 2023-12 | 2024-01 |

The planted-truth, blind-test rank, reason-accuracy and budget-slider figures matched and are unchanged.

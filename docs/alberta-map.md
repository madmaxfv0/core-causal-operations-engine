# Alberta Well Intelligence Map

The map at `/map` is a **read-only public-data view of Alberta**. Every dot is a real
Alberta Energy Regulator well record, drawn at the AER's own published coordinates.
Where a reported production record can be attributed to that well without ambiguity,
Petrinex volumes are shown alongside it.

There is no fallback generator anywhere in this pipeline. A value with no public
source reads **Not publicly available**.

---

## 1. What the map is built from

| Layer | Source | What it provides | How it is refreshed |
|---|---|---|---|
| Wells | **AER ST37 — List of Wells in Alberta** (AER's public ArcGIS Feature Service) | WGS84 location, AER well category, surface legal location | In-app, or `--source st37` |
| Facilities | **AER ST102 — Facility List** | Batteries, gas plants, injection/disposal facilities with operator and status | In-app, or `--source facilities` |
| Pipelines | **AER Pipeline Segments** | Licensed segments with substance, licensee and status | In-app, or `--source pipelines` |
| Production | **Petrinex Alberta Public Data — Conventional Volumetrics** | Reported monthly oil / gas / water / injection volumes per well | In-app, or `--petrinex N` |
| Casing failures | **AER Well Casing Failures Report** | Reported casing failures, updated daily by AER | In-app, or `--source casing_failures` |
| Vent flow / gas migration | **AER Vent Flow / Gas Migration Report** | Surface casing vent flow and gas migration reports, updated daily by AER | In-app, or `--source vent_flow` |
| Well licences | **AER Well Licence List** | Licence number, licensee, well name | File import (`--file licences=…`) — see note below |
| Abandoned wells (dedicated dataset) | **AER Abandoned Well Spatial Data** | A standalone abandonment-event record, if AER publishes one as a direct download | File import (`--file abandoned=…`) — see note below |

AER open data is published under the Open Government Licence — Alberta. Petrinex
public data is published under the [Petrinex terms](https://www.petrinex.ca/terms).

The first six are refreshable directly from the application. ST37/ST102/pipelines are
AER's own open ArcGIS services; casing failures and vent flow/gas migration are AER's
own daily-updated CSVs (`www2.aer.ca/t/Production/views/COM-*Report/*.csv`, found on
AER's [General Well Data](https://www.aer.ca/data-and-performance-reports/activity-and-data/lists-and-activities/general-well-data)
page) — the app downloads them directly, no manual step needed.

The remaining two are not wired to a live download:

* **Well licences** — AER's General Well Data page does not currently list a
  standalone direct-download licence file. ST37 already carries operator and
  lifecycle status per well, so this source adds little the map doesn't already show.
* **Abandoned wells (dedicated dataset)** — ST37's `Well_Category` already reports an
  `Abandoned` lifecycle state per well (242,970 of the 475,125 imported wells; see the
  map's **Abandoned** status filter). This source would only add a separate
  abandonment-event record, if AER ever publishes one as a direct download.

Both still accept a manually downloaded file via `--file licences=…` / `--file abandoned=…`
if AER adds one, or if you have an internal copy.

**A note on network access.** `casing_failures` and `vent_flow` are hosted on a
Tableau-served AER domain (`www2.aer.ca`) that returns `403 Forbidden` to this
development sandbox's network regardless of headers used — confirmed with `curl`, a
real browser, and Anthropic's own fetch infrastructure. This reads as an edge
network-reputation block (the identical AER ArcGIS services on `services2.arcgis.com`
are not blocked), not an authentication wall, and the same URL is expected to work from
an ordinary residential or office connection. If **Install** fails in your environment
too, download the CSV in a browser from the landing page shown next to the button and
import it with `--file casing_failures=/path/to/file.csv` — the previously validated
cache (if any) is never touched by a failed download.

## 2. Installing the data

**From the UI** — `/map` → **Data sources & updates** → *Install* / *Refresh* on each
source. The Petrinex row has a month selector (3 / 6 / 12 / 24 / 36); the number you
pick is the history window that gets downloaded, and every production chart, trend and
calculator baseline is recomputed from it.

**From the CLI:**

```bash
python scripts/update_alberta_data.py --status                  # what is installed
python scripts/update_alberta_data.py --all                     # everything + 12 months of Petrinex
python scripts/update_alberta_data.py --source st37              # one ArcGIS-served AER source
python scripts/update_alberta_data.py --source casing_failures  # one direct-download AER CSV
python scripts/update_alberta_data.py --petrinex 24 --end-month 2026-07
python scripts/update_alberta_data.py --file abandoned=/path/to/report.csv   # manual fallback / file-only sources
```

A full first install downloads ~475,000 well records and ~1.7M monthly volume rows;
budget roughly 8–10 minutes on a normal connection.

## 3. Reliability

The refresh path is written so that a bad network day cannot damage a working demo:

```
Official source
      │
      ▼
Download (connect 30 s / read 180–600 s, 4 attempts, exponential backoff)
      │
      ▼
Schema validation ── required field missing? ──▶ abort, keep previous cache
      │
      ▼
Row validation (coordinates in Alberta, identifiers parseable, duplicates counted)
      │
      ▼
Write to a staging directory, then atomic rename
      │
      ▼
Previous cache removed only after the new one is in place
```

Consequences that matter in a demo:

* A failed refresh leaves the **last known good** dataset active and reports the failure.
* A partial download is never promoted: the zip is integrity-checked before it replaces
  the previous file, and parquet caches are swapped by directory rename.
* If AER changes a column name, the import aborts with a message naming the missing
  field rather than importing corrupted rows.
* Downloaded source files are kept under `data/alberta/raw/` with their SHA-256, the
  retrieval timestamp and the source's own last-edit date, and are git-ignored.

## 4. Performance

ST37 is ~475,000 wells. Nothing in the design ever ships that to a browser.

* **Viewport queries.** The map requests only the current bounding box.
* **Server-side clustering.** Below zoom 11 the API returns grid-aggregated clusters
  (a few hundred circles) instead of individual features; cell size shrinks with zoom.
* **Bounded feature payloads.** Above zoom 11 the response is capped at 4,000 features
  and says `truncated: true` when more exist.
* **GL rendering.** Wells are one GeoJSON source drawn as GL circles — not DOM markers.
* **In-process caches.** Parquet caches and the ST37 ↔ Petrinex join are memoised on
  file mtime, so a viewport query is a numpy mask over pre-joined arrays.
* **Code splitting.** MapLibre (~800 kB) loads only on `/map`.
* **Pipeline extents** are precomputed at ingest so overlay queries are vectorised.

## 5. Identity and the production join

The two datasets identify the same physical location in two different notations:

* AER ST37 publishes a surface location such as `11-32-040-11W4`
  (legal subdivision – section – township – range + meridian).
* Petrinex publishes a 16-character Alberta UWI such as `100031106504W400`
  (location exception + LSD + section + township + range + meridian + event sequence).

Both encode the identical **Alberta Township System** cell, so the join is a
structural identifier join — never a fuzzy name match. `backend/data/ats.py` parses
both notations into one canonical cell.

**The link must be unique in both directions.** A legal subdivision is linked only when
it holds exactly one AER ST37 record *and* exactly one reporting Petrinex well.
Otherwise the reported volume could not be attributed to a single map point, and the
well shows `Not publicly available` with the reason. On the September 2026 data that
excludes 16,379 ambiguous Petrinex cells and 214,183 ST37 records that share a
subdivision — all of it reported in **Data sources & updates → Join validation** rather
than hidden.

## 6. What is measured, calculated, and unavailable

| Category | Examples |
|---|---|
| **REPORTED** | ST37 coordinates and well category; Petrinex monthly oil/gas/water volumes and producing hours |
| **CALCULATED** | Derived status/fluid (documented rule on the AER category); average daily rate = reported monthly volume ÷ calendar days; water cut; 3-month vs prior-month decline |
| **NOT AVAILABLE** | Tubing / casing / annulus / bottom-hole pressure, wellhead and motor temperature, choke position, pump frequency, motor current, vibration, ESP intake and discharge pressure, facility fluid capacity, bottom-hole location, spud/completion dates, field and pool |

Every well panel carries a **Data sources** tab naming the dataset, value type,
retrieval time and source edit date behind each group of values, and
`GET /api/map/provenance/{record_id}` returns the row-level trace for debugging.

Derived status rule: the AER `Well_Category` string is read for a lifecycle word —
`Abandoned`, `Suspended`, `Drilled and Cased`, `Surface Casing Only`; every other
reported category is shown as *Active*, and `Undefined` as *Not reported*. The fluid
word (`Oil`, `Gas`, `Crude bitumen`, `Injection`, `Disposal`, `Observation`) is read
the same way. Marker colours encode that reported category — **not** a risk score.

Water cut is undefined, not zero, unless both liquid phases were reported and some
liquid was actually produced. A missing water declaration never reads as "no water".

## 7. Public data is not SCADA

Alberta public data is a **monthly regulatory declaration**. It is not telemetry, and
the product never labels it as such. There is no public source for a private operator's
real-time measurements, so the map shows them as *Not publicly available* and the
calculator refuses to populate them:

> SCADA value unavailable. Enter manually, or connect a SCADA/historian source.
> CORE does not substitute a generated number for a missing measurement.

`docs/scada-integration.md` describes how a real operator connector would be added.

## 8. API

| Route | Purpose |
|---|---|
| `GET /api/alberta/status` | Installed sources, Petrinex window, summary, join report |
| `POST /api/alberta/sync/{kind}` | Refresh one source (`st37`, `facilities`, `pipelines`, `petrinex`); returns a job id |
| `GET /api/map/summary` | Every headline number, computed from imported rows |
| `GET /api/map/wells?bbox&zoom&status&fluid&operator&layer&producing&q` | Viewport: clusters or features |
| `GET /api/map/overlays/{facilities\|pipelines}?bbox` | Real AER overlays |
| `GET /api/map/search?q` | Exact-identifier friendly search |
| `GET /api/map/wells/{record_id}` | Full public record with per-value provenance |
| `GET /api/map/wells/{record_id}/calculator-inputs` | What public data can and cannot fill |
| `POST /api/map/wells/{record_id}/scenario` | Economics engine on the reported baseline |
| `GET /api/map/provenance/{record_id}` | Row-level source trace |
| `GET /api/map/join-report` | ST37 ↔ Petrinex join statistics |

## 9. Coordinate systems

Geometry is requested from AER's service already in EPSG:4326 (`outSR=4326`), so no
projection is ever guessed locally. For a file import that declares a projected CRS,
set `AER_ST37_CRS` (for example `EPSG:3400`) and the importer transforms with `pyproj`
and records the declared CRS in the cache metadata. It never infers one.

## 10. Disclaimer used in the product

> Public well and production information is sourced from Alberta Energy Regulator and
> Petrinex public datasets. Availability and reporting frequency vary by dataset.
> Monthly reported volumes are not real-time production.

# Connecting real SCADA / historian data

The Alberta map runs on **public regulatory data only**. Private operator telemetry has
no public source, so the platform reports it as *Not publicly available* rather than
generating a substitute. This document describes how a real connector would be added.

## 1. Where telemetry would attach

```
AER ST37 ─────────────┐
AER ST102 / pipelines ┤
Petrinex volumetrics ─┤
Operator SCADA ───────┤   ◀── the connector described here
Operator historian ───┤
Manual entry ─────────┘
            │
            ▼
   Identity + validation layer      backend/data/ats.py, alberta.py
            │
            ▼
      Unified well state
            │
   ┌────────┼────────────┬───────────────┐
   ▼        ▼            ▼               ▼
  Map   Well record   Calculators   Provenance panel
```

Today the "operator SCADA" branch is unimplemented on purpose. Everything downstream
already carries a `value_type` (`REPORTED` / `CALCULATED` / `NOT AVAILABLE`) and a
source block, so a connector only has to supply values with that same metadata — no
consumer needs to change.

## 2. The connector contract

A connector supplies point-in-time and historical values for a tag, plus a health
check. Conceptually:

```python
class SCADAConnector(Protocol):
    def health_check(self) -> dict: ...
    def get_latest_tag(self, tag: str) -> Observation: ...
    def get_tag_history(self, tag: str, start, end, interval) -> list[Observation]: ...
    def get_well_telemetry(self, well_id: str) -> dict[str, Observation]: ...
```

Every `Observation` must carry the metadata the rest of the product already expects:

```
value            unit             timestamp
measurement_type source_system    source_tag
quality          GOOD | SUSPECT | BAD | MISSING | STALE
value_type       MEASURED
```

A value without a timestamp and a quality flag must not be accepted: the calculators
lower their stated confidence when an input is stale or suspect, and they cannot do
that if the metadata is missing.

## 3. Integration options

### Option A — OPC UA

```
Field PLC / RTU  →  SCADA  →  OPC UA server  →  OPC UA adapter  →  telemetry service
```

Read-only subscription on a browse path per well. Suits near-real-time values.

### Option B — AVEVA PI / PI Web API

```
Sensors  →  SCADA  →  AVEVA PI  →  PI Web API  →  historian adapter
```

Best fit for history: interpolated and recorded values with server-side aggregation,
which is what baselines and trend analysis want.

### Option C — REST middleware

```
SCADA  →  operator middleware  →  REST API  →  platform
```

The usual choice when the operator will not expose control-system protocols. The
middleware owns the security boundary.

### Option D — CSV / SQL export

Batch drop or a read-only reporting database. Lowest integration cost; already
supported in spirit by the CSV import wizard at `/data/imports`.

## 4. Security posture

This is an industrial control environment, so the platform is **read-only for
operational telemetry**.

* No control commands are sent to SCADA. The platform does not open or close valves,
  change pump frequency, alter setpoints, or modify PLC logic.
* No requirement for the operator to expose control systems to the internet: a
  read-only historian, middleware endpoint or export drop is sufficient.
* Credentials come from the environment, never from the repository.
* Tag mapping is explicit configuration, never inferred from a tag name.

Any future write path would need a separately designed and approved industrial control
architecture; it is out of scope here.

## 5. Tag mapping

A connector needs an explicit mapping from a well to its tags, supplied by the
operator — for example:

| well | measurement | source tag | unit |
|---|---|---|---|
| `100031106504W400` | tubing_pressure | `PLANT1.WELL_A104.PT_TUBING` | kPa |
| `100031106504W400` | casing_pressure | `PLANT1.WELL_A104.PT_CASING` | kPa |

Units are normalised on ingest (kPa/bar/psi/MPa; m³/d and bbl/d; °C/°F) and the source
unit is retained alongside the normalised one, exactly as Petrinex m³ values are today.

## 6. What changes in the UI once a connector exists

Nothing structural. The well record's **Live telemetry** section and the calculator's
*Inputs with no public source* card are already rendered from a list of fields with no
value. When a connector supplies them they render with a value, unit, timestamp,
quality flag and source tag, and the **Data sources** tab gains a `scada` entry naming
the source system instead of `Not connected`.

Until then, the honest statement stands: this system shows what Alberta publishes, and
says so when it does not know.

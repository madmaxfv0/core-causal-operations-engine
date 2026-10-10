# Which real public dataset Real mode uses, and why

**Selected: Alberta — AER (ST37, ST102, pipelines, integrity reports) + Petrinex volumetrics.**

Texas RRC was evaluated against it as instructed. Alberta wins on the one criterion that
decides it: **whether the data can actually be fetched and joined programmatically.**

## The comparison

| Criterion | Alberta (AER + Petrinex) | Texas (RRC) |
|---|---|---|
| Machine-fetchable well list | **Yes** — AER's own ArcGIS Feature Service, verified: 475,125 wells | Shapefile downloads; no queryable service |
| Coordinates | **Yes** — WGS84 served directly (`outSR=4326`), no projection guessing | Yes, in shapefiles |
| Machine-fetchable production | **Yes** — Petrinex monthly API, verified: 1,697,176 records | **No.** The Production Data Query "does not have the capability to download or export query results"; the production database must be **purchased** |
| Oil / gas / water split | **Yes**, all three per well per month | Oil and gas; water not in the free query |
| Injection | **Yes** (INJ/DISP activities) | Limited |
| Operator | Yes | Yes |
| Well status / type | Yes (AER category) | Yes |
| Field / lease / pool | Facility/field proxy | Yes (lease-level) |
| Integrity records | **Yes** — casing failures + vent flow/gas migration CSVs | Not published equivalently |
| Deterministic join | **Yes** — Alberta Township System legal location, parsed from both sides, unique in both directions | Lease↔well joins are messy; production is often lease-level, not well-level |
| Reachable from this environment | Yes | **No** — `rrc.texas.gov` does not resolve here |

Texas's blocker is decisive: production is **lease-level and not exportable without purchase**,
so Real mode could show wells on a map but could not populate a single production chart from
an official free source. Alberta gives well-level monthly oil, gas, water and injection with a
clean structural join — which is what the existing charts, calculators and KPIs need.

## Field coverage of the existing application

Measured against the application's canonical schema (32 fields):

```
overall real-source coverage      18 / 32   = 56%

production   7/7    oil, water, gas, hours, injection, monthly history, cumulative
map          2/2    latitude, longitude
integrity    2/2    casing failures, vent flow / gas migration
wells        7/11   well_id, operator, field, jurisdiction, facility, status, well_type
                    (missing: pool, lift_type, spud_date, completion_date)
facilities   0/1    fluid capacity is operator data, not published
interventions 0/2   no public workover/job history exists anywhere
scada        0/7    pressure, temperature, vibration, ESP current, choke — no public source
```

## Major missing data types in Real mode

These are shown as **unavailable**, never substituted:

* **Live SCADA telemetry** — pressure, temperature, vibration, ESP current, choke position.
  Real mode states `Live SCADA not connected`. Synthetic mode keeps its simulated SCADA.
* **Intervention / workover history** — no regulator publishes it. The Interventions page shows
  an explicit empty state distinguishing *recorded historical intervention* from
  *AI / model recommendation*, rather than inventing past jobs.
* **Operator costs and facility capacity** — illustrative assumptions, labelled everywhere.
* **Pool, lift type, spud and completion dates** — not in the imported ST37 package.

Volumes actually imported and verified:

```
ST37 wells with coordinates   475,125
Petrinex monthly records    1,697,176
wells linked to production    109,571
AER ST102 facilities          120,212
AER pipeline segments          69,468
```

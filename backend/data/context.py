"""Data context: what CORE is actually analysing right now, and where each field comes from.

Two independent data planes exist in CORE and they must never be conflated:

* the **analytical data set** (`backend/data/store.py`) — wells + monthly production +
  interventions + facilities, used by every causal/economic page;
* the **Alberta public caches** (`backend/data/alberta.py`, `petrinex_cache.py`) — AER
  regulatory records and Petrinex reported volumes, used by the map.

This module reports both truthfully, per domain, so the UI can state exactly which
source a number came from and say *Not available* / *Operator data required* instead of
implying one data set contains fields that actually come from another.
"""
from __future__ import annotations

from . import alberta, store

# Truthful availability states used across the Data Hub and the context banner.
AVAILABLE = "Available"
NOT_AVAILABLE = "Not available"
NOT_APPLICABLE = "Not applicable"
NOT_MAPPED = "Not mapped"
OPERATOR_REQUIRED = "Operator data required"
ADAPTER_MISSING = "Adapter not implemented"

# Value kinds. Every provenance block carries exactly one.
REPORTED = "reported"        # a regulator/operator formally declared it
MEASURED = "measured"        # an instrument reading (requires a SCADA connector)
DERIVED = "derived"          # deterministic arithmetic on reported values
MODEL = "model estimate"     # model output
ASSUMPTION = "illustrative assumption"
SYNTHETIC = "synthetic"


def provenance(value, unit: str = "", kind: str = DERIVED, source=None, formula: str = "",
               period: str = "", source_fields=None, limitations=None, **extra) -> dict:
    """Reusable provenance block attached to any number that leaves the backend.

    Kept deliberately small so it can be produced anywhere a value is computed,
    rather than hand-writing a tooltip per metric in the UI.
    """
    return {
        "value": value,
        "unit": unit,
        "kind": kind,
        "source": [source] if isinstance(source, str) else list(source or []),
        "formula": formula,
        "period": period,
        "source_fields": list(source_fields or []),
        "limitations": list(limitations or []),
        **extra,
    }


def _dataset_domains(ds_meta: dict, name: str, counts: dict) -> dict:
    """Per-domain truth for the active analytical data set."""
    synthetic = "SYNTHETIC" in str(ds_meta.get("data_mode", "")).upper()
    label = ds_meta.get("source") or ds_meta.get("label") or name
    interventions = counts.get("interventions", 0)
    return {
        "wells": {"status": AVAILABLE if counts.get("wells") else NOT_AVAILABLE,
                  "source": label, "rows": counts.get("wells", 0),
                  "kind": SYNTHETIC if synthetic else REPORTED},
        "production": {"status": AVAILABLE if counts.get("production_rows") else NOT_AVAILABLE,
                       "source": label, "rows": counts.get("production_rows", 0),
                       "grain": "well × month",
                       "kind": SYNTHETIC if synthetic else REPORTED,
                       "limitations": [] if synthetic else ["Monthly reported volumes, not live telemetry."]},
        "interventions": {"status": AVAILABLE if interventions else (NOT_AVAILABLE if not synthetic else AVAILABLE),
                          "source": label if interventions else None, "rows": interventions,
                          "kind": SYNTHETIC if synthetic else REPORTED,
                          "note": None if interventions else
                                  "Public volumetric data contains no intervention or workover history."},
        "costs": {"status": AVAILABLE if synthetic else OPERATOR_REQUIRED,
                  "source": "CORE generator" if synthetic else None,
                  "kind": SYNTHETIC if synthetic else None,
                  "note": None if synthetic else
                          "Intervention costs, lifting costs and facility capacities are illustrative public "
                          "assumptions until operator cost data is connected."},
        "facilities": {"status": AVAILABLE if counts.get("facilities") else NOT_AVAILABLE,
                       "source": label, "rows": counts.get("facilities", 0),
                       "kind": SYNTHETIC if synthetic else REPORTED,
                       "note": None if synthetic else
                               "Facility fluid capacity is not published; utilisation needs operator data."},
    }


def _alberta_domains() -> dict:
    """Per-domain truth for the Alberta public map caches (independent of the data set)."""
    from . import petrinex_cache

    out = {}
    for kind, domain in (("st37", "wells"), ("facilities", "facilities"), ("pipelines", "pipelines")):
        m = alberta.meta(kind)
        spec = alberta.SOURCE_CATALOG[kind]
        out[domain] = {
            "status": AVAILABLE if m else NOT_AVAILABLE,
            "source": spec["dataset"], "kind": REPORTED,
            "rows": (m.get("stats") or {}).get("rows") if m else 0,
            "retrieved_at": m.get("retrieved_at") if m else None,
            "source_last_edit": m.get("source_last_edit") if m else None,
        }
    pmeta = petrinex_cache.cache_meta()
    out["production"] = {
        "status": AVAILABLE if pmeta else NOT_AVAILABLE,
        "source": pmeta.get("dataset") if pmeta else "Petrinex Alberta Conventional Volumetrics",
        "kind": REPORTED,
        "rows": pmeta.get("records", 0) if pmeta else 0,
        "period": f"{pmeta['months'][0]} → {pmeta['latest_month']}" if pmeta else None,
        "retrieved_at": pmeta.get("retrieved_at") if pmeta else None,
        "limitations": ["Monthly reported volumes, not live telemetry."],
    }
    integrity = [k for k in ("casing_failures", "vent_flow") if alberta.meta(k)]
    out["integrity"] = {
        "status": AVAILABLE if integrity else NOT_AVAILABLE,
        "source": ", ".join(alberta.SOURCE_CATALOG[k]["dataset"] for k in integrity) if integrity else None,
        "kind": REPORTED,
        "note": None if integrity else "AER casing-failure and vent-flow reports are not imported.",
    }
    out["interventions"] = {"status": NOT_AVAILABLE, "source": None, "kind": None,
                            "note": "Alberta public data contains no intervention or workover history."}
    out["telemetry"] = {"status": NOT_AVAILABLE, "source": None, "kind": None,
                        "note": "SCADA NOT CONNECTED — currently using public/cached data. Pressure, "
                                "temperature, vibration, choke and pump values have no public source."}
    return out


def describe() -> dict:
    """The active data context, with per-domain provenance for the UI banner."""
    name = store.active_dataset_name()
    health = store.dataset_health(name)
    try:
        ds = store.load_dataset(name)
        meta_ = ds.meta
        counts = {"wells": int(len(ds.wells)), "production_rows": int(len(ds.production)),
                  "interventions": int(len(ds.interventions)), "facilities": int(len(ds.facilities))}
    except Exception:
        meta_, counts = {}, {}
    synthetic = "SYNTHETIC" in str(meta_.get("data_mode", "")).upper()
    return {
        "dataset": {
            "name": name,
            "label": meta_.get("label") or name,
            "source": meta_.get("source"),
            "data_mode": meta_.get("data_mode"),
            "is_synthetic": synthetic,
            "usable": health.get("usable", False),
            "reason": health.get("reason"),
            "date_range": meta_.get("date_range"),
            "counts": counts,
            "domains": _dataset_domains(meta_, name, counts),
        },
        "alberta_public": {
            "label": "Alberta public data (map)",
            "note": "Independent of the analytical data set: the map always draws AER/Petrinex public records.",
            "domains": _alberta_domains(),
        },
        "available_datasets": [
            {**d, "usable": store.dataset_health(d["name"]).get("usable", False)}
            for d in store.list_datasets()
        ],
        "scada": {"connected": False,
                  "statement": "SCADA NOT CONNECTED — currently using public/cached data."},
    }

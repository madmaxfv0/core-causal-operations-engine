"""Persistent mutable state for the demo: decisions, notes, scenarios, donor overrides, portfolio edits."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from threading import Lock

from .config import MODEL_VERSION, STATE_FILE

_lock = Lock()
EMPTY = {"decisions": [], "notes": [], "reviewed": {}, "scenarios": [], "donor_overrides": {}, "manual_jobs": [], "plan": {"locked": {}, "removed": [], "moves": {}}, "connectors": {}, "imports": [], "intervention_outcomes": []}


def load() -> dict:
    if STATE_FILE.exists():
        try:
            d = json.loads(STATE_FILE.read_text())
            for k, v in EMPTY.items():
                d.setdefault(k, json.loads(json.dumps(v)))
            return d
        except Exception:
            pass
    return json.loads(json.dumps(EMPTY))


def save(d: dict):
    STATE_FILE.write_text(json.dumps(d, indent=1, default=str))


def reset():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_decision(recommendation_id: str, well_id: str, action: str, decision: str, user: str, reason: str | None, notes: str | None, inputs: dict | None, confidence: str | None, module: str) -> dict:
    with _lock:
        d = load()
        rec = {"decision_id": "DEC-" + uuid.uuid4().hex[:8].upper(), "recommendation_id": recommendation_id, "well_id": well_id, "action": action, "decision": decision, "user": user, "reason": reason, "notes": notes,
               "inputs": inputs or {}, "confidence": confidence, "module": module, "model_version": MODEL_VERSION, "timestamp": now(), "subsequent_outcome": None}
        d["decisions"].append(rec)
        save(d)
        return rec


def add_note(entity_id: str, text: str, user: str) -> dict:
    with _lock:
        d = load()
        n = {"note_id": "NOTE-" + uuid.uuid4().hex[:6].upper(), "entity_id": entity_id, "text": text, "user": user, "timestamp": now()}
        d["notes"].append(n)
        save(d)
        return n


def mark_reviewed(entity_id: str, user: str) -> dict:
    with _lock:
        d = load()
        d["reviewed"][entity_id] = {"user": user, "timestamp": now()}
        save(d)
        return d["reviewed"][entity_id]


def set_donor_overrides(analysis_key: str, exclusions: list[str], forced: list[str], locked: bool):
    with _lock:
        d = load()
        d["donor_overrides"][analysis_key] = {"exclusions": sorted(set(exclusions)), "forced": sorted(set(forced)), "locked": locked, "timestamp": now()}
        save(d)
        return d["donor_overrides"][analysis_key]


def get_donor_overrides(analysis_key: str) -> dict:
    return load()["donor_overrides"].get(analysis_key, {"exclusions": [], "forced": [], "locked": False})


def save_scenario(name: str, budget: float, constraints: dict, objective: str, plan: dict, user: str, scenario_id: str | None = None) -> dict:
    with _lock:
        d = load()
        sc = {"scenario_id": scenario_id or "SCN-" + uuid.uuid4().hex[:6].upper(), "name": name, "budget": budget, "constraints": constraints, "objective": objective, "plan_kpi": plan.get("kpi"), "selected_ids": [s["candidate_id"] for s in plan.get("selected", [])],
              "created_by": user, "created_at": now()}
        d["scenarios"] = [s for s in d["scenarios"] if s["scenario_id"] != sc["scenario_id"]] + [sc]
        save(d)
        return sc


def delete_scenario(scenario_id: str):
    with _lock:
        d = load()
        d["scenarios"] = [s for s in d["scenarios"] if s["scenario_id"] != scenario_id]
        save(d)


def plan_state() -> dict:
    return load()["plan"]


def update_plan(locked: dict | None = None, removed: list | None = None, moves: dict | None = None, reset_plan: bool = False) -> dict:
    with _lock:
        d = load()
        if reset_plan:
            d["plan"] = {"locked": {}, "removed": [], "moves": {}}
            d["manual_jobs"] = []
        if locked is not None:
            d["plan"]["locked"] = locked
        if removed is not None:
            d["plan"]["removed"] = removed
        if moves is not None:
            d["plan"]["moves"] = moves
        save(d)
        return d["plan"]


def add_manual_job(job: dict) -> dict:
    with _lock:
        d = load()
        job = dict(job)
        job["candidate_id"] = "MANUAL-" + uuid.uuid4().hex[:6].upper()
        d["manual_jobs"].append(job)
        save(d)
        return job


def add_intervention_outcome(outcome: dict) -> dict:
    with _lock:
        d = load()
        record = dict(outcome)
        record.setdefault("outcome_id", "OUT-" + uuid.uuid4().hex[:8].upper())
        record.setdefault("recorded_at", now())
        d["intervention_outcomes"].append(record)
        save(d)
        return record


def intervention_outcomes(well_id: str | None = None) -> list[dict]:
    rows = load()["intervention_outcomes"]
    return [r for r in rows if not well_id or r.get("well_id") == well_id]

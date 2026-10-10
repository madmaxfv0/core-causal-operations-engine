"""CORE Copilot: navigates evidence. It never produces a number that the engine did not compute."""
from __future__ import annotations

import os
import re

from ..archive import extraction as archive
from . import memory


def _fmt(v, d=1):
    if v is None:
        return "n/a"
    return f"{v:,.{d}f}"


def explain_rank(idle_rows: list[dict], ghost_rows: list[dict], a: str, b: str | None = None) -> dict:
    rows = {r["well_id"]: {**r, "_module": "idle"} for r in idle_rows}
    rows.update({r["well_id"]: {**r, "_module": "ghost"} for r in ghost_rows if r["well_id"] not in rows})
    ra = rows.get(a)
    if not ra:
        return {"answer": f"{a} is not in the current idle-well or ghost-barrel rankings.", "structure": None}
    out = {"well_id": a}
    if ra["_module"] == "idle":
        out["recommendation"] = f"{ra['status']} — {ra.get('intervention_type', 'n/a').replace('_', ' ')}; expected {_fmt(ra.get('expected_oil_bpd'))} bbl/d (range {_fmt(ra.get('expected_oil_lo'))}–{_fmt(ra.get('expected_oil_hi'))}), expected NPV {_fmt(ra.get('expected_npv'), 0)}."
        out["evidence"] = [f"{ra.get('analog_count', 0)} comparable historical restarts", f"estimated shut-in reason {ra.get('estimated_reason')} ({ra.get('reason_quality')})"] + [e for rr in ra.get("reasons", [])[:1] for e in rr["evidence"]]
        out["uncertainty"] = f"{ra.get('confidence')}; restart sustain probability {_fmt((ra.get('restart_probability') or 0) * 100, 0)}% from analogues"
        out["comparable_wells"] = [x["well_id"] for x in ra.get("analogs", [])][:6]
    else:
        out["recommendation"] = f"Ghost-barrel candidate: producing {_fmt(ra['observed_bpd'])} vs expected {_fmt(ra['expected_bpd'])} bbl/d (gap {_fmt(ra['gap_bpd'])}, range {_fmt(ra['gap_lo'])}–{_fmt(ra['gap_hi'])}); probable driver {ra.get('probable_driver')}."
        out["evidence"] = [f"{ra.get('duration_months')} months below the baseline lower band", f"baseline model: {ra.get('model', '').replace('_', ' ')}"]
        out["uncertainty"] = ra.get("confidence")
        out["comparable_wells"] = []
    out["economic_assumptions"] = "Illustrative public assumptions (oil price, netback, intervention costs) — editable in Settings."
    docs = archive.search(a)["hits"]
    out["source_documents"] = [{"document_id": h["document_id"], "file_name": h["file_name"]} for h in docs[:3]]
    text = f"{a}: {out['recommendation']}"
    if b:
        rb = rows.get(b)
        if rb:
            ka = ra.get("expected_npv") if ra["_module"] == "idle" else ra.get("annual_value")
            kb = rb.get("expected_npv") if rb["_module"] == "idle" else rb.get("annual_value")
            out["comparison"] = {"well_id": b, "value": kb, "confidence": rb.get("confidence"), "status": rb.get("status")}
            diffs = []
            if ka is not None and kb is not None:
                diffs.append(f"expected value {_fmt(ka, 0)} vs {_fmt(kb, 0)}")
            if ra.get("confidence") != rb.get("confidence"):
                diffs.append(f"confidence {ra.get('confidence')} vs {rb.get('confidence')}")
            if ra["_module"] == "idle" and rb["_module"] == "idle":
                diffs.append(f"analogues {ra.get('analog_count', 0)} vs {rb.get('analog_count', 0)}; sustain probability {_fmt((ra.get('restart_probability') or 0) * 100, 0)}% vs {_fmt((rb.get('restart_probability') or 0) * 100, 0)}%")
            text += f" Compared with {b}: " + "; ".join(diffs) + "."
        else:
            text += f" {b} is not ranked."
    out["answer"] = text
    return out


def operating_memory(memory_rows: list[dict], itype: str) -> dict:
    ev = memory.type_evidence(memory_rows, itype)
    if ev["n"] == 0:
        return {"answer": f"No completed analyses of {itype.replace('_', ' ')} jobs in the loaded data set.", "evidence": ev}
    return {"answer": f"The last {ev['n']} {itype.replace('_', ' ')} jobs: median causal effect {ev['median_effect_bpd']} bbl/d (P20 {ev['p20_effect_bpd']}, P80 {ev['p80_effect_bpd']}), {ev['success_rate']:.0%} paid back, median cost {ev['median_cost']:,.0f}, median water change {ev['median_water_change_bpd']} bbl/d. Failures: {', '.join(ev['failures']) or 'none'}.", "evidence": ev}


def ask(question: str, idle_rows, ghost_rows, memory_rows) -> dict:
    q = question.strip()
    ids = re.findall(r"\b([A-Z]{2,4}-\d{2,4})\b", q.upper())
    lower = q.lower()
    types = [t for t in ("pump_replacement", "cleanout", "water_shutoff", "stimulation", "workover", "restart") if t.replace("_", " ") in lower or t in lower]
    if ids and ("rank" in lower or "why" in lower or "above" in lower or "compare" in lower or "vs" in lower):
        res = explain_rank(idle_rows, ghost_rows, ids[0], ids[1] if len(ids) > 1 else None)
    elif types and ("last" in lower or "times" in lower or "history" in lower or "happened" in lower or "memory" in lower):
        res = operating_memory(memory_rows, types[0])
    elif ids:
        res = explain_rank(idle_rows, ghost_rows, ids[0])
    else:
        hits = archive.search(q)
        res = {"answer": (f"{len(hits['hits'])} archive documents match; see citations." if hits["hits"] else "I can explain rankings ('why is SYN-031 ranked above SYN-077?'), summarise operating memory ('what happened the last times we did water shutoff?'), or search the archive. I do not produce numbers the engine has not computed."),
               "source_documents": [{"document_id": h["document_id"], "file_name": h["file_name"]} for h in hits["hits"][:5]]}
    res["mode"] = "deterministic"
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("COPILOT_LLM", "0") == "1":
        try:
            import httpx
            r = httpx.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                           json={"model": "claude-sonnet-4-6", "max_tokens": 400, "system": "Rephrase the given evidence summary for an oilfield engineer. Do not add, change or invent any number.", "messages": [{"role": "user", "content": res["answer"]}]}, timeout=30)
            if r.status_code == 200:
                res["answer_rephrased"] = "".join(b.get("text", "") for b in r.json()["content"])
                res["mode"] = "deterministic + llm rephrase"
        except Exception:
            pass
    return res


def global_search(ctx, q: str, memory_rows: list[dict]) -> dict:
    ql = q.lower().strip()
    wells = []
    for r in ctx.ds.wells.itertuples():
        hay = f"{r.well_id} {r.field} {getattr(r, 'operator', '')} {ctx.well_status(r.well_id)}".lower()
        if ql in hay or (ql == "high water" and False):
            wells.append({"well_id": r.well_id, "field": r.field, "status": ctx.well_status(r.well_id)})
    if "high water" in ql:
        wc = ctx.ds.panel("water_cut")
        n = ctx.ds.n_months
        for wid in wc.columns:
            v = wc[wid].to_numpy(dtype=float)[n - 3:]
            if len(v) and float(v[~(v != v)].mean() if (v == v).any() else 0) >= 0.9 and ctx.well_status(wid) == "producing":
                wells.append({"well_id": wid, "field": None, "status": "producing (water cut ≥ 90%)"})
    ints = []
    for m in memory_rows:
        hay = f"{m['intervention_id']} {m['well_id']} {m['type']} {m['date']} {m['confidence']}".lower()
        if ql in hay or (ql.replace(" ", "_") in hay) or (ql.endswith("interventions") and ql[:4].isdigit() and m["date"].startswith(ql[:4])):
            ints.append({"intervention_id": m["intervention_id"], "well_id": m["well_id"], "type": m["type"], "date": m["date"], "causal_gain_bpd": m["causal_gain_bpd"]})
    docs = archive.search(q)["hits"][:8]
    return {"query": q, "wells": wells[:25], "interventions": ints[:25], "documents": docs}

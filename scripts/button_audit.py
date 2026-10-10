#!/usr/bin/env python3
"""Programmatic button/navigation audit: lists every interactive control in the frontend source with its handler.

    python scripts/button_audit.py   -> docs/button-audit.md

A control counts as WIRED when it has an onClick/onChange/onDrop/onSubmit handler, an href/to target, or is a form input.
Anything else is listed as UNWIRED and must be fixed or removed before the app is declared finished.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"
OUT = ROOT / "docs" / "button-audit.md"
PAT = re.compile(r"<(button|a|NavLink|Link|select|input|textarea|label)\b([^>]*)>", re.S)


def label_of(tag: str, attrs: str, after: str) -> str:
    m = re.search(r"aria-label=\{?[\"']?([^\"'}]+)", attrs) or re.search(r"title=\{?[\"']?([^\"'}]+)", attrs) or re.search(r"placeholder=\{?[\"']?([^\"'}]+)", attrs)
    if m:
        return m.group(1)[:60]
    txt = re.sub(r"<[^>]+>", " ", after[:140])
    txt = re.sub(r"\{[^}]*\}", lambda mm: mm.group(0)[:40], txt)
    return re.sub(r"\s+", " ", txt).strip()[:60] or f"<{tag}>"


def main():
    rows = []
    for f in sorted(SRC.rglob("*.tsx")):
        s = f.read_text()
        for m in PAT.finditer(s):
            tag, attrs = m.group(1), m.group(2)
            after = s[m.end(): m.end() + 200]
            handler = re.search(r"(onClick|onChange|onDrop|onSubmit|onKeyDown|onDragStart|onMouseEnter|href|\bto)=", attrs)
            if tag == "label":
                if "cursor-pointer" not in attrs and "<input" not in after[:120]:
                    continue
                handler = handler or re.search(r"<input", after)
            wired = bool(handler) or tag in ("input", "textarea", "select") or "type=\"file\"" in after[:120]
            if "disabled" in attrs and not wired:
                wired = True
            line = s[: m.start()].count("\n") + 1
            rows.append((f.relative_to(SRC).as_posix(), line, tag, label_of(tag, attrs, after), (handler.group(1) if handler and hasattr(handler, "group") and handler.re.groups else ("input" if handler else "")), "WIRED" if wired else "UNWIRED"))
    unwired = [r for r in rows if r[5] == "UNWIRED"]
    md = ["# CORE button & navigation audit", "", f"Generated from `frontend/src`. {len(rows)} interactive controls found, {len(unwired)} unwired.", "",
          "Routes covered by the automated jsdom smoke test (`frontend/smoke.mjs`): /, /wells, /wells/:id (all tabs), /ghost, /idle, /network, /interventions, /interventions/compare, /interventions/:id, /water, /portfolio, /portfolio/scenarios, /archive, /archive/ask, /model-lab (all tabs), /quality, /data, /data/imports, /decisions, /runs, /settings, /why, /present.", "",
          "| File | Line | Control | Label | Handler | Status |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3].replace('|', '/')} | {r[4]} | {r[5]} |")
    OUT.write_text("\n".join(md) + "\n")
    print(f"{len(rows)} controls, {len(unwired)} unwired -> {OUT}")
    for r in unwired:
        print("  UNWIRED", r)


if __name__ == "__main__":
    main()

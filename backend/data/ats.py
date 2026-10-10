"""Alberta Township System (DLS) identifier handling.

Two official Alberta datasets identify the same physical location in two different
notations:

* AER ST37 publishes a surface location string such as ``11-32-040-11W4``
  (legal subdivision - section - township - range + meridian).
* Petrinex publishes a 16-character Alberta UWI such as ``100031106504W400``
  (``100`` location exception + LSD + section + township + range + meridian +
  event sequence).

Both encode the identical Alberta Township System cell, so a join on the
canonical cell is an *authoritative structural* join, not a fuzzy name match.
It is however a **location-level** join: several wells (different events, several
bores) can legally share one legal subdivision.  Callers must therefore treat a
cell with more than one candidate as ambiguous - see
``backend/data/alberta.py:join_report``.

No coordinates are derived here.  Map coordinates always come from the AER's own
published geometry.
"""
from __future__ import annotations

import re

# LSD-SEC-TWP-RGE + meridian, tolerant of separators and missing zero padding.
_LOC_RE = re.compile(
    r"^(?P<lsd>\d{1,2})[-\s/]*(?P<sec>\d{1,2})[-\s/]*(?P<twp>\d{1,3})[-\s/]*(?P<rge>\d{1,2})[-\s/]*(?P<mer>[WE]\s*\d)$",
    re.IGNORECASE,
)
# Alberta UWI: 3-char location exception, LSD, section, township, range, meridian, event.
_UWI_RE = re.compile(
    r"^(?P<le>\d{2,3})(?P<lsd>\d{2})(?P<sec>\d{2})(?P<twp>\d{3})(?P<rge>\d{2})(?P<mer>[WE]\d)(?P<event>\d{2})$",
    re.IGNORECASE,
)


def _cell(lsd: str, sec: str, twp: str, rge: str, mer: str) -> str:
    mer = mer.upper().replace(" ", "")
    return f"{int(lsd):02d}-{int(sec):02d}-{int(twp):03d}-{int(rge):02d}{mer}"


def cell_from_location(value: object) -> str | None:
    """Canonical ATS cell from an AER surface-location string, or None."""
    if value is None:
        return None
    text = str(value).strip().upper().replace(" ", "")
    if not text or text in {"NAN", "NONE", ""}:
        return None
    match = _LOC_RE.match(text)
    if not match:
        return None
    g = match.groupdict()
    try:
        return _cell(g["lsd"], g["sec"], g["twp"], g["rge"], g["mer"])
    except (TypeError, ValueError):
        return None


def parse_uwi(value: object) -> dict | None:
    """Split an Alberta UWI (with or without the ``AB``/``ABWI`` prefix and separators)."""
    if value is None:
        return None
    text = str(value).strip().upper()
    for prefix in ("ABWI", "ABPR", "AB"):
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):]
            break
    text = text.replace("/", "").replace("-", "").replace(" ", "")
    match = _UWI_RE.match(text)
    if not match:
        return None
    g = match.groupdict()
    try:
        cell = _cell(g["lsd"], g["sec"], g["twp"], g["rge"], g["mer"])
    except (TypeError, ValueError):
        return None
    return {
        "uwi": text,
        "location_exception": g["le"],
        "event_sequence": g["event"],
        "cell": cell,
        "legal_location": f"{g['le']}/{cell}/{g['event']}",
    }


def cell_from_uwi(value: object) -> str | None:
    parsed = parse_uwi(value)
    return parsed["cell"] if parsed else None


def describe_cell(cell: str | None) -> str | None:
    """Human-readable legal location, e.g. 'LSD 11, Sec 32, Twp 040, Rge 11 W4'."""
    if not cell:
        return None
    match = re.match(r"^(\d{2})-(\d{2})-(\d{3})-(\d{2})([WE]\d)$", cell)
    if not match:
        return cell
    lsd, sec, twp, rge, mer = match.groups()
    return f"LSD {lsd}, Sec {sec}, Twp {twp}, Rge {rge} {mer}"

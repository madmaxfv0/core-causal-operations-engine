"""Paginated, resumable downloader for public ArcGIS Feature Services.

Used for the Alberta Energy Regulator's official open-data services (ST37 list of
wells, ST102 facility list, pipeline segments).  The AER publishes these under the
Open Government Licence - Alberta; this module only reads them.

Design rules that matter for data credibility:

* Nothing is ever invented.  A page that fails after the retry budget aborts the
  sync; the previously validated cache is left untouched.
* Every sync records the service URL, layer id, server-reported edit date, the
  row count and the retrieval timestamp so the UI can state provenance exactly.
* Geometry is requested in EPSG:4326 from the server (``outSR=4326``) so no
  coordinate system is ever guessed locally.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

USER_AGENT = "CORE Alberta public-data importer (contact: operator)"
PAGE_RETRIES = 4
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 180.0


class SourceUnavailable(RuntimeError):
    """Raised when an official source cannot be read; caller keeps last-known-good."""


def _client():
    import httpx

    return httpx.Client(
        timeout=__import__("httpx").Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def layer_metadata(service_url: str, layer: int = 0) -> dict:
    with _client() as client:
        try:
            response = client.get(f"{service_url}/{layer}", params={"f": "json"})
            response.raise_for_status()
            meta = response.json()
        except Exception as exc:  # network, DNS, TLS, JSON
            raise SourceUnavailable(f"{service_url}/{layer}: {exc}") from exc
    if "error" in meta:
        raise SourceUnavailable(f"{service_url}/{layer}: {meta['error'].get('message', 'service error')}")
    return meta


def _edit_date(meta: dict) -> str | None:
    info = (meta.get("editingInfo") or {}).get("lastEditDate")
    if isinstance(info, (int, float)):
        return datetime.fromtimestamp(info / 1000, tz=timezone.utc).isoformat()
    return None


def validate_layer(meta: dict, required_fields: Iterable[str]) -> None:
    present = {f["name"] for f in meta.get("fields", [])}
    missing = [f for f in required_fields if f not in present]
    if missing:
        raise SourceUnavailable(
            f"Source schema changed for layer '{meta.get('name')}': required field(s) "
            f"{', '.join(missing)} not found. Existing cached dataset remains active."
        )


def _rows_from_geojson(payload: dict, geometry: str) -> list[dict]:
    rows = []
    for feature in payload.get("features", []):
        props = dict(feature.get("properties") or {})
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates")
        if geometry == "point":
            if not coords or len(coords) < 2:
                props["longitude"], props["latitude"] = None, None
            else:
                props["longitude"], props["latitude"] = float(coords[0]), float(coords[1])
        else:
            props["geometry_json"] = json.dumps(coords) if coords else None
        rows.append(props)
    return rows


def fetch_layer(
    service_url: str,
    layer: int = 0,
    *,
    geometry: str = "point",
    page_size: int = 2000,
    where: str = "1=1",
    out_fields: str = "*",
    required_fields: Iterable[str] = (),
    progress: Callable[[int, int], None] | None = None,
    max_records: int | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Download an entire feature layer with pagination and retries.

    Returns the rows and a provenance dict.  Raises SourceUnavailable on any
    unrecoverable failure so the caller can preserve the last-known-good cache.
    """
    meta = layer_metadata(service_url, layer)
    validate_layer(meta, required_fields)
    server_page = int(meta.get("maxRecordCount") or page_size)
    page_size = max(1, min(page_size, server_page))

    with _client() as client:
        try:
            count_payload = client.get(
                f"{service_url}/{layer}/query",
                params={"where": where, "returnCountOnly": "true", "f": "json"},
            ).json()
        except Exception as exc:
            raise SourceUnavailable(f"count query failed: {exc}") from exc
        total = int(count_payload.get("count", 0))
        if max_records:
            total = min(total, max_records)
        if total == 0:
            raise SourceUnavailable("source returned zero records; refusing to replace cache")

        rows: list[dict] = []
        offset = 0
        while offset < total:
            take = min(page_size, total - offset)
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": take,
                "orderByFields": meta.get("objectIdField", "OBJECTID"),
            }
            payload = None
            last_error: Exception | None = None
            for attempt in range(PAGE_RETRIES):
                try:
                    response = client.get(f"{service_url}/{layer}/query", params=params)
                    response.raise_for_status()
                    candidate = response.json()
                    if "error" in candidate:
                        raise RuntimeError(candidate["error"].get("message", "service error"))
                    payload = candidate
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(min(30, 2 ** attempt))
            if payload is None:
                raise SourceUnavailable(
                    f"page at offset {offset} failed after {PAGE_RETRIES} attempts: {last_error}"
                )
            page_rows = _rows_from_geojson(payload, geometry)
            if not page_rows:
                break
            rows.extend(page_rows)
            offset += len(page_rows)
            if progress:
                progress(offset, total)

    if not rows:
        raise SourceUnavailable("no rows parsed from source; cache preserved")
    frame = pd.DataFrame(rows)
    provenance = {
        "service_url": service_url,
        "layer": layer,
        "layer_name": meta.get("name"),
        "server_record_count": total,
        "rows_downloaded": int(len(frame)),
        "source_crs": "EPSG:4326 (requested from server, not inferred locally)",
        "source_last_edit": _edit_date(meta),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    return frame, provenance


def write_cache(frame: pd.DataFrame, meta: dict, out_dir: Path) -> dict:
    """Atomically replace a cache directory, keeping the previous copy until success."""
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{out_dir.name}-", dir=out_dir.parent))
    try:
        frame.to_parquet(staging / "records.parquet", index=False)
        (staging / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        backup = out_dir.with_name(out_dir.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if out_dir.exists():
            out_dir.rename(backup)
        staging.rename(out_dir)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return meta

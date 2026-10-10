"""Optional operator SCADA HTTP adapter.

CORE never fabricates telemetry.  The adapter is inactive unless an operator
explicitly configures SCADA_HTTP_URL and exposes the documented JSON contract:
GET /health and GET /wells/{well_id}/telemetry.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx


TELEMETRY_FIELDS = (
    "tubing_pressure", "casing_pressure", "annulus_pressure",
    "wellhead_temperature", "bottomhole_pressure", "choke_position",
    "pump_frequency", "motor_current", "motor_temperature", "vibration",
    "esp_intake_pressure", "esp_discharge_pressure",
)


def _base_url() -> str | None:
    value = os.environ.get("SCADA_HTTP_URL", "").strip().rstrip("/")
    return value or None


def status() -> dict[str, Any]:
    base = _base_url()
    if not base:
        return {
            "connected": False,
            "real_time": False,
            "provider": None,
            "message": "SCADA NOT CONNECTED — currently using public/cached/simulated data.",
        }
    try:
        with httpx.Client(timeout=5, follow_redirects=True) as client:
            response = client.get(f"{base}/health")
            response.raise_for_status()
            payload = response.json()
        return {
            "connected": True,
            "real_time": True,
            "provider": os.environ.get("SCADA_PROVIDER", "HTTP SCADA adapter"),
            "endpoint": base,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "health": payload,
            "message": "SCADA CONNECTED — telemetry is supplied by the configured operator endpoint.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "connected": False,
            "real_time": False,
            "provider": os.environ.get("SCADA_PROVIDER", "HTTP SCADA adapter"),
            "endpoint": base,
            "error": str(exc),
            "message": "SCADA CONFIGURED BUT UNAVAILABLE — no telemetry is shown until the endpoint is healthy.",
        }


def telemetry(well_id: str) -> dict[str, Any]:
    base = _base_url()
    if not base:
        return {"connected": False, "real_time": False, "telemetry": {}, "message": status()["message"]}
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            response = client.get(f"{base}/wells/{well_id}/telemetry")
            response.raise_for_status()
            payload = response.json()
        values = payload.get("telemetry", payload) if isinstance(payload, dict) else {}
        filtered = {key: values[key] for key in TELEMETRY_FIELDS if key in values and values[key] is not None}
        return {
            "connected": True,
            "real_time": True,
            "well_id": well_id,
            "telemetry": filtered,
            "observed_at": payload.get("observed_at") if isinstance(payload, dict) else None,
            "source": payload.get("source") if isinstance(payload, dict) else os.environ.get("SCADA_PROVIDER", "HTTP SCADA adapter"),
            "message": "SCADA CONNECTED — telemetry is supplied by the configured operator endpoint.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"connected": False, "real_time": False, "telemetry": {}, "well_id": well_id,
                "error": str(exc),
                "message": "SCADA CONFIGURED BUT UNAVAILABLE — no telemetry is shown until the endpoint is healthy."}

"""Data-context integrity tests.

These lock in the failure modes found during the Data Hub audit:

* a source that "connects" while importing zero rows, writes an empty data set,
  becomes active and takes every downstream page down (this actually happened);
* an evidence base built from one data set being served under another data set's
  badge — i.e. synthetic SYN-* records presented as REAL PUBLIC DATA;
* View schema / View sample returning hard-coded display metadata rather than the
  columns and rows that were really imported.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.data import context, store


# --------------------------------------------------------------------------- empty-import guard

def _tables(n_wells: int, n_rows: int) -> dict:
    return {
        "wells": pd.DataFrame({"well_id": [f"W{i}" for i in range(n_wells)]}),
        "production_monthly": pd.DataFrame({"well_id": [f"W{i%max(n_wells,1)}" for i in range(n_rows)],
                                            "month": ["2025-01"] * n_rows}),
    }


def test_empty_import_is_refused_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROCESSED_DIR", tmp_path)
    with pytest.raises(store.EmptyDatasetError, match="0 wells"):
        store.write_dataset("empty_source", _tables(0, 0), {"label": "x"})
    assert not (tmp_path / "empty_source" / "meta.json").exists()


def test_import_with_wells_but_no_production_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROCESSED_DIR", tmp_path)
    with pytest.raises(store.EmptyDatasetError):
        store.write_dataset("no_rows", _tables(5, 0), {"label": "x"})


def test_a_real_import_is_written_with_truthful_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROCESSED_DIR", tmp_path)
    store.write_dataset("good", _tables(3, 12), {"label": "x"})
    meta = pd.read_json(tmp_path / "good" / "meta.json", typ="series")
    assert meta["n_wells"] == 3 and meta["rows"] == 12
    assert store.dataset_health("good")["usable"] is True


def test_unusable_dataset_cannot_become_active(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROCESSED_DIR", tmp_path)
    with pytest.raises(store.EmptyDatasetError):
        store.set_active_dataset("does_not_exist")


# --------------------------------------------------------------------------- Petrinex window guard

def test_petrinex_min_months_cannot_silently_empty_the_import():
    """A 3-month request with a 24-month history requirement produced 0 wells and
    still reported success. min_months must clamp to the requested window."""
    from backend.data import petrinex

    import inspect
    src = inspect.getsource(petrinex.build_alberta)
    assert "min_months = max(1, min(min_months, len(months)))" in src
    assert "raise ValueError" in src   # an empty result must raise, not return empty tables


# --------------------------------------------------------------------------- no silent mixing

def test_evidence_from_another_dataset_is_refused(monkeypatch):
    from backend.core import precompute

    monkeypatch.setattr(precompute, "get", lambda name: {"dataset_name": "synthetic",
                                                         "dataset_version": "abc"} if name == "meta" else {})

    class _DS:
        name = "alberta_petrinex"
        meta = {"dataset_version": "zzz"}

    class _Ctx:
        ds = _DS()

    monkeypatch.setattr(precompute.engine, "get_context", lambda: _Ctx())
    reason = precompute.dataset_mismatch()
    assert reason and "synthetic" in reason and "alberta_petrinex" in reason


def test_matching_dataset_passes_the_guard(monkeypatch):
    from backend.core import precompute

    monkeypatch.setattr(precompute, "get", lambda name: {"dataset_name": "synthetic"} if name == "meta" else {})

    class _DS:
        name = "synthetic"
        meta = {"dataset_version": "abc"}

    class _Ctx:
        ds = _DS()

    monkeypatch.setattr(precompute.engine, "get_context", lambda: _Ctx())
    assert precompute.dataset_mismatch() is None


def test_legacy_cache_is_accepted_only_when_the_version_hash_matches(monkeypatch):
    from backend.core import precompute

    class _DS:
        name = "synthetic"
        meta = {"dataset_version": "v1"}

    class _Ctx:
        ds = _DS()

    monkeypatch.setattr(precompute.engine, "get_context", lambda: _Ctx())
    monkeypatch.setattr(precompute, "get", lambda n: {"dataset_version": "v1"} if n == "meta" else {})
    assert precompute.dataset_mismatch() is None          # same data, older cache format
    monkeypatch.setattr(precompute, "get", lambda n: {"dataset_version": "v2"} if n == "meta" else {})
    assert precompute.dataset_mismatch() is not None       # different data -> refuse


# --------------------------------------------------------------------------- context truthfulness

def test_context_reports_scada_as_not_connected():
    described = context.describe()
    assert described["scada"]["connected"] is False
    assert "SCADA NOT CONNECTED" in described["scada"]["statement"]


def test_context_marks_the_active_dataset_and_its_domains():
    described = context.describe()
    ds = described["dataset"]
    assert ds["name"] and isinstance(ds["is_synthetic"], bool)
    for domain in ("wells", "production", "interventions", "costs", "facilities"):
        assert ds["domains"][domain]["status"] in {
            context.AVAILABLE, context.NOT_AVAILABLE, context.NOT_APPLICABLE,
            context.NOT_MAPPED, context.OPERATOR_REQUIRED, context.ADAPTER_MISSING,
        }


def test_alberta_public_plane_never_claims_telemetry():
    domains = context.describe()["alberta_public"]["domains"]
    assert domains["telemetry"]["status"] == context.NOT_AVAILABLE
    assert "SCADA NOT CONNECTED" in domains["telemetry"]["note"]
    assert domains["interventions"]["status"] == context.NOT_AVAILABLE


def test_provenance_block_has_the_required_shape():
    block = context.provenance(100.0, unit="bbl/d", kind=context.DERIVED,
                               source="Petrinex Alberta", formula="oil_volume / reporting_days",
                               period="2025-03", source_fields=["oil_m3", "days"],
                               limitations=["monthly reported data, not live SCADA"])
    for key in ("value", "unit", "kind", "source", "formula", "period", "source_fields", "limitations"):
        assert key in block
    assert block["source"] == ["Petrinex Alberta"]
    assert block["kind"] == "derived"


# --------------------------------------------------------------------------- API surface
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.api.main import app
    return TestClient(app, raise_server_exceptions=False)


def test_context_endpoint_states_the_active_context(client):
    body = client.get("/api/data/context").json()
    assert body["dataset"]["name"]
    assert body["scada"]["connected"] is False
    assert isinstance(body["available_datasets"], list)


def test_connect_on_a_source_without_an_adapter_does_not_report_connected(client):
    body = client.post("/api/data/connectors/north_dakota/connect", json={}).json()
    assert body["ok"] is False
    assert "Adapter not implemented" in body["message"]


def test_operator_api_never_claims_a_connection(client):
    body = client.post("/api/data/connectors/operator_api/connect", json={}).json()
    assert body["ok"] is False
    assert "SCADA NOT CONNECTED" in body["message"]


def test_view_schema_reports_observed_columns_not_a_hardcoded_list(client):
    body = client.post("/api/data/connectors/synthetic/schema", json={}).json()
    assert body["observed"] is True
    wells = body["tables"]["wells"]
    assert wells["rows"] > 0
    assert any(c["name"] == "well_id" for c in wells["columns"])
    assert all("dtype" in c for c in wells["columns"])


def test_view_sample_returns_real_rows(client):
    body = client.post("/api/data/connectors/synthetic/sample", json={}).json()
    assert body["rows_total"] > 0
    assert len(body["sample"]) > 0
    assert "well_id" in body["sample"][0]


def test_sample_of_an_unimported_source_is_a_clean_404(client):
    r = client.post("/api/data/connectors/aer_casing_failures/sample", json={})
    assert r.status_code == 404
    assert "not imported" in r.text


def test_activating_an_unknown_dataset_is_refused(client):
    assert client.post("/api/data/activate/not_a_dataset").status_code == 404


# --------------------------------------------------------------------------- data mode
def test_default_mode_is_synthetic_so_the_demo_is_immediately_available():
    from backend.data import mode as data_mode
    assert data_mode.SYNTHETIC == "SYNTHETIC"
    assert data_mode.dataset_for(data_mode.SYNTHETIC) == "synthetic"


def test_mode_describe_states_scada_truthfully_per_mode(client):
    from backend.data import mode as data_mode

    original = data_mode.current()
    try:
        client.post("/api/data/mode", json={"mode": "SYNTHETIC"})
        syn = client.get("/api/data/mode").json()
        assert syn["mode"] == "SYNTHETIC"
        assert syn["scada_live"] is True                 # simulated SCADA stays in the demo
        assert "Simulated SCADA" in syn["source_line"]

        real = client.post("/api/data/mode", json={"mode": "REAL"}).json()
        if real.get("ready"):
            assert real["scada_live"] is False
            assert real["scada"] == "Live SCADA not connected"
            assert "Petrinex" in real["source_line"] or "AER" in real["source_line"]
    finally:
        client.post("/api/data/mode", json={"mode": original})


def test_switching_modes_never_serves_the_other_modes_wells(client):
    """Synthetic -> Real -> Synthetic must not leak SYN-* into real pages or vice versa."""
    from backend.data import mode as data_mode

    original = data_mode.current()
    try:
        for _ in range(2):
            client.post("/api/data/mode", json={"mode": "SYNTHETIC"})
            body = client.get("/api/wells").text
            assert "SYN-" in body, "synthetic mode must show its own wells"

            real = client.post("/api/data/mode", json={"mode": "REAL"}).json()
            if not real.get("ready"):
                continue
            for route in ("/api/wells", "/api/overview", "/api/water"):
                text = client.get(route).text
                assert "SYN-" not in text, f"{route} leaked synthetic wells into REAL mode"
    finally:
        client.post("/api/data/mode", json={"mode": original})


def test_unknown_mode_is_rejected(client):
    assert client.post("/api/data/mode", json={"mode": "MAGIC"}).status_code == 400


def test_interventions_never_crash_without_history(client):
    """A data set with no recorded jobs must return a full-shaped empty response."""
    from backend.core import memory

    empty = memory.overview([])
    assert empty["has_history"] is False
    for key in memory.CHART_KEYS:
        assert key in empty["charts"]
    assert isinstance(empty["charts"]["scatter"], list)   # the page maps over this
    assert empty["kpis"]["jobs_analysed"] == 0


def test_runs_are_tagged_with_their_dataset():
    import inspect
    from backend.core import engine
    src = inspect.getsource(engine.analysis)
    assert 'd["dataset"] = ctx.ds.name' in src
    assert "dataset" in inspect.signature(engine.list_runs).parameters

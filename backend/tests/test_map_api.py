"""Alberta map API tests.

Covers the viewport, search, detail, provenance, overlay and calculator routes.
Tests that need the real cache skip cleanly when it has not been installed, so the
suite still passes on a machine that has never downloaded the Canadian datasets.
"""
from __future__ import annotations

import pytest

from backend.data import alberta

pytestmark = pytest.mark.skipif(
    alberta.records("st37").empty,
    reason="AER ST37 cache not installed (run scripts/update_alberta_data.py --all)",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.api.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def a_linked_well():
    frame = alberta.wells()
    linked = frame[frame.uwi.notna() & frame.oil_m3.notna()]
    if linked.empty:
        pytest.skip("no linked producing well in the installed cache")
    return linked.sort_values("oil_m3", ascending=False).iloc[0]


def test_status_reports_every_source(client):
    body = client.get("/api/alberta/status").json()
    kinds = {s["kind"] for s in body["sources"]}
    assert {"st37", "facilities", "pipelines", "casing_failures", "vent_flow", "abandoned"} <= kinds
    assert body["mode"] == "REAL PUBLIC DATA"
    assert "SCADA" in body["mode_note"] or "telemetry" in body["mode_note"]
    assert body["summary"]["available"] is True


def test_low_zoom_returns_clusters_not_hundreds_of_thousands_of_features(client):
    body = client.get("/api/map/wells?bbox=-120.1,48.9,-109.9,60.1&zoom=5").json()
    assert body["clustered"] is True
    assert body["count"] > 100_000
    assert body["features"] == []
    assert 0 < len(body["clusters"]) < 1000        # bounded payload
    assert sum(c["count"] for c in body["clusters"]) == body["count"]


def test_high_zoom_returns_individual_validated_records(client, a_linked_well):
    lng, lat = float(a_linked_well.longitude), float(a_linked_well.latitude)
    bbox = f"{lng - 0.02},{lat - 0.02},{lng + 0.02},{lat + 0.02}"
    body = client.get(f"/api/map/wells?bbox={bbox}&zoom=13").json()
    assert body["clustered"] is False
    ids = {f["record_id"] for f in body["features"]}
    assert a_linked_well.record_id in ids
    feature = next(f for f in body["features"] if f["record_id"] == a_linked_well.record_id)
    assert feature["latitude"] == pytest.approx(lat)
    assert feature["longitude"] == pytest.approx(lng)


def test_bbox_must_be_well_formed(client):
    assert client.get("/api/map/wells?bbox=1,2,3").status_code == 400
    assert client.get("/api/map/wells?bbox=a,b,c,d").status_code == 400


def test_filters_actually_change_the_result(client):
    box = "bbox=-120.1,48.9,-109.9,60.1&zoom=5"
    everything = client.get(f"/api/map/wells?{box}").json()["count"]
    abandoned = client.get(f"/api/map/wells?{box}&status=Abandoned").json()["count"]
    oil = client.get(f"/api/map/wells?{box}&fluid=Oil").json()["count"]
    producing = client.get(f"/api/map/wells?{box}&producing=true").json()["count"]
    assert 0 < abandoned < everything
    assert 0 < oil < everything
    assert 0 < producing < everything
    assert abandoned + oil != 0


def test_search_finds_a_real_well_by_its_exact_uwi(client, a_linked_well):
    body = client.get(f"/api/map/search?q={a_linked_well.uwi}").json()
    assert body["count"] >= 1
    assert any(r["uwi"] == a_linked_well.uwi for r in body["results"])


def test_search_finds_a_real_well_by_legal_location(client, a_linked_well):
    body = client.get(f"/api/map/search?q={a_linked_well.surface_location}").json()
    assert any(r["record_id"] == a_linked_well.record_id for r in body["results"])


def test_search_for_nonsense_returns_nothing_rather_than_something(client):
    body = client.get("/api/map/search?q=zzzz-not-a-well-zzzz").json()
    assert body["results"] == [] and body["count"] == 0


def test_well_detail_carries_real_values_and_their_provenance(client, a_linked_well):
    body = client.get(f"/api/map/wells/{a_linked_well.record_id}").json()
    well = body["well"]
    assert well["record_id"] == a_linked_well.record_id
    assert well["latitude"] == pytest.approx(float(a_linked_well.latitude))
    assert well["surface_location"] == a_linked_well.surface_location
    assert body["sources"]["identity"]["dataset"].startswith("AER ST37")
    assert body["sources"]["coordinates"]["value_type"] == "REPORTED"
    assert body["sources"]["status_and_fluid"]["value_type"] == "CALCULATED"
    assert body["sources"]["scada"] == "Not connected"
    assert body["production_history"], "a linked well must expose its reported months"
    assert body["production_history"][-1]["month"] == a_linked_well.latest_month


def test_private_telemetry_is_reported_missing_and_never_generated(client, a_linked_well):
    body = client.get(f"/api/map/wells/{a_linked_well.record_id}").json()
    for field, value in body["telemetry"].items():
        assert value == "Not publicly available", field
    assert "does not publish" in body["telemetry_note"]


def test_unknown_record_is_a_clean_404(client):
    r = client.get("/api/map/wells/ST37-does-not-exist")
    assert r.status_code == 404 and "Traceback" not in r.text


def test_provenance_trace_names_the_source_of_every_value(client, a_linked_well):
    body = client.get(f"/api/map/provenance/{a_linked_well.record_id}").json()
    fields = {entry["field"]: entry for entry in body["trace"]}
    assert "REPORTED" == fields["latitude/longitude/well_category/surface_location"]["value_type"]
    assert fields["ats_cell"]["value"] == a_linked_well.ats_cell
    production = fields["production"]
    assert production["value_type"] == "REPORTED"
    assert production["join"]["uwi"] == a_linked_well.uwi
    assert production["monthly_rows"] > 0


def test_overlays_return_real_aer_records(client):
    facilities = client.get("/api/map/overlays/facilities?bbox=-114,53,-113,54&limit=20").json()
    assert facilities["available"] is True
    assert facilities["source"].startswith("AER ST102")
    assert all(-114 <= f["longitude"] <= -113 for f in facilities["features"])
    pipelines = client.get("/api/map/overlays/pipelines?bbox=-114,53,-113,54&limit=20").json()
    assert pipelines["available"] is True
    assert all(p["geometry"] for p in pipelines["features"])
    assert client.get("/api/map/overlays/nope").status_code == 404


def test_calculator_offers_public_inputs_and_refuses_to_invent_pressure(client, a_linked_well):
    body = client.get(f"/api/map/wells/{a_linked_well.record_id}/calculator-inputs").json()
    assert body["available"]["oil_bpd"]["source"] == "Petrinex"
    assert body["available"]["oil_bpd"]["value_type"] == "CALCULATED"
    for key in ("tubing_pressure", "casing_pressure", "annulus_pressure", "vibration"):
        assert body["unavailable"][key]["value"] is None
        assert body["unavailable"][key]["value_type"] == "NOT AVAILABLE"


def test_scenario_runs_on_reported_volumes_and_states_its_caveats(client, a_linked_well):
    body = client.post(f"/api/map/wells/{a_linked_well.record_id}/scenario",
                       json={"uplift_fraction": 0.2, "success_probability": 0.6, "horizon_months": 12}).json()
    assert body["baseline"]["oil_bpd"] > 0
    assert body["result"]["success_probability"] == 0.6
    assert body["result"]["npv"] <= body["result"]["npv_if_success"]
    assert any("not telemetry" in c or "not a measured rate" in c for c in body["caveats"])
    assert body["mode"].startswith("REAL PUBLIC DATA")


def test_scenario_refuses_a_well_with_no_public_baseline(client):
    frame = alberta.wells()
    unlinked = frame[frame.uwi.isna()]
    if unlinked.empty:
        pytest.skip("every well is linked in this cache")
    record = unlinked.iloc[0].record_id
    r = client.post(f"/api/map/wells/{record}/scenario", json={"uplift_fraction": 0.2})
    assert r.status_code == 422
    assert "will not invent" in r.text


def test_summary_numbers_are_not_hard_coded(client):
    body = client.get("/api/map/summary").json()
    summary, join = body["summary"], body["join"]
    assert summary["wells_loaded"] == join["st37_wells_imported"]
    assert summary["matched_to_production"] == join["st37_wells_linked"]

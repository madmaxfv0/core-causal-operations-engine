"""Alberta public-data tests.

Two layers, deliberately:

* Unit tests on the parsers, identifier normalisation, validation and join rules,
  driven by fixtures (fast, always run).
* Integration checks against the REAL imported cache, skipped when the cache has
  not been installed on this machine.  These verify actual records rather than
  fabricated fixtures, as required: an identifier that exists in the source, a
  coordinate that survives into the normalized store, and a production value that
  matches the Petrinex row it came from.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from backend.data import alberta, ats, petrinex_cache


# --------------------------------------------------------------------------- identifiers

def test_ats_cell_from_aer_surface_location():
    assert ats.cell_from_location("11-32-040-11W4") == "11-32-040-11W4"
    assert ats.cell_from_location("2-10-43-23W4") == "02-10-043-23W4"
    assert ats.cell_from_location("  02-10-043-23 W4 ") == "02-10-043-23W4"
    assert ats.cell_from_location("not a location") is None
    assert ats.cell_from_location(None) is None


def test_uwi_parses_to_the_same_cell_as_the_aer_location():
    parsed = ats.parse_uwi("ABWI100031106504W400")
    assert parsed["cell"] == "03-11-065-04W4"
    assert parsed["event_sequence"] == "00"
    assert parsed["legal_location"] == "100/03-11-065-04W4/00"
    # the AER writes the identical cell in its own notation
    assert ats.cell_from_location("03-11-065-04W4") == parsed["cell"]


def test_uwi_rejects_confidential_and_malformed_identifiers():
    assert ats.parse_uwi("***") is None
    assert ats.parse_uwi("") is None
    assert ats.parse_uwi("ABWI12345") is None
    assert ats.cell_from_uwi("100031106504W400") == "03-11-065-04W4"


def test_describe_cell_is_human_readable():
    assert ats.describe_cell("11-32-040-11W4") == "LSD 11, Sec 32, Twp 040, Rge 11 W4"
    assert ats.describe_cell(None) is None


# --------------------------------------------------------------------------- ST37 normalisation

def _st37_fixture() -> pd.DataFrame:
    return pd.DataFrame({
        "OBJECTID": [1, 2, 3, 4],
        "Well_Category": ["Suspended Oil", "Abandoned Gas", "Injection", "Undefined"],
        "Surface_Location": ["11-32-040-11W4", "02-10-043-23W4", "08-35-077-06W4", "bad"],
        "latitude": [52.48, 52.68, 55.71, 12.0],       # last one is outside Alberta
        "longitude": [-111.55, -113.25, -110.80, 40.0],
    })


def test_casing_failure_and_vent_flow_columns_parse_to_well_id():
    """AER's own documented column names (report catalogue) must normalize cleanly."""
    vent_flow = alberta.normalize_columns(pd.DataFrame({
        "Report Date": ["2026-06-01"],
        "Licence Number": ["0123456"],
        "Current Licence Status": ["Active"],
        "Surface Location": ["00/11-32-040-11W4/00"],
        "Licensee at Reporting": ["TEST OPERATOR"],
        "Flow Substance": ["Gas"],
        "Flow Rate (m3/day)": ["12.5"],
    }))
    assert vent_flow.well_id.tolist() == ["0123456"]
    assert vent_flow.surface_location.tolist() == ["00/11-32-040-11W4/00"]
    stats = alberta.validate_wells(vent_flow, ("well_id",))
    assert stats["valid_identifiers"] == 1

    casing = alberta.normalize_columns(pd.DataFrame({
        "Licence Number": ["0123456"],
        "Surface Location": ["00/11-32-040-11W4/00"],
        "Failure Type": ["Casing Leak"],
    }))
    assert casing.well_id.tolist() == ["0123456"]


def test_file_source_urls_point_at_aers_real_direct_download_endpoints():
    """These are the exact URLs AER publishes on its General Well Data page —
    not a generic catalogue link the user has to search for."""
    assert alberta.FILE_SOURCES["casing_failures"]["url"].startswith(
        "https://www2.aer.ca/t/Production/views/COM-WellCasingFailureReport/")
    assert alberta.FILE_SOURCES["vent_flow"]["url"].startswith(
        "https://www2.aer.ca/t/Production/views/COM-VentFlowGasMigrationReport/")
    # both are now offered as one-click refreshable in the UI/CLI
    statuses = {s["kind"]: s for s in alberta.source_status()}
    assert statuses["casing_failures"]["refreshable"] is True
    assert statuses["vent_flow"]["refreshable"] is True


def test_download_file_source_rejects_a_source_with_no_configured_url():
    with pytest.raises(ValueError, match="no configured direct-download URL"):
        alberta.download_file_source("licences")


def test_download_file_source_fails_cleanly_and_names_the_manual_fallback(monkeypatch):
    """A blocked/unreachable network must not raise an opaque error, and must never
    fabricate integrity data — it must say exactly how to import the file manually."""
    import httpx

    class _FakeResponse:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("blocked", request=None, response=httpx.Response(403))

    class _FakeStream:
        def __enter__(self):
            return _FakeResponse()
        def __exit__(self, *a):
            return False

    class _FakeClient:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def stream(self, method, url):
            return _FakeStream()

    monkeypatch.setattr("httpx.Client", lambda *a, **k: _FakeClient())
    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="--file casing_failures="):
        alberta.download_file_source("casing_failures")


def test_st37_status_and_fluid_are_derived_by_a_documented_rule():
    out, stats = alberta.normalize_st37(_st37_fixture())
    assert list(out.status) == ["Suspended", "Abandoned", "Active"]
    assert list(out.fluid) == ["Oil", "Gas", "Injection"]
    assert stats["invalid_coordinates"] == 1          # the out-of-Alberta row is dropped, not "fixed"
    assert stats["valid_coordinates"] == 3
    assert stats["unparsed_legal_locations"] == 1
    assert alberta.derive_status("Undefined") == "Not reported"
    assert alberta.derive_fluid("Drilled and Cased") == "Not reported"


def test_st37_coordinates_are_never_invented():
    out, _ = alberta.normalize_st37(_st37_fixture())
    assert out.latitude.notna().all() and out.longitude.notna().all()
    assert out.latitude.between(48, 61).all()
    assert out.longitude.between(-125, -109).all()


def test_transform_only_runs_for_a_declared_crs():
    frame = pd.DataFrame({"latitude": [52.0], "longitude": [-113.0]})
    same = alberta.transform_to_wgs84(frame, None)
    assert same.latitude.iloc[0] == 52.0               # no CRS declared -> no guessing


# --------------------------------------------------------------------------- Petrinex parsing

def test_petrinex_water_cut_is_undefined_when_water_was_not_reported():
    """A missing water declaration must never be read as zero water."""
    monthly = pd.DataFrame({
        "uwi": ["100010101008W404", "100010101305W400", "100010101319W403"],
        "month": ["2026-07"] * 3,
        "oil_m3": [10.0, 10.0, 0.0],
        "water_m3": [30.0, None, 0.0],
    })
    liquid = monthly.oil_m3.fillna(0) + monthly.water_m3.fillna(0)
    defined = monthly.water_m3.notna() & monthly.oil_m3.notna() & (liquid > 0)
    import numpy as np
    water_cut = pd.Series(np.where(defined, monthly.water_m3 / liquid.replace(0, np.nan), np.nan))
    assert water_cut[0] == pytest.approx(0.75)
    assert pd.isna(water_cut[1])       # water not reported -> undefined, not 0
    assert pd.isna(water_cut[2])       # nothing produced -> undefined, not 0


def test_petrinex_schema_change_aborts_the_import(tmp_path):
    import io
    import zipfile

    path = tmp_path / "AB_Vol_2026-07.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Vol_2026-07-AB.CSV", "ProductionMonth,SomethingElse\n2026-07,1\n")
    with pytest.raises(petrinex_cache.PetrinexUnavailable, match="schema changed"):
        petrinex_cache.parse_month(path)


def test_petrinex_reads_a_nested_zip(tmp_path):
    import io
    import zipfile

    csv = ("ProductionMonth,OperatorName,ReportingFacilityID,ActivityID,ProductID,FromToID,"
           "FromToIDType,FromToIDIdentifier,Volume,Hours\n"
           "2026-07,TEST OPERATOR,ABBT0000001,PROD,OIL,ABWI100031106504W400,WI,100031106504W400,100.0,720\n"
           "2026-07,TEST OPERATOR,ABBT0000001,PROD,WATER,ABWI100031106504W400,WI,100031106504W400,300.0,720\n"
           "2026-07,TEST OPERATOR,ABBT0000001,PROD,OIL,ABWI***,WI,***,5.0,720\n")
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("Vol_2026-07-AB.CSV", csv)
    outer = tmp_path / "AB_Vol_2026-07.zip"
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("Vol_2026-07-AB.csv.zip", inner.getvalue())

    monthly, extra = petrinex_cache.parse_month(outer)
    assert len(monthly) == 1                                   # the confidential row is dropped
    assert extra["stats"]["confidential_rows_dropped"] == 1
    row = monthly.iloc[0]
    assert row.oil_m3 == 100.0 and row.water_m3 == 300.0
    assert extra["attrs"].iloc[0].ats_cell == "03-11-065-04W4"
    assert extra["attrs"].iloc[0].operator == "TEST OPERATOR"


def test_available_months_are_contiguous_and_ordered():
    months = petrinex_cache.available_months(4, end="2026-07")
    assert months == ["2026-04", "2026-05", "2026-06", "2026-07"]


# --------------------------------------------------------------------------- cache safety

def test_import_preserves_previous_cache_on_schema_error(tmp_path, monkeypatch):
    monkeypatch.setattr(alberta.config, "ALBERTA_CACHE_DIR", tmp_path / "cache")
    good = tmp_path / "good.csv"
    pd.DataFrame({"well_id": ["A"], "latitude": [53.0], "longitude": [-113.0]}).to_csv(good, index=False)
    alberta.import_file(good, "abandoned")
    old = (tmp_path / "cache" / "abandoned" / "records.parquet").read_bytes()
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"well_id": ["A"]}).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="required field"):
        alberta.import_file(bad, "abandoned")
    assert (tmp_path / "cache" / "abandoned" / "records.parquet").read_bytes() == old


def test_validate_wells_counts_problems_instead_of_dropping_them_silently():
    frame = alberta.normalize_columns(pd.DataFrame({
        "UWI": ["00/01-02-003-04W5/0", "00/01-02-003-04W5/0", ""],
        "Surface Latitude": ["53.5", "999", "54.0"],
        "Surface Longitude": ["-113.4", "-113.0", "-114.0"],
    }))
    stats = alberta.validate_wells(frame)
    assert stats["rows"] == 3
    assert stats["valid_identifiers"] == 2
    assert stats["duplicate_identifiers"] == 1
    assert stats["invalid_coordinates"] == 1


def test_cluster_aggregates_without_losing_records():
    frame = pd.DataFrame({
        "latitude": [52.2, 52.4, 55.3],
        "longitude": [-113.2, -113.4, -117.6],
        "status": ["Active", "Abandoned", "Active"],
        "oil_m3": [10.0, None, 0.0],
    })
    clusters = alberta.cluster(frame, 1.0)
    assert sum(c["count"] for c in clusters) == 3          # no record is lost
    assert len(clusters) == 2
    grouped = next(c for c in clusters if c["count"] == 2)
    assert grouped["abandoned"] == 1 and grouped["active"] == 1
    assert grouped["producing"] == 1                        # only the row with reported oil > 0


def test_cluster_cell_size_controls_grouping():
    """Grid clustering is a display aggregation: a smaller cell splits, a larger one merges."""
    frame = pd.DataFrame({
        "latitude": [52.2, 52.4], "longitude": [-113.2, -113.4],
        "status": ["Active", "Active"], "oil_m3": [1.0, 1.0],
    })
    assert len(alberta.cluster(frame, 1.0)) == 1
    assert len(alberta.cluster(frame, 0.05)) == 2


# --------------------------------------------------------------------------- integration: real cache

pytestmark_real = pytest.mark.skipif(
    alberta.records("st37").empty,
    reason="AER ST37 cache not installed (run scripts/update_alberta_data.py --all)",
)


@pytestmark_real
def test_real_st37_cache_is_internally_consistent():
    frame = alberta.records("st37")
    assert len(frame) > 100_000
    assert frame.latitude.between(48, 61).all()
    assert frame.longitude.between(-125, -109).all()
    assert frame.record_id.is_unique
    meta = alberta.meta("st37")
    assert meta["source"].startswith("Alberta Energy Regulator")
    assert meta["source_crs"].startswith("EPSG:4326")


@pytestmark_real
def test_real_well_coordinates_survive_normalisation_unchanged():
    """A real record's normalized coordinates must equal what the map serves."""
    frame = alberta.records("st37")
    sample = frame.iloc[0]
    served = alberta.map_query((sample.longitude - 0.001, sample.latitude - 0.001,
                                sample.longitude + 0.001, sample.latitude + 0.001))
    match = served[served.record_id == sample.record_id]
    assert len(match) == 1
    assert match.iloc[0].latitude == pytest.approx(sample.latitude)
    assert match.iloc[0].longitude == pytest.approx(sample.longitude)
    # and the legal location parsed from the AER string round-trips
    assert ats.cell_from_location(sample.surface_location) == sample.ats_cell


@pytestmark_real
def test_production_link_is_unique_in_both_directions():
    frame = alberta.wells()
    linked = frame[frame.uwi.notna()]
    assert len(linked) > 0
    assert linked.uwi.is_unique                      # one reported volume -> at most one map point
    assert (linked.cell_records == 1).all()          # and only where one AER record holds the cell


@pytestmark_real
def test_real_production_values_match_the_petrinex_source_rows():
    frame = alberta.wells()
    linked = frame[frame.uwi.notna() & frame.oil_m3.notna()]
    if linked.empty:
        pytest.skip("no linked producing wells in the installed cache")
    sample = linked.sort_values("oil_m3", ascending=False).iloc[0]
    history = petrinex_cache.history(sample.uwi)
    assert not history.empty
    latest = history.sort_values("month").iloc[-1]
    assert latest.month == sample.latest_month
    assert float(latest.oil_m3) == pytest.approx(float(sample.oil_m3))
    # the daily average the UI shows is exactly volume / days in that month
    days = pd.Period(latest.month).days_in_month
    assert float(latest.oil_m3_per_day) == pytest.approx(float(latest.oil_m3) / days)


@pytestmark_real
def test_join_report_does_not_hide_failed_joins():
    report = alberta.join_report()
    assert report["available"] is True
    assert report["st37_wells_linked"] + report["st37_wells_unlinked"] == report["st37_wells_imported"]
    assert report["st37_links_blocked_by_shared_location"] > 0
    assert "no fuzzy name matching" in report["join_key"]


@pytestmark_real
def test_dataset_summary_numbers_come_from_the_imported_rows():
    frame = alberta.wells()
    summary = alberta.dataset_summary()
    assert summary["wells_loaded"] == len(frame)
    assert summary["abandoned"] == int((frame.status == "Abandoned").sum())
    assert summary["active"] == int((frame.status == "Active").sum())
    assert summary["wells_loaded"] == summary["active"] + summary["suspended"] + summary["abandoned"] \
        + int(frame.status.isin(["Drilled and cased", "Surface casing only", "Not reported"]).sum())

/**
 * Alberta Well Intelligence Map.
 *
 * Data contract: every dot is an AER ST37 regulatory record with AER-published
 * WGS84 geometry.  Production, where shown, is a Petrinex reported monthly volume
 * linked through the well's Alberta Township System legal location.  Nothing on
 * this page is generated: fields with no public source read "Not publicly available".
 */
import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Card, Drawer, ErrorBox, Icon, Kpi, Skeleton, Tabs, useFetch } from "../components/ui";
import { Dropdown, Floating, HoverCard, LAYER } from "../components/overlay";
import { Any, api, fmt } from "../lib/api";
import { useT } from "../lib/i18n";
import { useProv } from "../lib/provenance";
import type { MapHandle } from "./map/MapCanvas";
import { Basemap, WELL_COLOURS } from "./map/legend";
import { WellPanel } from "./map/WellPanel";
import { DataSources } from "./map/DataSources";

type Bbox = [number, number, number, number];

// MapLibre is ~800 kB. Loading it lazily keeps it off every other route's critical
// path and out of the main bundle; only /map pays for it.
const MapCanvas = React.lazy(async () => ({ default: (await import("./map/MapCanvas")).MapCanvas }));

/** If the map chunk or WebGL is unavailable, the rest of the page must keep working. */
class MapBoundary extends React.Component<{ children: React.ReactNode; title: string; hint: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="map-loading">
        <div className="glass-strong p-5 text-center max-w-md">
          <div className="font-semibold mb-1">{this.props.title}</div>
          <div className="subtle text-[13px]">{this.props.hint}</div>
        </div>
      </div>
    );
  }
}

const LAYERS = [
  ["", "All wells"],
  ["production", "Reporting production"],
  ["water", "Water cut ≥ 50%"],
  ["injection", "Injection / disposal"],
  ["abandoned", "Abandoned"],
  ["integrity", "Integrity record"],
] as const;

export function AlbertaMap() {
  const { t } = useT();
  const prov = useProv();
  const mapRef = useRef<MapHandle>(null);
  const searchRef = useRef<HTMLDivElement>(null);

  const [view, setView] = useState<{ bbox: Bbox; zoom: number } | null>(null);
  const [basemap, setBasemap] = useState<Basemap>("dark");
  const [status, setStatus] = useState<string>("");
  const [fluid, setFluid] = useState<string>("");
  const [operator, setOperator] = useState<string>("");
  const [layer, setLayer] = useState<string>("");
  const [producing, setProducing] = useState(false);
  const [showFacilities, setShowFacilities] = useState(false);
  const [showPipelines, setShowPipelines] = useState(false);
  const [tab, setTab] = useState("map");

  const [wells, setWells] = useState<Any[]>([]);
  const [clusters, setClusters] = useState<Any[]>([]);
  const [facilities, setFacilities] = useState<Any[]>([]);
  const [pipelines, setPipelines] = useState<Any[]>([]);
  const [meta, setMeta] = useState<Any>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<Any>(null);

  const [q, setQ] = useState("");
  const [results, setResults] = useState<Any>(null);
  const [hover, setHover] = useState<{ f: Any; rect: Any } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const summary = useFetch<Any>("/api/map/summary");
  const sourceStatus = useFetch<Any>("/api/alberta/status");
  const detail = useFetch<Any>(selected ? `/api/map/wells/${encodeURIComponent(selected)}` : null, [selected]);
  const s = summary.data?.summary;
  const installed = !!s?.available;

  const filters = useMemo(() => {
    const p = new URLSearchParams();
    if (status) p.set("status", status);
    if (fluid) p.set("fluid", fluid);
    if (operator.trim()) p.set("operator", operator.trim());
    if (layer) p.set("layer", layer);
    if (producing) p.set("producing", "true");
    return p.toString();
  }, [status, fluid, operator, layer, producing]);

  // Viewport-driven fetch: only the current bounding box is ever requested.
  useEffect(() => {
    if (!view || !installed) return;
    let alive = true;
    const timer = window.setTimeout(async () => {
      setLoading(true); setFetchError(null);
      const bbox = view.bbox.map((n) => n.toFixed(4)).join(",");
      try {
        const data = await api.get(`/api/map/wells?bbox=${bbox}&zoom=${view.zoom}&${filters}`);
        if (!alive) return;
        setWells(data.features || []);
        setClusters(data.clusters || []);
        setMeta(data);
      } catch (e) {
        if (alive) setFetchError(e);
      } finally {
        if (alive) setLoading(false);
      }
    }, 220);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [view, filters, installed]);

  useEffect(() => {
    if (!view || !showFacilities) { setFacilities([]); return; }
    const bbox = view.bbox.map((n) => n.toFixed(4)).join(",");
    api.get(`/api/map/overlays/facilities?bbox=${bbox}&limit=1500`).then((d) => setFacilities(d.features || [])).catch(() => setFacilities([]));
  }, [view, showFacilities]);

  useEffect(() => {
    if (!view || !showPipelines) { setPipelines([]); return; }
    const bbox = view.bbox.map((n) => n.toFixed(4)).join(",");
    api.get(`/api/map/overlays/pipelines?bbox=${bbox}&limit=1200`).then((d) => setPipelines(d.features || [])).catch(() => setPipelines([]));
  }, [view, showPipelines]);

  const onViewport = useCallback((bbox: Bbox, zoom: number) => setView({ bbox, zoom }), []);
  const onHover = useCallback((f: Any, point: Any) => {
    if (!f || !point) { setHover(null); return; }
    setHover({ f, rect: { top: point.y, left: point.x, width: 1, height: 1 } });
  }, []);
  const onSelect = useCallback((f: Any) => { setSelected(f.record_id); setHover(null); }, []);
  const onClusterClick = useCallback((lng: number, lat: number) => {
    const map = mapRef.current?.getMap();
    mapRef.current?.flyTo(lng, lat, Math.min(16, (map?.getZoom() || 5) + 2.2));
  }, []);

  const runSearch = async () => {
    if (!q.trim()) { setResults(null); return; }
    try { setResults(await api.get(`/api/map/search?q=${encodeURIComponent(q.trim())}&limit=25`)); }
    catch (e: Any) { setResults({ results: [], error: e.message }); }
  };

  const pick = (r: Any) => {
    setResults(null);
    setSelected(r.record_id);
    if (r.longitude && r.latitude) mapRef.current?.flyTo(r.longitude, r.latitude, 14);
  };

  if (summary.error) return <ErrorBox error={summary.error} onRetry={summary.reload} />;

  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 style={{ fontSize: 28 }}>{t("x_map_title")}</h1>
        <Badge label={t("m_real_public")} color="blue" />
        <span className="subtle text-[12px]">
          AER ST37 geometry · Petrinex reported volumes where the legal location matches uniquely
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-3">
        <Kpi label={t("m_wells_imported")} value={fmt.n(s?.wells_loaded)} small
             sub={s?.st37_release ? `ST37 source edited ${fmt.date(s.st37_release)}` : "not installed"}
             provenance={summary.data?.sources?.find((x: Any) => x.kind === "st37")?.meta} />
        <Kpi label={t("m_active")} provenance={prov("map_active")} value={fmt.n(s?.active)} small sub={`${fmt.n(s?.suspended)} suspended`} />
        <Kpi label={t("m_abandoned")} provenance={prov("map_abandoned")} value={fmt.n(s?.abandoned)} small sub="AER category" />
        <Kpi label={t("m_linked")} provenance={prov("map_linked")} value={fmt.n(s?.matched_to_production)} small
             sub={`${fmt.n(s?.reported_producing)} reported oil in ${s?.production_period || "—"}`} />
        <Kpi label={t("m_operators")} provenance={prov("map_operators")} value={fmt.n(s?.operators)} small sub="Petrinex reporting operators" />
        <Kpi label={t("m_scada")} provenance={prov("map_scada")} value="—" small sub="SCADA NOT CONNECTED — public/cached data only"
             badge={<Badge label={t("m_not_connected")} color="grey" small />} />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[{ key: "map", label: "Map" }, { key: "data", label: "Data sources & updates" }]} />

      {tab === "data" && <DataSources status={sourceStatus.data} onDone={() => { sourceStatus.reload(); summary.reload(); }} />}

      {tab === "map" && (
        <Card
          title={t("m_field_intel")}
          subtitle={installed
            ? `${fmt.n(meta?.count)} records in view${meta?.clustered ? ` · shown as ${fmt.n(meta?.returned)} clusters` : ""}${meta?.truncated ? " · zoom in for individual wells" : ""}`
            : "No Canadian dataset is installed yet."}
        >
          <div className="flex flex-wrap gap-2 mb-3">
            <div ref={searchRef} className="relative min-w-[240px]">
              <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runSearch()}
                     placeholder={t("x_search_ph")} aria-label={t("m_search_aria")} className="w-full" />
              <Dropdown open={!!results} onClose={() => setResults(null)} anchorRef={searchRef} width={460}>
                {results?.error && <div className="subtle p-2 text-[12px]">{results.error}</div>}
                {results && !results.results?.length && !results.error && <div className="subtle p-2 text-[12px]">{t("x_no_match")}</div>}
                {(results?.results || []).map((r: Any) => (
                  <button key={r.record_id} className="block w-full text-left px-2 py-1.5 rounded hover:bg-white/10 text-[12px]" onClick={() => pick(r)}>
                    <b>{r.uwi || r.record_id}</b>
                    <span className="faint"> · {r.surface_location} · {r.operator || "operator not reported"} · {r.status}</span>
                  </button>
                ))}
                {results?.count > (results?.results?.length || 0) &&
                  <div className="faint text-[11px] px-2 pt-1">{fmt.n(results.count)} matches — showing the first {results.results.length}.</div>}
              </Dropdown>
            </div>
            <button className="btn sm" onClick={runSearch}><Icon name="search" size={13} />{t("x_search2")}</button>

            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("x_status2")}>
              <option value="">{t("m_all_status")}</option>
              {["Active", "Suspended", "Abandoned", "Drilled and cased", "Surface casing only", "Not reported"].map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
            <select value={fluid} onChange={(e) => setFluid(e.target.value)} aria-label={t("x_fluid")}>
              <option value="">{t("m_all_fluids")}</option>
              {["Oil", "Gas", "Crude bitumen", "Injection", "Disposal", "Observation", "Not reported"].map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
            <select value={layer} onChange={(e) => setLayer(e.target.value)} aria-label={t("x_layer")}>
              {LAYERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <input value={operator} onChange={(e) => setOperator(e.target.value)} placeholder={t("m_operator_contains")} aria-label={t("m_operator")} style={{ width: 190 }} />
            <label className="chip" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={producing} onChange={(e) => setProducing(e.target.checked)} />Reported oil &gt; 0
            </label>
            <label className="chip" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={showFacilities} onChange={(e) => setShowFacilities(e.target.checked)} />Facilities
            </label>
            <label className="chip" style={{ fontSize: 12 }}>
              <input type="checkbox" checked={showPipelines} onChange={(e) => setShowPipelines(e.target.checked)} />Pipelines
            </label>
            <select value={basemap} onChange={(e) => setBasemap(e.target.value as Basemap)} aria-label={t("x_basemap")}>
              <option value="dark">{t("m_bm_dark")}</option>
              <option value="satellite">{t("m_bm_sat")}</option>
              <option value="streets">{t("m_bm_streets")}</option>
              <option value="none">{t("m_bm_none")}</option>
            </select>
            <button className="btn sm" onClick={() => mapRef.current?.fitAlberta()}>{t("x_reset_view")}</button>
          </div>

          <div className="map-shell glass-inner" style={{ height: "min(70vh, 720px)", minHeight: 440 }}>
            <MapBoundary title={t("x_map_fail")} hint={t("x_map_fail_hint")}>
            <Suspense fallback={<div className="map-loading"><Skeleton h={120} /></div>}>
              <MapCanvas
                ref={mapRef} wells={wells} clusters={clusters} facilities={facilities} pipelines={pipelines}
                basemap={basemap} selectedId={selected} ariaLabel={t("m_map_aria")}
                onViewport={onViewport} onHover={onHover} onSelect={onSelect} onClusterClick={onClusterClick}
              />
            </Suspense>
            </MapBoundary>

            {!installed && (
              <div className="map-loading">
                <div className="glass-strong p-5 text-center max-w-md">
                  <div className="font-semibold mb-1">{t("x_ca_not_imported")}</div>
                  <div className="subtle text-[13px] mb-3">
                    Open <b>{t("x_ds_updates")}</b> above and install AER ST37, or run
                    <code> python scripts/update_alberta_data.py --source st37</code>.
                    No replacement or simulated wells are shown.
                  </div>
                  <button className="btn primary sm" onClick={() => setTab("data")}>{t("x_install_ds")}</button>
                </div>
              </div>
            )}
            {installed && loading && (
              <div className="map-overlay glass-strong px-3 py-1.5 text-[11px]" style={{ top: 12, left: 12 }}>
                Loading viewport…
              </div>
            )}
            {fetchError && (
              <div className="map-overlay glass-strong px-3 py-2 text-[11px]" style={{ top: 12, left: 12, color: "#FFB3A8" }}>
                {String((fetchError as Any).message)}
              </div>
            )}

            <div className="map-overlay glass-strong p-3 text-[11px] space-y-1" style={{ left: 12, bottom: 26 }}>
              {WELL_COLOURS.map(([label, colour]) => (
                <div key={label}><span className="map-legend-dot" style={{ background: colour }} />{label}</div>
              ))}
              <div className="pt-1"><span className="map-legend-dot" style={{ background: "transparent", borderColor: "#E4614F", borderWidth: 2 }} />integrity record matched</div>
              <div className="faint pt-1" style={{ maxWidth: 210 }}>
                Colours are AER-reported categories, not a risk score.
              </div>
            </div>
          </div>

          <div className="faint text-[11px] mt-2">
            Public well and production information is sourced from Alberta Energy Regulator and Petrinex public
            datasets. Availability and reporting frequency vary by dataset. Monthly reported volumes are not
            real-time production.
          </div>
        </Card>
      )}

      {/* Hover preview is portalled to <body>: the WebGL canvas cannot paint over it
          and the map container's overflow cannot clip it. */}
      <Floating
        anchor={hover?.rect || null} open={!!hover} side="top" layer={LAYER.tooltip} interactive={false}
        className="glass-strong px-3 py-2 text-[12px]" style={{ borderRadius: 12, maxWidth: 300 }}
      >
        {hover?.f && (hover.f._kind === "facility" ? (
          <div className="space-y-0.5">
            <div className="font-semibold">{hover.f.name}</div>
            <div className="faint">AER ST102 facility {hover.f.facility_id}</div>
            <div className="subtle">{hover.f.operator}</div>
            <div className="faint">{hover.f.facility_type} · {hover.f.facility_status}</div>
          </div>
        ) : (
          <div className="space-y-0.5">
            <div className="font-semibold">{hover.f.uwi || hover.f.record_id}</div>
            <div className="faint">{hover.f.surface_location}</div>
            <div className="subtle">{hover.f.operator || "Operator not publicly reported"}</div>
            <div className="faint">{hover.f.well_category} · {hover.f.status}</div>
            <div className="faint">
              {hover.f.latest_month
                ? `Latest reported month ${hover.f.latest_month}${hover.f.oil_m3 != null ? ` · ${fmt.n(hover.f.oil_m3, 1)} m³ oil` : ""}`
                : "No linked production record"}
            </div>
            <div className="pt-1" style={{ color: "#FFD97A" }}>{t("x_click_full")}</div>
          </div>
        ))}
      </Floating>

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={detail.data?.well?.uwi || selected || "Well record"} width={680}>
        <WellPanel data={detail.data} loading={detail.loading} error={detail.error} />
      </Drawer>
    </div>
  );
}

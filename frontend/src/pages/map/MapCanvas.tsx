/**
 * MapLibre GL canvas for the Alberta well map.
 *
 * Performance contract (the ST37 dataset is ~475,000 wells):
 *  - The browser NEVER receives the whole dataset.  Every viewport change asks the
 *    API for the current bounding box only.
 *  - Below zoom 11 the API returns server-computed grid clusters, so the map draws
 *    a few hundred circles instead of hundreds of thousands.
 *  - Wells are drawn as GL circle layers from one GeoJSON source, not as DOM
 *    markers, so panning stays smooth.
 *
 * Hover/selection UI is NOT drawn inside this container: the hover card is
 * portalled to <body> by the parent (see components/overlay.tsx) so the WebGL
 * canvas can never paint over it and the map's `overflow: hidden` can never clip it.
 */
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import React, { useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Any } from "../../lib/api";
import { Basemap, WELL_COLOURS } from "./legend";

/**
 * Key-free public basemaps. Esri's Canvas services match the product's dark
 * palette; OpenStreetMap is offered for street context. If a tile host is
 * unreachable (offline demo, restricted network) MapLibre simply draws no
 * raster and the well layers still render on the app background.
 */
const RASTER: Record<Exclude<Basemap, "none">, { tiles: string[]; attribution: string; reference?: string }> = {
  dark: {
    tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
    reference: "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
  },
  satellite: {
    tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
    reference: "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri World Imagery — Maxar, Earthstar Geographics",
  },
  streets: {
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: "© OpenStreetMap contributors",
  },
};

function style(basemap: Basemap): Any {
  const sources: Any = {};
  const layers: Any[] = [
    { id: "bg", type: "background", paint: { "background-color": "#0A0F1B" } },
  ];
  if (basemap !== "none") {
    const spec = RASTER[basemap];
    sources.base = { type: "raster", tiles: spec.tiles, tileSize: 256, attribution: spec.attribution, maxzoom: 17 };
    layers.push({ id: "base", type: "raster", source: "base",
                  paint: { "raster-opacity": basemap === "satellite" ? 0.95 : 1 } });
    if (spec.reference) {
      sources.baseRef = { type: "raster", tiles: [spec.reference], tileSize: 256, maxzoom: 17 };
      layers.push({ id: "base-ref", type: "raster", source: "baseRef",
                    paint: { "raster-opacity": 0.75 } });
    }
  }
  return { version: 8, sources, layers };
}

const EMPTY = { type: "FeatureCollection", features: [] } as Any;

export type MapHandle = {
  flyTo: (lng: number, lat: number, zoom?: number) => void;
  fitAlberta: () => void;
  getMap: () => maplibregl.Map | null;
};

export const MapCanvas = React.forwardRef<MapHandle, {
  wells: Any[];
  clusters: Any[];
  facilities: Any[];
  pipelines: Any[];
  basemap: Basemap;
  selectedId?: string | null;
  /** Accessible name, passed in because this forwardRef body cannot use hooks. */
  ariaLabel?: string;
  onViewport: (bbox: [number, number, number, number], zoom: number) => void;
  onHover: (feature: Any | null, point: { x: number; y: number } | null) => void;
  onSelect: (feature: Any) => void;
  onClusterClick: (lng: number, lat: number) => void;
}>(function MapCanvas(props, ref) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  // Cluster counts are drawn as HTML labels rather than a GL symbol layer so the
  // map needs no external glyph server and stays readable offline. There are only
  // a few hundred clusters, so the DOM cost is negligible.
  const [labels, setLabels] = useState<{ id: string; x: number; y: number; text: string }[]>([]);
  const latest = useRef(props);
  latest.current = props;

  const projectLabels = useCallback(() => {
    const m = map.current;
    if (!m) { setLabels([]); return; }
    setLabels((latest.current.clusters || []).map((c: Any) => {
      const p = m.project([c.longitude, c.latitude]);
      return { id: c.id, x: p.x, y: p.y,
               text: c.count >= 1000 ? `${(c.count / 1000).toFixed(c.count >= 10000 ? 0 : 1)}k` : String(c.count) };
    }));
  }, []);


  useImperativeHandle(ref, () => ({
    flyTo: (lng, lat, zoom = 13) => map.current?.flyTo({ center: [lng, lat], zoom, duration: 900 }),
    fitAlberta: () => map.current?.fitBounds([[-120.1, 48.9], [-109.9, 60.1]], { padding: 24, duration: 700 }),
    getMap: () => map.current,
  }));

  // ---- init once
  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({
      container: container.current,
      style: style(latest.current.basemap),
      bounds: [[-120.1, 48.9], [-109.9, 60.1]],
      fitBoundsOptions: { padding: 20 },
      maxBounds: [[-134, 42], [-96, 66]],
      minZoom: 3.5,
      maxZoom: 17,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.current = m;
    // Debug handle: lets `window.__coreMap` be inspected when diagnosing a map issue.
    (window as Any).__coreMap = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    m.touchZoomRotate.disableRotation();

    const emitViewport = () => {
      const b = m.getBounds();
      latest.current.onViewport(
        [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
        Number(m.getZoom().toFixed(2)),
      );
    };

    // Data layers are attached on `styledata` (fires as soon as the style JSON is
    // applied) rather than on `load`. `load` waits for every source — including the
    // raster basemap — to finish, so a slow, blocked or offline tile host would
    // otherwise leave the well layers permanently unattached. addLayers is
    // idempotent, so this also re-attaches them after a basemap switch.
    const attach = () => {
      if (!m.style || !m.isStyleLoaded() || m.getLayer("wells")) return;
      addLayers(m);
      ready.current = true;
      pushData(m, latest.current);
      projectLabels();
    };
    m.on("styledata", attach);
    m.on("idle", attach);
    m.once("idle", emitViewport);
    window.setTimeout(emitViewport, 0);
    m.on("moveend", emitViewport);
    m.on("move", () => projectLabels());
    m.on("zoom", () => projectLabels());

    // The card can lay out after the map is constructed (tabs, KPI wrap, window
    // resize), which would leave the GL canvas at a stale size — and the initial
    // fit-to-Alberta would then be computed for the wrong viewport. Re-fit once the
    // container has settled at its real size.
    let fitted = false;
    // Never re-frame the map once the user has taken control of it.
    const lockFit = () => { fitted = true; };
    m.on("dragstart", lockFit);
    m.on("zoomstart", lockFit);
    const observer = new ResizeObserver(() => {
      m.resize();
      if (!fitted && container.current && container.current.clientWidth > 400) {
        fitted = true;
        m.fitBounds([[-120.1, 48.9], [-109.9, 60.1]], { padding: 20, animate: false });
      }
    });
    observer.observe(container.current);

    m.on("mousemove", "wells", (e) => {
      m.getCanvas().style.cursor = "pointer";
      const f = e.features?.[0];
      if (f) latest.current.onHover(f.properties, { x: e.originalEvent.clientX, y: e.originalEvent.clientY });
    });
    m.on("mouseleave", "wells", () => { m.getCanvas().style.cursor = ""; latest.current.onHover(null, null); });
    m.on("click", "wells", (e) => { const f = e.features?.[0]; if (f) latest.current.onSelect(f.properties); });
    m.on("mouseenter", "clusters", () => { m.getCanvas().style.cursor = "zoom-in"; });
    m.on("mouseleave", "clusters", () => { m.getCanvas().style.cursor = ""; });
    m.on("click", "clusters", (e) => {
      const f = e.features?.[0];
      if (f && f.geometry.type === "Point") {
        const [lng, lat] = (f.geometry as Any).coordinates;
        latest.current.onClusterClick(lng, lat);
      }
    });
    m.on("mousemove", "facilities", (e) => {
      const f = e.features?.[0];
      if (f) latest.current.onHover({ ...f.properties, _kind: "facility" },
                                    { x: e.originalEvent.clientX, y: e.originalEvent.clientY });
    });
    m.on("mouseleave", "facilities", () => latest.current.onHover(null, null));
    return () => { observer.disconnect(); m.remove(); map.current = null; ready.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- basemap swap keeps data layers
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    m.setStyle(style(props.basemap));
  }, [props.basemap]);

  // ---- data updates
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    pushData(m, props);
    projectLabels();
  }, [props.wells, props.clusters, props.facilities, props.pipelines, props.selectedId]);

  // Inline positioning on purpose: maplibre's own `.maplibregl-map { position: relative }`
  // rule would otherwise win over a utility class and collapse the container height.
  return (
    <>
      <div ref={container} style={{ position: "absolute", inset: 0 }} aria-label={props.ariaLabel || "Alberta well map"} />
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }} aria-hidden="true">
        {labels.map((l) => (
          <span key={l.id} style={{
            position: "absolute", left: l.x, top: l.y, transform: "translate(-50%,-50%)",
            fontSize: 11, fontWeight: 700, color: "#0C1220", letterSpacing: "-0.01em",
            textShadow: "0 0 3px rgba(255,255,255,0.6)",
          }}>{l.text}</span>
        ))}
      </div>
    </>
  );
});

function addLayers(m: maplibregl.Map) {
  const add = (id: string, src: Any) => { if (!m.getSource(id)) m.addSource(id, src); };
  add("pipelines", { type: "geojson", data: EMPTY });
  add("facilities", { type: "geojson", data: EMPTY });
  add("wells", { type: "geojson", data: EMPTY });
  add("clusters", { type: "geojson", data: EMPTY });
  add("selected", { type: "geojson", data: EMPTY });

  const layer = (spec: Any) => { if (!m.getLayer(spec.id)) m.addLayer(spec); };

  layer({ id: "pipelines", type: "line", source: "pipelines",
    paint: { "line-color": ["match", ["get", "substance"],
        "Natural Gas", "#4F6BE8", "Crude Oil", "#5CC489", "Fresh Water", "#5AC8E0",
        "Salt Water", "#B7C4FF", "#8E9AAF"],
      "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 12, 2.2],
      "line-opacity": 0.65 } });

  layer({ id: "facilities", type: "circle", source: "facilities",
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 3, 13, 7],
      "circle-color": "#F2B632", "circle-opacity": 0.85,
      "circle-stroke-width": 1, "circle-stroke-color": "rgba(12,18,32,0.9)" } });

  const colourExpr: Any = ["match", ["get", "fluid"],
    ...WELL_COLOURS.flatMap(([k, v]) => [k, v]), "#6B7488"];

  layer({ id: "wells", type: "circle", source: "wells",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 2.2, 10, 3.6, 13, 6, 16, 10],
      "circle-color": colourExpr,
      "circle-opacity": ["case", ["==", ["get", "status"], "Abandoned"], 0.45, 0.92],
      "circle-stroke-width": ["case", ["get", "integrity_record"], 2,
        ["==", ["get", "status"], "Suspended"], 1.4, 0.5],
      "circle-stroke-color": ["case", ["get", "integrity_record"], "#E4614F",
        ["==", ["get", "status"], "Suspended"], "#FFD97A", "rgba(10,15,27,0.85)"],
    } });

  layer({ id: "selected", type: "circle", source: "selected",
    paint: { "circle-radius": 12, "circle-color": "rgba(242,182,50,0.18)",
      "circle-stroke-width": 2.5, "circle-stroke-color": "#F2B632" } });

  layer({ id: "clusters", type: "circle", source: "clusters",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 11, 50, 15, 500, 21, 5000, 28, 50000, 38],
      "circle-color": ["interpolate", ["linear"], ["get", "count"], 1, "rgba(92,196,137,0.75)",
        200, "rgba(242,182,50,0.78)", 5000, "rgba(228,97,79,0.8)"],
      "circle-stroke-width": 1.5, "circle-stroke-color": "rgba(255,255,255,0.75)" } });

}

function pushData(m: maplibregl.Map, p: Any) {
  const set = (id: string, data: Any) => (m.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data);
  set("wells", {
    type: "FeatureCollection",
    features: (p.wells || []).map((w: Any) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [w.longitude, w.latitude] },
      properties: { ...w, integrity_record: !!w.integrity_record },
    })),
  });
  set("clusters", {
    type: "FeatureCollection",
    features: (p.clusters || []).map((c: Any) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [c.longitude, c.latitude] },
      properties: { ...c, label: c.count >= 1000 ? `${(c.count / 1000).toFixed(c.count >= 10000 ? 0 : 1)}k` : String(c.count) },
    })),
  });
  set("facilities", {
    type: "FeatureCollection",
    features: (p.facilities || []).filter((f: Any) => f.longitude && f.latitude).map((f: Any) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [f.longitude, f.latitude] }, properties: f,
    })),
  });
  set("pipelines", {
    type: "FeatureCollection",
    features: (p.pipelines || []).map((s: Any) => ({
      type: "Feature",
      geometry: { type: Array.isArray(s.geometry?.[0]?.[0]) ? "MultiLineString" : "LineString", coordinates: s.geometry },
      properties: { licence_no: s.licence_no, company_name: s.company_name, substance: s.substance, status: s.status },
    })),
  });
  const sel = (p.wells || []).find((w: Any) => w.record_id === p.selectedId);
  set("selected", sel ? { type: "FeatureCollection", features: [{ type: "Feature",
    geometry: { type: "Point", coordinates: [sel.longitude, sel.latitude] }, properties: {} }] } : EMPTY);
}

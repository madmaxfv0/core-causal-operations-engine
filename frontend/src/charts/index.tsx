import React, { useMemo, useRef, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Any, exportSvgAsPng, fmt } from "../lib/api";
import { useT } from "../lib/i18n";
import { Icon } from "../components/ui";

export const C = { amber: "#F2B632", blue: "#4F6BE8", green: "#5CC489", red: "#E4614F", ink: "#F4F5F7", muted: "rgba(244,245,247,0.55)", grid: "rgba(255,255,255,0.08)", lav: "#B7C4FF", teal: "#5AC8E0" };

export const TT = ({ active, payload, label, fmtv, extra }: Any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-strong p-3 text-[12px]" style={{ borderRadius: 12, minWidth: 150 }}>
      <div className="subtle mb-1">{label}</div>
      {payload.filter((p: Any) => p.value !== null && p.value !== undefined && p.name && !String(p.dataKey).startsWith("_")).map((p: Any) => <div key={p.dataKey} className="flex justify-between gap-3"><span style={{ color: p.color || p.stroke || C.ink }}>{p.name}</span><span className="font-medium">{fmtv ? fmtv(p.value, p.dataKey) : fmt.n(p.value, 1)}</span></div>)}
      {extra?.(payload[0]?.payload)}
    </div>
  );
};

export function ChartFrame({ children, name, height = 260, toolbar }: { children: React.ReactNode; name: string; height?: number; toolbar?: React.ReactNode }) {
  const { t } = useT();
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div>
      <div className="flex justify-end gap-2 mb-1 -mt-1">{toolbar}<button className="btn ghost sm" onClick={() => exportSvgAsPng(ref.current, `${name}.png`)} title={t("export_png")}><Icon name="download" size={13} />PNG</button></div>
      <div ref={ref} style={{ width: "100%", height }}><ResponsiveContainer>{children as Any}</ResponsiveContainer></div>
    </div>
  );
}

const Defs = () => (
  <defs>
    <linearGradient id="gAmber" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.amber} stopOpacity={0.55} /><stop offset="100%" stopColor={C.amber} stopOpacity={0.05} /></linearGradient>
    <linearGradient id="gBlue" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.blue} stopOpacity={0.5} /><stop offset="100%" stopColor={C.blue} stopOpacity={0.04} /></linearGradient>
    <linearGradient id="gBand" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.lav} stopOpacity={0.25} /><stop offset="100%" stopColor={C.lav} stopOpacity={0.08} /></linearGradient>
    <pattern id="hatch" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke={C.red} strokeWidth="2.5" strokeOpacity="0.7" /></pattern>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
  </defs>
);

// ------------------------------------------------------------------ HERO CHART
export function HeroChart({ analysis, height = 340, compact }: { analysis: Any; height?: number; compact?: boolean }) {
  const { t } = useT();
  const [win, setWin] = useState<"12" | "24" | "36" | "FULL">("FULL");
  const [donors, setDonors] = useState(false);
  const [naive, setNaive] = useState(true);
  const [band, setBand] = useState(true);
  const rows = useMemo(() => {
    if (!analysis?.actual) return [];
    const n = analysis.actual.length;
    let cum = 0;
    const out: Any[] = [];
    for (let i = 0; i < n; i++) {
      const rel = analysis.rel_months?.[i] ?? i;
      const post = rel >= 0;
      const a = analysis.actual[i], cf = analysis.counterfactual[i];
      const diff = post && a !== null && cf !== null ? a - cf : null;
      if (post && diff !== null) cum += diff * (analysis.days?.[i] || 30.4);
      const r: Any = { rel, month: analysis.months?.[i], actual: a, cf, lo: analysis.cf_lo?.[i], hi: analysis.cf_hi?.[i], diff, cum: post ? Math.round(cum) : null, naive: post ? analysis.naive_post_level : (rel >= -3 ? analysis.naive_pre_level : null) };
      r._bandBase = r.lo; r._bandSpan = r.hi !== null && r.lo !== null ? r.hi - r.lo : null;
      // causal effect area between cf and actual (positive and negative parts)
      r._effBase = post && a !== null && cf !== null ? Math.min(a, cf) : null;
      r._effPos = post && diff !== null && diff > 0 ? diff : 0;
      r._effNeg = post && diff !== null && diff < 0 ? -diff : 0;
      Object.entries(analysis.donor_paths || {}).forEach(([k, v]: Any) => { r[`d_${k}`] = v[i]; });
      out.push(r);
    }
    const lim = win === "FULL" ? 999 : Number(win);
    return out.filter((r) => Math.abs(r.rel) <= lim);
  }, [analysis, win]);
  if (!analysis?.actual?.length) return <div className="glass-inner p-6 subtle">{t("empty")}</div>;
  const donorKeys = Object.keys(analysis.donor_paths || {});
  const fmtv = (v: Any, k: string) => (k === "cum" ? `${fmt.n(v)} bbl` : `${fmt.n(v, 1)} bbl/d`);
  return (
    <div>
      {!compact && (
        <div className="flex flex-wrap items-center gap-2 mb-2">
          {(["12", "24", "36", "FULL"] as const).map((w) => <button key={w} className={`chip ${win === w ? "amber" : ""}`} style={{ padding: "5px 11px", fontSize: 12 }} onClick={() => setWin(w)}>{w === "FULL" ? "FULL" : `${w}M`}</button>)}
          <span className="flex-1" />
          <label className="chip cursor-pointer" style={{ padding: "5px 11px", fontSize: 12 }}><input type="checkbox" checked={donors} onChange={(e) => setDonors(e.target.checked)} />{t("show_donors")}</label>
          <label className="chip cursor-pointer" style={{ padding: "5px 11px", fontSize: 12 }}><input type="checkbox" checked={naive} onChange={(e) => setNaive(e.target.checked)} />{t("show_naive")}</label>
          <label className="chip cursor-pointer" style={{ padding: "5px 11px", fontSize: 12 }}><input type="checkbox" checked={band} onChange={(e) => setBand(e.target.checked)} />{t("show_band")}</label>
        </div>
      )}
      <ChartFrame name={`counterfactual_${analysis.well_id}`} height={height}>
        <ComposedChart data={rows} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
          <Defs />
          <CartesianGrid vertical={false} stroke={C.grid} />
          <XAxis dataKey="rel" tickFormatter={(v) => (v === 0 ? "0" : v > 0 ? `+${v}` : String(v))} tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={44} />
          <Tooltip content={<TT fmtv={fmtv} extra={(p: Any) => p && <div className="faint mt-1">{p.month} · {t("difference")}: {p.diff === null ? "—" : fmt.n(p.diff, 1)} bbl/d · {t("cumulative")}: {p.cum === null ? "—" : fmt.n(p.cum)} bbl</div>} />} />
          {band && <Area dataKey="_bandBase" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} legendType="none" />}
          {band && <Area dataKey="_bandSpan" stackId="band" stroke="none" fill="url(#gBand)" name={t("hero_band")} isAnimationActive={false} />}
          <Area dataKey="_effBase" stackId="eff" stroke="none" fill="transparent" isAnimationActive={false} legendType="none" />
          <Area dataKey="_effPos" stackId="eff" stroke="none" fill={C.amber} fillOpacity={0.45} name={t("hero_causal_area")} isAnimationActive={false} />
          <Area dataKey="_effNeg" stackId="eff" stroke="none" fill={C.red} fillOpacity={0.45} legendType="none" isAnimationActive={false} />
          {donors && donorKeys.map((k) => <Line key={k} dataKey={`d_${k}`} name={k} stroke={C.muted} strokeWidth={1} dot={false} strokeDasharray="2 3" isAnimationActive={false} />)}
          {naive && <Line dataKey="naive" name={t("hero_naive")} stroke={C.red} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />}
          <Line dataKey="cf" name={t("hero_cf")} stroke={C.lav} strokeWidth={2.4} dot={false} strokeDasharray="1 0" isAnimationActive={false} style={{ filter: "url(#glow)" }} />
          <Line dataKey="actual" name={t("hero_actual")} stroke={C.amber} strokeWidth={2.6} dot={{ r: 2, fill: C.amber, strokeWidth: 0 }} isAnimationActive={false} style={{ filter: "url(#glow)" }} />
          <ReferenceLine x={0} stroke={C.ink} strokeOpacity={0.6} strokeDasharray="3 3" label={{ value: t("intervention"), fill: C.muted, fontSize: 11, position: "insideTopRight" }} />
          {!compact && <Legend wrapperStyle={{ fontSize: 11, color: C.muted }} iconSize={10} />}
        </ComposedChart>
      </ChartFrame>
      {!compact && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 text-[12px]">
          <div className="glass-inner p-3"><div className="faint">{t("naive_estimate")}</div><div className="text-[18px] font-semibold" style={{ color: C.red }}>{fmt.n(analysis.naive_effect_bpd, 1)} <span className="faint text-[11px]">bbl/d</span></div><div className="faint">{fmt.n(analysis.naive_cumulative_bbl)} bbl</div></div>
          <div className="glass-inner p-3"><div className="faint">{t("causal_estimate")}</div><div className="text-[18px] font-semibold" style={{ color: C.amber }}>{fmt.n(analysis.mean_effect_bpd, 1)} <span className="faint text-[11px]">bbl/d</span></div><div className="faint">{t("range")} {fmt.range(analysis.effect_lo_bpd, analysis.effect_hi_bpd, 1)}</div></div>
          <div className="glass-inner p-3"><div className="faint">{t("cumulative_oil")}</div><div className="text-[18px] font-semibold">{fmt.n(analysis.cumulative_effect_bbl)} <span className="faint text-[11px]">bbl</span></div><div className="faint">{t("range")} {fmt.range(analysis.cumulative_lo_bbl, analysis.cumulative_hi_bbl)}</div></div>
          <div className="glass-inner p-3"><div className="faint">{t("model")}</div><div className="text-[14px] font-semibold">{analysis.model_label}</div><div className="faint">{analysis.diagnostics?.donor_count} {t("donors").toLowerCase()} · R² {fmt.n(analysis.diagnostics?.pre_r2, 2)}</div></div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ others
export function TrendChart({ data, xKey = "month", series, height = 240, name = "trend", stacked }: { data: Any[]; xKey?: string; series: { key: string; name: string; color?: string; type?: "area" | "line" | "bar"; axis?: "left" | "right" }[]; height?: number; name?: string; stacked?: boolean }) {
  return (
    <ChartFrame name={name} height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <Defs />
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey={xKey} tick={{ fill: C.muted, fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={28} />
        <YAxis yAxisId="left" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={46} />
        {series.some((s) => s.axis === "right") && <YAxis yAxisId="right" orientation="right" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={40} />}
        <Tooltip content={<TT />} />
        {series.map((s) => s.type === "bar" ? <Bar key={s.key} yAxisId={s.axis || "left"} dataKey={s.key} name={s.name} fill={s.color || C.amber} radius={[8, 8, 8, 8]} stackId={stacked ? "s" : undefined} isAnimationActive={false} />
          : s.type === "line" ? <Line key={s.key} yAxisId={s.axis || "left"} dataKey={s.key} name={s.name} stroke={s.color || C.blue} strokeWidth={2} dot={false} isAnimationActive={false} style={{ filter: "url(#glow)" }} />
            : <Area key={s.key} yAxisId={s.axis || "left"} dataKey={s.key} name={s.name} stroke={s.color || C.amber} strokeWidth={2} fill={s.color === C.blue ? "url(#gBlue)" : "url(#gAmber)"} isAnimationActive={false} />)}
        <Legend wrapperStyle={{ fontSize: 11 }} iconSize={10} />
      </ComposedChart>
    </ChartFrame>
  );
}

export function Waterfall({ steps, height = 260, name = "waterfall", unit = "" }: { steps: { step: string; value: number; kind: "total" | "delta" }[]; height?: number; name?: string; unit?: string }) {
  let run = 0;
  const data = steps.map((s) => {
    if (s.kind === "total") { run = s.value; return { step: s.step, _base: 0, span: s.value, kind: "total", value: s.value }; }
    const base = s.value >= 0 ? run : run + s.value; run += s.value;
    return { step: s.step, _base: base, span: Math.abs(s.value), kind: s.value >= 0 ? "up" : "down", value: s.value };
  });
  return (
    <ChartFrame name={name} height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <Defs />
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="step" tick={{ fill: C.muted, fontSize: 10 }} axisLine={false} tickLine={false} interval={0} height={44} tickFormatter={(v) => (v.length > 18 ? v.slice(0, 17) + "…" : v)} />
        <YAxis tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={46} />
        <Tooltip content={<TT fmtv={(v: Any) => `${fmt.n(v, 1)} ${unit}`} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="_base" stackId="w" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="span" name="value" stackId="w" radius={[6, 6, 6, 6]} isAnimationActive={false}>{data.map((d, i) => <Cell key={i} fill={d.kind === "total" ? C.amber : d.kind === "up" ? C.green : C.red} fillOpacity={d.kind === "total" ? 0.9 : 0.75} />)}</Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function Matrix({ points, xLabel, yLabel, quadrants, xMid, height = 300, name = "matrix", onPoint, xFmt }: { points: Any[]; xLabel: string; yLabel: string; quadrants?: [string, string, string, string]; xMid?: number; height?: number; name?: string; onPoint?: (p: Any) => void; xFmt?: (v: Any) => string }) {
  const xs = points.map((p) => p.x);
  const mid = xMid ?? (xs.length ? (Math.max(...xs) + Math.min(...xs)) / 2 : 0);
  return (
    <ChartFrame name={name} height={height}>
      <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
        <Defs />
        <CartesianGrid stroke={C.grid} />
        <XAxis dataKey="x" name={xLabel} type="number" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={xFmt} label={{ value: xLabel, position: "insideBottom", fill: C.muted, fontSize: 11, dy: 8 }} />
        <YAxis dataKey="y" name={yLabel} type="number" domain={[0, 1]} tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={40} label={{ value: yLabel, angle: -90, position: "insideLeft", fill: C.muted, fontSize: 11 }} />
        <ZAxis dataKey="z" range={[60, 320]} />
        {quadrants && <>
          <ReferenceLine x={mid} stroke={C.grid} strokeDasharray="4 4" /><ReferenceLine y={0.5} stroke={C.grid} strokeDasharray="4 4" />
          <ReferenceArea x1={mid} y1={0.5} y2={1} fill={C.green} fillOpacity={0.05} label={{ value: quadrants[0], fill: C.muted, fontSize: 11, position: "insideTopRight" }} />
          <ReferenceArea x2={mid} y1={0.5} y2={1} fill={C.blue} fillOpacity={0.05} label={{ value: quadrants[1], fill: C.muted, fontSize: 11, position: "insideTopLeft" }} />
          <ReferenceArea x2={mid} y1={0} y2={0.5} fill={C.ink} fillOpacity={0.02} label={{ value: quadrants[2], fill: C.muted, fontSize: 11, position: "insideBottomLeft" }} />
          <ReferenceArea x1={mid} y1={0} y2={0.5} fill={C.amber} fillOpacity={0.04} label={{ value: quadrants[3], fill: C.muted, fontSize: 11, position: "insideBottomRight" }} />
        </>}
        <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active, payload }: Any) => active && payload?.length ? <div className="glass-strong p-3 text-[12px]" style={{ borderRadius: 12 }}><div className="font-medium">{payload[0].payload.label || payload[0].payload.well_id}</div><div className="subtle">{xLabel}: {xFmt ? xFmt(payload[0].payload.x) : fmt.n(payload[0].payload.x, 1)}</div><div className="subtle">{yLabel}: {fmt.n(payload[0].payload.y, 2)}</div>{payload[0].payload.sub && <div className="faint">{payload[0].payload.sub}</div>}</div> : null} />
        <Scatter data={points} onClick={(p: Any) => onPoint?.(p)} isAnimationActive={false} style={{ cursor: onPoint ? "pointer" : "default" }}>{points.map((p, i) => <Cell key={i} fill={p.color || (p.module === "ghost" ? C.blue : C.amber)} fillOpacity={0.85} stroke="rgba(255,255,255,0.4)" />)}</Scatter>
      </ScatterChart>
    </ChartFrame>
  );
}

export function Bars({ data, xKey, series, height = 240, name = "bars", horizontal, fmtv, colorBy }: { data: Any[]; xKey: string; series: { key: string; name: string; color?: string }[]; height?: number; name?: string; horizontal?: boolean; fmtv?: (v: Any, k?: string) => string; colorBy?: (row: Any) => string }) {
  return (
    <ChartFrame name={name} height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, left: horizontal ? 10 : 0, bottom: 0 }} barGap={3}>
        <Defs />
        <CartesianGrid vertical={!!horizontal} horizontal={!horizontal} stroke={C.grid} />
        {horizontal ? <><XAxis type="number" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => (fmtv ? fmtv(v) : String(v))} /><YAxis type="category" dataKey={xKey} tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={120} /></>
          : <><XAxis dataKey={xKey} tick={{ fill: C.muted, fontSize: 10 }} axisLine={false} tickLine={false} interval={0} tickFormatter={(v) => (String(v).length > 14 ? String(v).slice(0, 13) + "…" : String(v).replace(/_/g, " "))} /><YAxis tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v) => (fmtv ? fmtv(v) : String(v))} /></>}
        <Tooltip content={<TT fmtv={fmtv} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} iconSize={10} />}
        {series.map((s, si) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color || [C.amber, C.blue, C.green, C.red][si % 4]} radius={horizontal ? [0, 8, 8, 0] : [8, 8, 8, 8]} isAnimationActive={false}>{colorBy && data.map((d, i) => <Cell key={i} fill={colorBy(d)} />)}</Bar>)}
      </BarChart>
    </ChartFrame>
  );
}

export function Tornado({ rows, height = 220, name = "tornado" }: { rows: { factor: string; low: number; high: number; base: number }[]; height?: number; name?: string }) {
  const data = rows.map((r) => ({ factor: r.factor, low: Math.min(r.low, r.high) - r.base, high: Math.max(r.low, r.high) - r.base, base: r.base, lo: r.low, hi: r.high }));
  return (
    <ChartFrame name={name} height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, left: 10, bottom: 0 }} stackOffset="sign">
        <Defs />
        <CartesianGrid horizontal={false} stroke={C.grid} />
        <XAxis type="number" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => fmt.money(v)} />
        <YAxis type="category" dataKey="factor" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={130} />
        <ReferenceLine x={0} stroke={C.ink} strokeOpacity={0.5} />
        <Tooltip content={({ active, payload }: Any) => active && payload?.length ? <div className="glass-strong p-3 text-[12px]" style={{ borderRadius: 12 }}><div className="font-medium">{payload[0].payload.factor}</div><div className="subtle">{fmt.money(payload[0].payload.lo)} → {fmt.money(payload[0].payload.hi)}</div><div className="faint">base {fmt.money(payload[0].payload.base)}</div></div> : null} />
        <Bar dataKey="low" stackId="t" fill={C.red} fillOpacity={0.7} radius={[8, 0, 0, 8]} isAnimationActive={false} name="low" />
        <Bar dataKey="high" stackId="t" fill={C.green} fillOpacity={0.7} radius={[0, 8, 8, 0]} isAnimationActive={false} name="high" />
      </BarChart>
    </ChartFrame>
  );
}

export function Histogram({ edges, counts, height = 220, name = "hist", zeroIndex, xFmt }: { edges: number[]; counts: number[]; height?: number; name?: string; zeroIndex?: number; xFmt?: (a: number, b: number) => string }) {
  const data = counts.map((c, i) => ({ bin: xFmt ? xFmt(edges[i], edges[i + 1]) : `${edges[i]}…${edges[i + 1]}`, count: c, neg: edges[i + 1] <= 0 }));
  return <Bars data={data} xKey="bin" series={[{ key: "count", name: "count" }]} height={height} name={name} colorBy={(d) => (d.neg ? C.red : C.amber)} fmtv={(v) => fmt.n(v)} />;
}

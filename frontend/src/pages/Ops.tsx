import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Bars, C } from "../charts";
import { DataTable } from "../components/DataTable";
import { useApp } from "../components/Shell";
import { Badge, Card, Drawer, ErrorBox, Icon, Kpi, LabeledValue, Progress, Skeleton, Tabs, useFetch, useToast } from "../components/ui";
import { Any, api, download, fmt, toCSV } from "../lib/api";
import { useT } from "../lib/i18n";

// ------------------------------------------------------------------ ARCHIVE
export function Archive({ ask }: { ask?: boolean }) {
  const { t } = useT();
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const { data, error, loading, reload } = useFetch<Any>("/api/archive/documents");
  const [idx, setIdx] = useState(0);
  const [doc, setDoc] = useState<Any>(null);
  const [edits, setEdits] = useState<Record<string, Any>>({});
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Any>(null);
  const docs: Any[] = data?.documents || [];
  useEffect(() => { const want = sp.get("doc"); if (want && docs.length) { const i = docs.findIndex((d) => d.document_id === want); if (i >= 0) setIdx(i); } }, [data]);
  useEffect(() => { if (docs[idx]) api.get(`/api/archive/documents/${docs[idx].document_id}`).then(setDoc); setEdits({}); setEditing(false); }, [idx, data]);
  const review = async (decision: string) => { if (!doc) return; setBusy(true); try { await api.post(`/api/archive/documents/${doc.document.document_id}/review`, { decision, edits: decision === "edit" ? edits : undefined }); toast(`${decision} ✓ ${doc.document.file_name}`); setEditing(false); reload(); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  useEffect(() => { const h = (e: KeyboardEvent) => { if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return; if (e.key === "j") setIdx((i) => Math.min(docs.length - 1, i + 1)); if (e.key === "k") setIdx((i) => Math.max(0, i - 1)); if (e.key === "a") review("approve"); if (e.key === "r") review("reject"); if (e.key === "u") review("unreadable"); if (e.key === "e") setEditing(true); }; document.addEventListener("keydown", h); return () => document.removeEventListener("keydown", h); /* eslint-disable-next-line */ }, [doc, docs.length]);
  const upload = async (file: File | null) => { if (!file) return; setBusy(true); try { const r = await api.upload("/api/archive/upload", file); toast(`${file.name} → ${r.extraction.source_language}, confidence ${fmt.pct(r.extraction.llm_confidence)}`); reload(); setSp({ doc: r.document.document_id }); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  const search = async () => { if (!q.trim()) return; setHits(await api.get(`/api/archive/search?q=${encodeURIComponent(q)}`)); };
  const rerun = async () => { if (!doc) return; setBusy(true); try { await api.post(`/api/archive/documents/${doc.document.document_id}/extract`); toast("Re-extracted"); reload(); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const st = data.stats;
  const ex = doc?.extraction;
  const confColor = (c: number, v: Any) => (v === null || v === undefined ? "red" : c >= 0.85 ? "green" : c >= 0.6 ? "amber" : "red");
  const pageText = (doc?.pages || []).join("\n\n");
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Kpi label={t("processed")} value={st.documents_processed} small sub={`ru ${st.languages.ru} · az ${st.languages.az} · en ${st.languages.en}`} />
        <Kpi label={t("fields_extracted")} value={st.fields_extracted} small />
        <Kpi label={t("auto")} value={st.auto_approve_candidates} small sub={`≥ ${fmt.pct(0.9)} overall`} />
        <Kpi label={t("human")} value={st.human_reviewed} small />
        <Kpi label={t("low_conf")} value={st.low_confidence_fields} small />
        <Kpi label={t("accuracy")} value={st.accuracy_on_validated_sample === null ? "—" : fmt.pct(st.accuracy_on_validated_sample)} small sub={`${st.validated_documents} validated · provider ${st.provider} · OCR ${st.ocr_available ? st.ocr_languages.join("+") : "none"}`} />
      </div>
      <Tabs tabs={[{ key: "queue", label: t("queue") }, { key: "ask", label: t("ask_archive") }]} value={ask ? "ask" : "queue"} onChange={(k) => setSp(k === "ask" ? { tab: "ask" } : {})} />
      {(ask || sp.get("tab") === "ask") ? (
        <Card title={t("ask_archive")} subtitle={t("x_retrieval")}>
          <div className="flex gap-2"><input className="flex-1" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder={t("ask_placeholder")} /><button className="btn primary" onClick={search}>{t("search")}</button></div>
          <div className="flex flex-wrap gap-1 mt-2">{["pump replacement water cut above 80", "scale", "why was SYN-104 shut in", "water shutoff"].map((s) => <button key={s} className="chip" style={{ fontSize: 11 }} onClick={() => { setQ(s); api.get(`/api/archive/search?q=${encodeURIComponent(s)}`).then(setHits); }}>{s}</button>)}</div>
          {hits && <div className="mt-3 space-y-2 fade-in"><div className="faint text-[12px]">{hits.note}</div>{hits.hits.map((h: Any) => <button key={h.document_id} className="w-full text-left glass-inner p-3 text-[12px] hover:bg-white/10" onClick={() => setSp({ doc: h.document_id })}><div className="flex justify-between"><span className="font-medium">{h.file_name}</span><span className="flex gap-1"><Badge label={h.language} small /><Badge label={h.review_status} small /></span></div><div className="subtle">{h.well_id} · {h.date} · {h.intervention_type}</div>{h.snippets.map((s: string, i: number) => <div key={i} className="faint">…{s}…</div>)}</button>)}</div>}
        </Card>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: "minmax(220px, 280px) minmax(0, 1fr)" }}>
          <Card title={t("queue")} action={<label className="btn sm cursor-pointer"><Icon name="upload" size={13} />{t("upload")}<input type="file" className="hidden" accept=".pdf,.txt,.png,.jpg,.jpeg,.tif,.tiff,.docx" onChange={(e) => upload(e.target.files?.[0] || null)} disabled={busy} /></label>}>
            <div className="space-y-1 max-h-[70vh] overflow-auto">{docs.map((d, i) => <button key={d.document_id} className={`w-full text-left glass-inner px-3 py-2 text-[12px] hover:bg-white/10 ${i === idx ? "outline outline-2 outline-amber" : ""}`} onClick={() => setIdx(i)}><div className="flex justify-between gap-1"><span className="font-medium truncate">{d.file_name}</span><Badge label={d.review_status} small /></div><div className="faint">{d.language} · {d.well_id || "—"} · {d.file_type}</div></button>)}</div>
            <div className="faint text-[11px] mt-3">{t("shortcuts")}</div>
          </Card>
          <div className="grid gap-3">
            {doc && ex && (
              <>
                <Card title={<span className="flex items-center gap-2">{doc.document.file_name} <Badge label={doc.document.review_status} /><Badge label={ex.source_language} small /><Badge label={`${t("confidence")} ${fmt.pct(ex.llm_confidence)}`} color={ex.llm_confidence >= 0.9 ? "green" : ex.llm_confidence >= 0.5 ? "amber" : "red"} small /></span>} action={<div className="flex gap-1 flex-wrap"><button className="btn sm ghost" onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0}>{t("previous")}</button><button className="btn sm ghost" onClick={() => setIdx(Math.min(docs.length - 1, idx + 1))} disabled={idx >= docs.length - 1}>{t("next")}</button><a className="btn sm" href={`/api/archive/file/${doc.document.document_id}`} target="_blank" rel="noreferrer"><Icon name="download" size={13} />file</a><button className="btn sm" onClick={rerun} disabled={busy}><Icon name="reset" size={13} />extract</button></div>}>
                  <div className="text-[12px] faint">{doc.document.note || ""} {doc.document.text_source === "ocr" && `OCR confidence ${fmt.pct(doc.document.ocr_confidence)}.`} provider: {ex.provider}. {t("ar_note")}</div>
                  <div className="flex gap-2 mt-3 flex-wrap"><button className="btn primary" onClick={() => review("approve")} disabled={busy}>{t("approve")} (A)</button><button className="btn" onClick={() => setEditing(!editing)}>{t("edit")} (E)</button><button className="btn danger" onClick={() => review("reject")} disabled={busy}>{t("reject")} (R)</button><button className="btn" onClick={() => review("unreadable")} disabled={busy}>{t("unreadable")} (U)</button>{editing && <button className="btn primary" onClick={() => review("edit")} disabled={busy || !Object.keys(edits).length}>{t("save")} {Object.keys(edits).length} {t("edit").toLowerCase()}s</button>}</div>
                </Card>
                <div className="grid md:grid-cols-2 gap-3">
                  <Card title={t("preview")}><pre className="text-[12px] whitespace-pre-wrap max-h-[62vh] overflow-auto subtle" style={{ fontFamily: "inherit" }}>{pageText || "(no readable text — routed to manual review)"}</pre></Card>
                  <Card title={t("extracted")}>
                    <div className="max-h-[62vh] overflow-auto space-y-1">
                      {Object.entries(ex.fields).map(([k, v]: Any) => (
                        <div key={k} className="flex items-center gap-2 text-[12px] py-1" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                          <span className="w-[150px] faint shrink-0">{k.replace(/_/g, " ")}</span>
                          {editing ? <input className="flex-1" style={{ padding: "3px 8px" }} value={edits[k] ?? (v.value ?? "")} onChange={(e) => setEdits({ ...edits, [k]: e.target.value })} /> : <span className="flex-1 truncate" title={v.snippet || ""}>{v.value === null || v.value === undefined ? <span className="faint">—</span> : String(v.value)}</span>}
                          <span className={`badge ${confColor(v.confidence, v.value)}`} style={{ fontSize: 10 }} title={v.snippet ? `p.${v.page}: …${v.snippet}…` : "no source span"}>{v.value === null ? "missing" : fmt.pct(v.confidence)}</span>
                          {v.snippet && <button className="btn ghost" style={{ padding: 2 }} title={`Source p.${v.page}: …${v.snippet}…`} onClick={() => toast(`p.${v.page}: …${v.snippet}…`)}><Icon name="info" size={12} /></button>}
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              </>
            )}
            {!doc && <Card><div className="subtle">{t("x_upload_report")}</div></Card>}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ DATA HUB
export function DataHub() {
  const { t } = useT();
  const toast = useToast();
  const nav = useNavigate();
  const { reloadMeta } = useApp();
  const { data, error, loading, reload } = useFetch<Any>("/api/data/connectors");
  const [panel, setPanel] = useState<Any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const act = async (c: Any, action: string) => {
    setBusy(c.id + action);
    setSteps([]);
    try {
      const r = await api.post(`/api/data/connectors/${c.id}/${action}`, {});
      // Schema/sample open in a drawer: the old inline panel rendered below 15 cards,
      // far off-screen, so the button looked like it did nothing.
      if (action === "schema" || action === "sample") {
        setPanel({ title: `${c.name} · ${action}`, body: r });
      } else if (r.job_id) {
        // Long imports run as tracked jobs so progress is visible instead of a frozen button.
        const done = await api.job(r.job_id, setSteps);
        toast(done.message || "done", done.ok ? "ok" : "err");
        reload(); reloadMeta();
      } else {
        toast(r.message || "done", r.ok ? "ok" : "err");
        if (r.redirect) nav(r.redirect);
        reload(); reloadMeta();
      }
    } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(null); setSteps([]); }
  };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={400} />;
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-3 flex-wrap"><h1 style={{ fontSize: 28 }}>{t("dh_title")}</h1><span className="subtle text-[13px]">{t("x_pub_ds_note")}</span><span className="flex-1" /><a className="btn sm" href="/api/data/sample-schema.csv"><Icon name="download" size={13} />{t("sample_schema")}</a><button className="btn sm primary" onClick={() => nav("/data/imports")}>{t("import_wizard")}</button></div>
      {busy && <Progress steps={steps.length ? steps : [t("loading")]} label={busy} />}
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
        {data.connectors.map((c: Any) => (
          <Card key={c.id} title={<span className="flex items-center gap-2">{c.name} {c.active && <Badge label="active" color="amber" small />}</span>} subtitle={<span>{c.source} · {c.jurisdiction}</span>}>
            <div className="flex items-center gap-2 mb-2"><Badge label={c.connected ? t("connected") : t("not_connected")} color={c.connected ? "green" : "grey"} /><span className="faint text-[11px]">{t("last_refresh")}: {c.last_refresh ? fmt.date(c.last_refresh) : "—"}</span></div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
              <LabeledValue label={t("grain")} value={c.grain} /><LabeledValue label={t("rows")} value={c.rows ? fmt.n(c.rows) : "—"} /><LabeledValue label={t("date")} value={c.date_range ? c.date_range.join(" → ") : "—"} /><LabeledValue label={t("dq")} value={c.quality || "—"} />
              <LabeledValue label={`${t("oil")} / ${t("water")} / gas`} value={`${String(c.oil)} / ${String(c.water)} / ${String(c.gas)}`} /><LabeledValue label={t("status")} value={c.well_status} /><LabeledValue label={t("interventions_avail")} value={String(c.interventions)} /><LabeledValue label={t("licence")} value={c.license} />
            </div>
            {c.note && <div className="faint text-[11px] mt-2">{c.note}</div>}
            <div className="flex flex-wrap gap-1 mt-3">
              {!c.connected && <button className="btn sm primary" onClick={() => act(c, "connect")} disabled={!!busy}>{busy === c.id + "connect" ? t("loading") : t("connect")}</button>}
              {c.connected && <button className="btn sm" onClick={() => act(c, "refresh")} disabled={!!busy}>{t("refresh")}</button>}
              <button className="btn sm" onClick={() => act(c, "schema")}>{t("view_schema")}</button>
              {c.connected && <button className="btn sm" onClick={() => act(c, "sample")}>{t("view_sample")}</button>}
              {c.connected && c.id !== "synthetic" && <button className="btn sm danger" onClick={() => act(c, "disconnect")}>{t("disconnect")}</button>}
              {c.url && <a className="btn sm ghost" href={c.url} target="_blank" rel="noreferrer">source ↗</a>}
            </div>
          </Card>
        ))}
      </div>
      <Drawer open={!!panel} onClose={() => setPanel(null)} title={panel?.title} width={720}>
        <pre className="text-[11px] whitespace-pre-wrap subtle">{JSON.stringify(panel?.body, null, 1)}</pre>
      </Drawer>
    </div>
  );
}

export function Imports() {
  const { t } = useT();
  const toast = useToast();
  const { reloadMeta } = useApp();
  const [mode, setMode] = useState<"production" | "interventions">("production");
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [prev, setPrev] = useState<Any>(null);
  const [map, setMap] = useState<Record<string, string>>({});
  const [units, setUnits] = useState<Record<string, string>>({ oil: "m3", water: "m3", gas: "e3m3" });
  const [val, setVal] = useState<Any>(null);
  const [name, setName] = useState("import");
  const [res, setRes] = useState<Any>(null);
  const [busy, setBusy] = useState(false);
  const steps = [t("step_upload"), t("step_preview"), t("step_map"), t("step_validate"), t("step_units"), t("step_confirm"), t("step_ingest")];
  const canon = mode === "production" ? ["well_id", "month", "oil", "water", "gas", "hours", "status", "field"] : ["well_id", "date", "type", "cost", "duration", "notes", "outcome"];
  const required = mode === "production" ? ["well_id", "month", "oil"] : ["well_id", "date", "type"];
  const preview = async (f: File) => { setBusy(true); try { const p = await api.upload("/api/data/import/preview", f); setPrev(p); setMap(p.suggested_mapping || {}); setStep(1); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  const validate = async () => { if (!file) return; setBusy(true); try { if (mode === "production") { const v = await api.upload("/api/data/import/validate", file, { mapping: JSON.stringify(map), units: JSON.stringify(units) }); setVal(v); } else { setVal({ ok: required.every((r) => map[r]), errors: required.filter((r) => !map[r]).map((r) => `Required column not mapped: ${r}`), warnings: [] }); } setStep(3); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  const ingest = async () => { if (!file) return; setBusy(true); try { const r = mode === "production" ? await api.upload("/api/data/import/ingest", file, { mapping: JSON.stringify(map), units: JSON.stringify(units), dataset_name: name }) : await api.upload("/api/data/import/interventions", file, { mapping: JSON.stringify(map), dataset_name: "synthetic" }); setRes(r); setStep(6); reloadMeta(); toast(r.ok ? "Imported ✓" : "Import failed", r.ok ? "ok" : "err"); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  const reset = () => { setStep(0); setFile(null); setPrev(null); setMap({}); setVal(null); setRes(null); };
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-3 flex-wrap"><h1 style={{ fontSize: 28 }}>{t("nav_imports")}</h1><Tabs tabs={[{ key: "production", label: t("import_wizard") }, { key: "interventions", label: t("import_interventions") }]} value={mode} onChange={(k) => { setMode(k as Any); reset(); }} /><span className="flex-1" /><a className="btn sm" href="/api/data/sample-schema.csv"><Icon name="download" size={13} />{t("sample_schema")}</a></div>
      <div className="flex gap-1 flex-wrap">{steps.map((s, i) => <span key={s} className={`chip ${i === step ? "amber" : i < step ? "" : "faint"}`} style={{ fontSize: 12 }}>{i + 1}. {s}</span>)}</div>
      <Card>
        {step === 0 && <div className="grid gap-3"><div className="subtle text-[13px]">{mode === "production" ? "Required columns: well identifier, month/date, oil. Optional: water, gas, hours, status, field." : "Required: well, date, intervention type. Optional: cost, duration, notes, outcome. If you only have reports, send them to Archive AI instead."}</div><label className="btn primary w-fit cursor-pointer"><Icon name="upload" size={14} />{t("step_upload")} (.csv / .xlsx)<input type="file" className="hidden" accept=".csv,.tsv,.xlsx" onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f) preview(f); }} /></label></div>}
        {step === 1 && prev && <div className="grid gap-3"><div className="subtle text-[13px]">{prev.rows} rows · {prev.columns.length} columns</div><div className="overflow-auto max-h-[300px]"><table className="core"><thead><tr>{prev.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead><tbody>{prev.sample.map((r: Any, i: number) => <tr key={i}>{prev.columns.map((c: string) => <td key={c}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody></table></div><div className="flex gap-2"><button className="btn ghost" onClick={reset}>{t("back")}</button><button className="btn primary" onClick={() => setStep(2)}>{t("next")}</button></div></div>}
        {step === 2 && prev && <div className="grid gap-3"><div className="grid md:grid-cols-2 gap-2 text-[12px]">{canon.map((c) => <label key={c} className="flex items-center gap-2"><span className="w-[110px]">{c}{required.includes(c) && <span className="text-amber"> *</span>}</span><select value={map[c] || ""} onChange={(e) => setMap({ ...map, [c]: e.target.value })} className="flex-1"><option value="">—</option>{prev.columns.map((col: string) => <option key={col} value={col}>{col}</option>)}</select></label>)}</div><div className="flex gap-2"><button className="btn ghost" onClick={() => setStep(1)}>{t("back")}</button><button className="btn primary" onClick={validate} disabled={busy || !required.every((r) => map[r])}>{t("step_validate")}</button></div></div>}
        {step === 3 && val && <div className="grid gap-3">{val.errors.map((e: string, i: number) => <div key={i} className="glass-inner p-3 text-[#FFB3A8] text-[13px]">{e}</div>)}{val.warnings.map((w: string, i: number) => <div key={i} className="glass-inner p-3 text-amber text-[13px]">{w}</div>)}{val.ok && <div className="glass-inner p-3 text-[#9FE6BC] text-[13px]">Schema valid{val.wells ? ` · ${val.wells} wells · ${val.months} months` : ""}</div>}<div className="flex gap-2"><button className="btn ghost" onClick={() => setStep(2)}>{t("back")}</button><button className="btn primary" disabled={!val.ok} onClick={() => setStep(mode === "production" ? 4 : 5)}>{t("next")}</button></div></div>}
        {step === 4 && <div className="grid gap-3"><div className="grid grid-cols-3 gap-2 text-[12px]">{["oil", "water", "gas"].map((u) => <label key={u} className="flex flex-col gap-1"><span className="faint">{u} unit</span><select value={units[u]} onChange={(e) => setUnits({ ...units, [u]: e.target.value })}>{u === "gas" ? <><option value="e3m3">e3m³</option><option value="mcf">mcf</option></> : <><option value="m3">m³</option><option value="bbl">bbl</option></>}</select></label>)}</div><div className="faint text-[12px]">{t("x_src_units")}</div><div className="flex gap-2"><button className="btn ghost" onClick={() => setStep(3)}>{t("back")}</button><button className="btn primary" onClick={() => setStep(5)}>{t("next")}</button></div></div>}
        {step === 5 && <div className="grid gap-3 text-[13px]"><div>File <b>{file?.name}</b> · mapping {JSON.stringify(map)} {mode === "production" && <>· units {JSON.stringify(units)}</>}</div>{mode === "production" && <label className="flex items-center gap-2">dataset name <input value={name} onChange={(e) => setName(e.target.value)} /></label>}<div className="flex gap-2"><button className="btn ghost" onClick={() => setStep(mode === "production" ? 4 : 3)}>{t("back")}</button><button className="btn primary" onClick={ingest} disabled={busy}>{busy ? t("loading") : t("step_ingest")}</button></div></div>}
        {step === 6 && res && <div className="grid gap-3 text-[13px]">{res.ok ? <div className="glass-inner p-3 text-[#9FE6BC]">Imported{res.dataset ? ` into data set "${res.dataset}"` : ""}: {res.rows ?? res.imported} rows{res.wells ? `, ${res.wells} wells, ${res.months} months` : ""}. {mode === "production" ? "Activate it in the Data hub and rebuild the evidence base from Settings." : "Rebuild the evidence base from Settings to analyse the new records."}</div> : <div className="glass-inner p-3 text-[#FFB3A8]">{(res.errors || []).join("; ")}</div>}<button className="btn w-fit" onClick={reset}>{t("reset")}</button></div>}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ DECISIONS
export function DecisionLog() {
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>("/api/decisions");
  const mve = useFetch<Any>("/api/decisions/model-vs-engineer");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  const m = mve.data;
  return (
    <div className="grid gap-3">
      {m && <div className="grid grid-cols-2 md:grid-cols-5 gap-3"><Kpi label={t("dl_title")} value={m.decisions} small /><Kpi label={t("acceptance")} value={fmt.pct(m.acceptance_rate)} small /><Kpi label={t("override")} value={fmt.pct(m.override_rate)} small sub="overrides are learning signals, not errors" /><Kpi label={t("defer")} value={m.deferred} small /><Kpi label={t("outcome")} value={<span className="text-[13px]">{m.outcomes.note}</span>} small /></div>}
      {m && Object.keys(m.by_reason).length > 0 && <Card title={t("mve")} subtitle={m.note}><Bars data={Object.entries(m.by_reason).map(([r, n]) => ({ r, n }))} xKey="r" series={[{ key: "n", name: "overrides" }]} height={180} name="override_reasons" /></Card>}
      <Card title={t("dl_title")} subtitle={t("x_audit_rec")} action={<a className="btn sm" href="/api/decisions/export.csv"><Icon name="download" size={13} />{t("export_csv")}</a>}>
        {!data.decisions.length ? <div className="subtle text-[13px]">{t("x_no_dec_yet")}</div> :
          <DataTable id="decisions" rows={data.decisions} rowKey="decision_id" columns={[{ key: "timestamp", label: t("timestamp"), render: (r: Any) => fmt.date(r.timestamp) }, { key: "user", label: t("user") }, { key: "well_id", label: t("well") }, { key: "recommendation_id", label: t("recommendation") }, { key: "action", label: t("action"), render: (r: Any) => String(r.action).replace(/_/g, " ") }, { key: "model_version", label: t("model_version") }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }, { key: "decision", label: t("action"), render: (r: Any) => <Badge label={r.decision} /> }, { key: "reason", label: t("reason") }, { key: "notes", label: t("notes") }, { key: "inputs", label: "inputs", render: (r: Any) => <span className="faint">{JSON.stringify(r.inputs)}</span>, hidden: true }, { key: "subsequent_outcome", label: t("outcome"), render: (r: Any) => r.subsequent_outcome || <span className="faint">pending</span> }]} onRow={(r) => nav(`/wells/${r.well_id}`)} defaultSort={{ key: "timestamp", dir: "desc" }} />}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ SETTINGS
export function Settings() {
  const { t } = useT();
  const toast = useToast();
  const { meta, reloadMeta } = useApp();
  const { data, error, loading, reload, setData } = useFetch<Any>("/api/settings");
  const [dirty, setDirty] = useState(false);
  const [steps, setSteps] = useState<string[] | null>(null);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={400} />;
  const upd = (path: string[], v: Any) => { const d = JSON.parse(JSON.stringify(data)); let n = d; for (const k of path.slice(0, -1)) n = n[k]; n[path[path.length - 1]] = v; setData(d); setDirty(true); };
  const save = async () => { try { const r = await api.put("/api/settings", data); setData(r.settings); setDirty(false); toast(t("saved")); reloadMeta(); } catch (e: Any) { toast(e.message, "err"); } };
  const resetAll = async () => { const r = await api.post("/api/settings/reset"); setData(r.settings); setDirty(false); toast(t("reset_defaults")); reloadMeta(); };
  const rebuild = async (full: boolean) => { setSteps(["Queued"]); try { const j = await api.post(`/api/evidence/rebuild?full=${full}`); await api.job(j.job_id, setSteps); setSteps(null); toast(t("rebuild") + " ✓"); reloadMeta(); } catch (e: Any) { setSteps(null); toast(e.message, "err"); } };
  const Field = ({ path, label, step = 1, unit }: { path: string[]; label: string; step?: number; unit?: string }) => { let v: Any = data; for (const k of path) v = v?.[k]; const isP = v && typeof v === "object" && "value" in v; const val = isP ? v.value : v; return <label className="flex items-center gap-2 text-[12px] py-1"><span className="flex-1">{label}</span>{val === null ? <Badge label={v.source} small /> : typeof val === "boolean" ? <input type="checkbox" checked={val} onChange={(e) => upd(isP ? [...path, "value"] : path, e.target.checked)} /> : typeof val === "number" ? <input type="number" step={step} className="w-[110px]" style={{ padding: "4px 8px" }} value={val} onChange={(e) => upd(isP ? [...path, "value"] : path, Number(e.target.value))} /> : <input className="w-[140px]" style={{ padding: "4px 8px" }} value={val} onChange={(e) => upd(isP ? [...path, "value"] : path, e.target.value)} />}<span className="faint w-[80px]">{unit || (isP ? v.unit : "")}</span>{isP && <Badge label={v.source} small />}</label>; };
  const e = data.economics;
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap"><h1 style={{ fontSize: 28 }}>{t("st_title")}</h1><span className="flex-1" /><button className="btn primary" onClick={save} disabled={!dirty}>{t("save")}</button><button className="btn" onClick={resetAll}>{t("reset_defaults")}</button><button className="btn" onClick={() => rebuild(false)} disabled={!!steps}>{t("rebuild")} (economics)</button><button className="btn" onClick={() => rebuild(true)} disabled={!!steps}>{t("rebuild")} (full)</button></div>
      {meta?.evidence_stale && <div className="glass-inner px-4 py-2 text-[12px] text-amber">{t("stale")}</div>}
      {steps && <Progress steps={steps} label={t("rebuild")} />}
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
        <Card title={t("st_units")}><label className="flex items-center gap-2 text-[12px] py-1"><span className="flex-1">volume</span><select value={data.units.volume} onChange={(ev) => upd(["units", "volume"], ev.target.value)}><option value="bbl">bbl</option><option value="m3">m³</option></select></label><Field path={["units", "currency"]} label="currency" /></Card>
        <Card title={t("st_econ")} subtitle={t("x_pub_assump")}><Field path={["economics", "oil_price"]} label="oil price" /><Field path={["economics", "royalty_rate"]} label="royalty rate" step={0.01} /><Field path={["economics", "lifting_cost"]} label="lifting cost" step={0.5} /><Field path={["economics", "discount_rate"]} label="discount rate" step={0.01} /><Field path={["economics", "horizon_months"]} label="planning horizon" /><div className="faint text-[11px] mt-2">netback = price × (1 − royalty) − lifting</div></Card>
        <Card title={`${t("water")} — $/bbl`}>{Object.keys(e.water).map((k) => <Field key={k} path={["economics", "water", k]} label={k.replace(/_/g, " ")} step={0.05} />)}</Card>
        <Card title={`${t("cost")} — ${t("nav_interventions").toLowerCase()}`}>{Object.keys(e.intervention_costs).map((k) => <Field key={k} path={["economics", "intervention_costs", k]} label={k.replace(/_/g, " ")} step={1000} />)}</Card>
        <Card title={t("st_causal")} subtitle="changes require a full rebuild">{["default_model", "pre_window", "post_window", "max_donors", "min_donors", "bootstrap_samples", "placebo_wells", "same_field_only", "seed"].map((k) => <Field key={k} path={["causal", k]} label={k.replace(/_/g, " ")} />)}</Card>
        <Card title={t("st_restart")} subtitle={t("x_nm_months")}><Field path={["restart", "min_inactive_months"]} label="min inactive months (N)" /><Field path={["restart", "min_producing_months"]} label="min producing months (M)" /><Field path={["restart", "zero_threshold_bpd"]} label="zero threshold" step={0.1} unit="bbl/d" /></Card>
        <Card title={t("st_conf")}><Field path={["confidence", "high"]} label="high ≥" step={0.05} /><Field path={["confidence", "moderate"]} label="moderate ≥" step={0.05} /><Field path={["confidence", "min_pre_r2"]} label="min pre-period R²" step={0.05} /></Card>
        <Card title={t("st_portfolio")}>{["budget", "crews", "rigs", "horizon_months", "max_concurrent", "min_npv", "risk_tolerance"].map((k) => <Field key={k} path={["portfolio", k]} label={k.replace(/_/g, " ")} step={k === "risk_tolerance" ? 0.05 : k === "budget" || k === "min_npv" ? 10000 : 1} />)}<label className="flex items-center gap-2 text-[12px] py-1"><span className="flex-1">objective</span><select value={data.portfolio.objective} onChange={(ev) => upd(["portfolio", "objective"], ev.target.value)}>{["npv", "oil", "cash", "water", "balanced"].map((o) => <option key={o} value={o}>{o}</option>)}</select></label></Card>
        <Card title={t("st_archive")}><label className="flex items-center gap-2 text-[12px] py-1"><span className="flex-1">{t("x_llm_provider")}</span><select value={data.archive.llm_provider} onChange={(ev) => upd(["archive", "llm_provider"], ev.target.value)}>{["mock", "anthropic", "openai", "local"].map((o) => <option key={o} value={o}>{o}</option>)}</select></label><Field path={["archive", "auto_approve_confidence"]} label="auto-approve confidence" step={0.05} /><Field path={["archive", "ocr_languages"]} label={t("x_ocr_langs")} /><div className="faint text-[11px] mt-2">{t("x_api_keys")}</div></Card>
        <Card title={t("st_data")}><Field path={["decisions", "require_reject_reason"]} label="require a reason to reject" /><div className="text-[12px] mt-2">{t("x_active_ds")} <b>{meta?.dataset}</b> ({meta?.data_mode})</div><div className="text-[12px] mt-1">Available: {(meta?.datasets || []).map((d: Any) => <button key={d.name} className="chip mr-1 mt-1" style={{ fontSize: 11 }} onClick={async () => { await api.post(`/api/data/activate/${d.name}`); reloadMeta(); toast(`${d.name} active — rebuild the evidence base`); }}>{d.name}</button>)}</div></Card>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ WHY CORE
export function WhyCore() {
  const { t } = useT();
  const rows = [["Historical records describe what was done.", "Measures what it actually changed."], ["Inactive wells are reviewed manually.", "Screens the entire field."], ["Water is discussed as a percentage.", "Converts it into economics."], ["Recommendations are ranked individually.", "Builds an executable portfolio under actual constraints."], ["Knowledge lives in documents and people.", "Creates searchable, evidence-linked institutional memory."]];
  return (
    <div className="grid gap-3">
      <div className="pt-6 pl-2"><div className="hero-title">{t("why_title")}</div><div className="subtle mt-3 max-w-[720px]">{t("x_core_stmt3")}</div><div className="faint mt-2">{t("x_from_hist")}</div></div>
      <div className="grid gap-2">{rows.map(([a, b], i) => <div key={i} className="grid md:grid-cols-2 gap-3"><div className="glass p-5"><div className="faint text-[12px] mb-1">{t("today")}</div><div className="text-[16px]">{a}</div></div><div className="glass p-5" style={{ borderColor: "rgba(242,182,50,0.4)" }}><div className="text-amber text-[12px] mb-1">{t("core_label")}</div><div className="text-[16px] font-medium">{b}</div></div></div>)}</div>
      <Card title={t("x_pred_vs_causal")}><div className="grid md:grid-cols-2 gap-3 text-[13px]"><div className="glass-inner p-4"><div className="faint">{t("x_prediction")}</div><div className="text-[16px]">"What is likely to happen?"</div><div className="subtle mt-1">{t("x_many_systems")}</div></div><div className="glass-inner p-4" style={{ borderColor: "rgba(242,182,50,0.4)" }}><div className="text-amber">{t("x_causal_decision")}</div><div className="text-[16px]">"What changes if we perform action X rather than doing nothing?"</div><div className="subtle mt-1">{t("x_core_both")}</div></div></div><div className="faint text-[12px] mt-3">{t("x_core_stmt1")}</div></Card>
    </div>
  );
}

# CORE button & navigation audit

Generated from `frontend/src`. 249 interactive controls found, 0 unwired.

Routes covered by the automated jsdom smoke test (`frontend/smoke.mjs`): /, /wells, /wells/:id (all tabs), /ghost, /idle, /network, /interventions, /interventions/compare, /interventions/:id, /water, /portfolio, /portfolio/scenarios, /archive, /archive/ask, /model-lab (all tabs), /quality, /data, /data/imports, /decisions, /runs, /settings, /why, /present.

| File | Line | Control | Label | Handler | Status |
|---|---|---|---|---|---|
| charts/index.tsx | 25 | button | exportSvgAsPng(ref.current, `${name}.png`)} title={t("export | onClick | WIRED |
| charts/index.tsx | 78 | button | setWin(w)}>{w === "FULL" ? "FULL" : `${w}M`} )} <label class | onClick | WIRED |
| charts/index.tsx | 80 | label | setDonors(e.target.checked)} />{t("show_donors")} <label cla | input | WIRED |
| charts/index.tsx | 80 | input | setDonors(e.target.checked)} />{t("show_donors")} <label cla | onChange | WIRED |
| charts/index.tsx | 81 | label | setNaive(e.target.checked)} />{t("show_naive")} <label class | input | WIRED |
| charts/index.tsx | 81 | input | setNaive(e.target.checked)} />{t("show_naive")} <label class | onChange | WIRED |
| charts/index.tsx | 82 | label | setBand(e.target.checked)} />{t("show_band")} )} < | input | WIRED |
| charts/index.tsx | 82 | input | setBand(e.target.checked)} />{t("show_band")} )} <ChartFrame | onChange | WIRED |
| components/DataContext.tsx | 67 | button | setOpen((o) => !o)} aria-expanded={open} aria-label={t("ctx_ | onClick | WIRED |
| components/DataContext.tsx | 97 | button | d.usable ? d.label : d.name | onClick | WIRED |
| components/DataMode.tsx | 56 | button | choose(value)} > {label} ))} {data?.ready === false && <B | onClick | WIRED |
| components/DataTable.tsx | 36 | input | { setQ(e.target.value); setPage(0); }} placeholder={t("searc | onChange | WIRED |
| components/DataTable.tsx | 41 | button | setShowCols(!showCols)}>{t("columns")} {showCols && <div cla | onClick | WIRED |
| components/DataTable.tsx | 42 | label | toggleCol(c.key)} />{c.label} )} } | input | WIRED |
| components/DataTable.tsx | 42 | input | toggleCol(c.key)} />{c.label} )} } {Object.keys(views).lengt | onChange | WIRED |
| components/DataTable.tsx | 44 | select | e.target.value && applyView(e.target.value)} defaultValue="" | onChange | WIRED |
| components/DataTable.tsx | 45 | button | {t("save_view")} {t("export_csv")}</button | onClick | WIRED |
| components/DataTable.tsx | 46 | button | {t("export_csv")} <div className="overflow-auto" style={{ ma | onClick | WIRED |
| components/DataTable.tsx | 61 | button | setPage(page - 1)}>{t("previous")} {page + 1} / {pages} <but | onClick | WIRED |
| components/DataTable.tsx | 61 | button | = pages - 1} onClick={() => setPage(page + 1)}>{t("next")} } |  | WIRED |
| components/Shell.tsx | 89 | NavLink | CORE | to | WIRED |
| components/Shell.tsx | 97 | NavLink | t(n.key as Any) | to | WIRED |
| components/Shell.tsx | 104 | NavLink | t( | to | WIRED |
| components/Shell.tsx | 105 | NavLink | t( | to | WIRED |
| components/Shell.tsx | 106 | NavLink | t( | to | WIRED |
| components/Shell.tsx | 113 | select | setField(e.target.value)} aria-label={t("field")} style={{ p | onChange | WIRED |
| components/Shell.tsx | 117 | input | setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && | onChange | WIRED |
| components/Shell.tsx | 121 | button | { nav(`/wells/${w.well_id}`); setResults(null); }}> {w.well_ | onClick | WIRED |
| components/Shell.tsx | 122 | button | { nav(`/interventions/${i.intervention_i`); setResults(null) | onClick | WIRED |
| components/Shell.tsx | 123 | button | { nav(`/archive?doc=${d.document_id}`); setResults(null); }} | onClick | WIRED |
| components/Shell.tsx | 127 | select | setLang(e.target.value as Lang)} aria-label={t("language")}> | onChange | WIRED |
| components/Shell.tsx | 128 | select | setRole(e.target.value)} aria-label={t("role")}> {t("role_ex | onChange | WIRED |
| components/Shell.tsx | 129 | button | openCopilot()} aria-label={t("copilot")}> {t("copilot")} {me | onClick | WIRED |
| components/Shell.tsx | 131 | NavLink | {t("rebuild")} } {children} {copil | to | WIRED |
| components/Shell.tsx | 136 | button | setCopilot({ ...copilot, open: false })} aria-label={t("clos | onClick | WIRED |
| components/Shell.tsx | 139 | button | askCopilot(s)}>{s} )} {copilot.busy && } { | onClick | WIRED |
| components/Shell.tsx | 147 | button | nav(`/wells/${w}`)}>{w} )} } {copilot.answer.economic_assump | onClick | WIRED |
| components/Shell.tsx | 149 | button | nav(`/archive?doc=${d.document_id}`)}>{d.file_name} )} } mod | onClick | WIRED |
| components/Shell.tsx | 154 | input | setCopilot({ ...copilot, q: e.target.value })} onKeyDown={(e | onChange | WIRED |
| components/Shell.tsx | 154 | button | askCopilot(copilot.q)} disabled={copilot.busy // !copilot.q. | onClick | WIRED |
| components/overlay.tsx | 210 | button | setPinned(false)} aria-label={t("x_close")}>✕ } )} {content} | onClick | WIRED |
| components/ui.tsx | 50 | a | corner.label | href | WIRED |
| components/ui.tsx | 50 | button | corner.label | onClick | WIRED |
| components/ui.tsx | 129 | button | t( | onClick | WIRED |
| components/ui.tsx | 165 | button | onChange(tb.key)}>{tb.label} )} ); } export function Empty({ | onClick | WIRED |
| components/ui.tsx | 179 | button | {t("retry")} } ; } export function useFetch (url: string / n | onClick | WIRED |
| components/ui.tsx | 217 | button | submit("ACCEPT")} disabled={busy}>{t("accept")} setOpen("M | onClick | WIRED |
| components/ui.tsx | 218 | button | setOpen("MODIFY")} disabled={busy}>{t("modify")} se | onClick | WIRED |
| components/ui.tsx | 219 | button | setOpen("REJECT")} disabled={busy}>{t("reject")} sub | onClick | WIRED |
| components/ui.tsx | 220 | button | submit("DEFER")} disabled={busy}>{t("defer")} {open && ( | onClick | WIRED |
| components/ui.tsx | 225 | select | setReason(e.target.value)} className="w-full mb-2" aria-labe | onChange | WIRED |
| components/ui.tsx | 226 | textarea | setNotes(e.target.value)} className="w-full mb-2" rows={2} p | onChange | WIRED |
| components/ui.tsx | 227 | button | submit(open)}>{t("confirm")} setOpen(null)}>{t("cancel")} </ | onClick | WIRED |
| components/ui.tsx | 227 | button | setOpen(null)}>{t("cancel")} )} ); } export function Labeled | onClick | WIRED |
| pages/Field.tsx | 59 | button | nav(`/wells/${wellId}`)}>{t("open")} {t("well").toLowerCase( | onClick | WIRED |
| pages/Field.tsx | 59 | button | setCompare(!compare)}>{t("compare_scenarios")} <Icon name="d | onClick | WIRED |
| pages/Field.tsx | 59 | a | {t("export_pdf")} <div className="grid g | href | WIRED |
| pages/Field.tsx | 76 | button | nav(`/wells/${w}`)}>{w} )} {t("x_how_much")} {fmt.n(data.why | onClick | WIRED |
| pages/Field.tsx | 127 | button | nav(`/wells/${wellId}?tab=causal`)}>{t("open")} {t("tab_caus | onClick | WIRED |
| pages/Field.tsx | 127 | a | {t("export_pdf")} <HeroChart analysis={data.analysis} compa | href | WIRED |
| pages/Field.tsx | 173 | select | setUnit(e.target.value as Any)}> bbl m³ <div className="grid | onChange | WIRED |
| pages/Field.tsx | 183 | input | setEdits({ ...edits, [k2]: Number(e.target.value))} /> $/bbl | onChange | WIRED |
| pages/Field.tsx | 184 | button | {saving ? t("loading") : t("save")} setEdits({})}>{t("cancel | onClick | WIRED |
| pages/Field.tsx | 184 | button | setEdits({})}>{t("cancel")} {t("facility")} {t("util | onClick | WIRED |
| pages/Field.tsx | 192 | select | setSc({ ...sc, well_id: e.target.value })}>{data.rows.map((r | onChange | WIRED |
| pages/Field.tsx | 193 | label | {l} <input type="number" step={k2 === "success_probability"  | input | WIRED |
| pages/Field.tsx | 193 | input | setSc({ ...sc, [k2]: Number(e.target.value) })} /> )} {t | onChange | WIRED |
| pages/Field.tsx | 195 | button | {t("apply")} {scRes && <Kpi label={t("net_value")} valu | onClick | WIRED |
| pages/Guide.tsx | 79 | button | nav("/map")}>{t("g_open_map")} nav("/")}>{t("g_open_overview | onClick | WIRED |
| pages/Guide.tsx | 80 | button | nav("/")}>{t("g_open_overview")} {t("g_sub")} {/* live p | onClick | WIRED |
| pages/Guide.tsx | 107 | button | nav("/map")}>{t("g_open_map")} } /> <Step n="2" icon="data"  | onClick | WIRED |
| pages/Guide.tsx | 109 | button | nav("/data")}>{t("nav_datahub")} } /> <Step n="3" icon="grid | onClick | WIRED |
| pages/Guide.tsx | 111 | button | nav("/")}>{t("nav_overview")} } /> | onClick | WIRED |
| pages/Interventions.tsx | 36 | button | nav("/data")}>{t("nav_datahub")} nav("/data/imports")}>{t("x | onClick | WIRED |
| pages/Interventions.tsx | 37 | button | nav("/data/imports")}>{t("x_import_int")} ); } return ( <div | onClick | WIRED |
| pages/Interventions.tsx | 95 | button | nav(`/wells/${r.well_id}`)}>{r.well_id} · {r.date} · {iType( | onClick | WIRED |
| pages/Interventions.tsx | 97 | button | donorsRef.current?.scrollIntoView({ behavior: "smooth" })}>{ | onClick | WIRED |
| pages/Interventions.tsx | 98 | button | nav(`/wells/${r.well_id}?tab=causal`)}>{t("view_donors")} <b | onClick | WIRED |
| pages/Interventions.tsx | 99 | button | {t("rerun")} nav("/settings")}>{t("change_assumpti | onClick | WIRED |
| pages/Interventions.tsx | 100 | button | nav("/settings")}>{t("change_assumptions")} {t("mark_reviewe | onClick | WIRED |
| pages/Interventions.tsx | 101 | button | {t("mark_reviewed")} <Icon name="download" size={1 | onClick | WIRED |
| pages/Interventions.tsx | 102 | a | {t("export_pdf")} download(`${id}.csv`, toCSV([r], | href | WIRED |
| pages/Interventions.tsx | 103 | button | download(`${id}.csv`, toCSV([r], Object.keys(r).filter((k) = | onClick | WIRED |
| pages/Interventions.tsx | 112 | textarea | setNote(e.target.value)} placeholder={t("add_note")} /> {t(" | onChange | WIRED |
| pages/Interventions.tsx | 112 | button | {t("add_note")} {data.notes.map((n: Any) => <div key={n. cla | onClick | WIRED |
| pages/Interventions.tsx | 117 | button | nav(`/archive?doc=${d.document_id}`)}>{d.file_name} ) : <div | onClick | WIRED |
| pages/Interventions.tsx | 117 | button | nav("/archive")}>{t("upload")} } ); } export function Compar | onClick | WIRED |
| pages/Lab.tsx | 83 | button | setReveal(!reveal)}>{reveal ? t("hide") : t("reveal")} <Card | onClick | WIRED |
| pages/Lab.tsx | 133 | a | e.stopPropagation()}>JSON }]} onRow={(r) => nav(`/wells/${r. | href | WIRED |
| pages/Lab.tsx | 153 | select | setF({ ...f, field: e.target.value })}> {t("field_all")} {da | onChange | WIRED |
| pages/Lab.tsx | 154 | select | setF({ ...f, tag: e.target.value })}> {t("status")} {["produ | onChange | WIRED |
| pages/Lab.tsx | 155 | select | setF({ ...f, conf: e.target.value })}> {t("confidence")} {[" | onChange | WIRED |
| pages/Lab.tsx | 156 | select | setF({ ...f, itype: e.target.value })}> {t("est_intervention | onChange | WIRED |
| pages/Lab.tsx | 157 | label | {t("water_cut")} ≥ {fmt.pct(f.wc)} setF({ ...f, wc: Number(e | input | WIRED |
| pages/Lab.tsx | 157 | input | setF({ ...f, wc: Number(e.target.value) })} style={{ width:  | onChange | WIRED |
| pages/Map.tsx | 193 | input | setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && | onChange | WIRED |
| pages/Map.tsx | 199 | button | pick(r)}> {r.uwi // r.record_id} · {r.surface_location} · {r | onClick | WIRED |
| pages/Map.tsx | 208 | button | {t("x_search2")} setStatus(e.target.value)} ar | onClick | WIRED |
| pages/Map.tsx | 210 | select | setStatus(e.target.value)} aria-label={t("x_status2")}> {t(" | onChange | WIRED |
| pages/Map.tsx | 214 | select | setFluid(e.target.value)} aria-label={t("x_fluid")}> {t("m_a | onChange | WIRED |
| pages/Map.tsx | 218 | select | setLayer(e.target.value)} aria-label={t("x_layer")}> {LAYERS | onChange | WIRED |
| pages/Map.tsx | 221 | input | setOperator(e.target.value)} placeholder={t("m_operator_cont | onChange | WIRED |
| pages/Map.tsx | 222 | label | setProducing(e.target.checked)} />Reported oil &gt; 0 | input | WIRED |
| pages/Map.tsx | 223 | input | setProducing(e.target.checked)} />Reported oil &gt; 0 | onChange | WIRED |
| pages/Map.tsx | 225 | label | setShowFacilities(e.target.checked)} />Facilities | input | WIRED |
| pages/Map.tsx | 226 | input | setShowFacilities(e.target.checked)} />Facilities | onChange | WIRED |
| pages/Map.tsx | 228 | label | setShowPipelines(e.target.checked)} />Pipelines < | input | WIRED |
| pages/Map.tsx | 229 | input | setShowPipelines(e.target.checked)} />Pipelines setBasemap(e | onChange | WIRED |
| pages/Map.tsx | 231 | select | setBasemap(e.target.value as Basemap)} aria-label={t("x_base | onChange | WIRED |
| pages/Map.tsx | 237 | button | mapRef.current?.fitAlberta()}>{t("x_reset_view")} <div class | onClick | WIRED |
| pages/Map.tsx | 260 | button | setTab("data")}>{t("x_install_ds")} )} {installed && loading | onClick | WIRED |
| pages/Ops.tsx | 50 | input | setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && | onChange | WIRED |
| pages/Ops.tsx | 50 | button | {t("search")} {["pump replacement water cut above 80", "scal | onClick | WIRED |
| pages/Ops.tsx | 51 | button | { setQ(s); api.get(`/api/archive/search?`).then(setHits); }} | onClick | WIRED |
| pages/Ops.tsx | 52 | button | setSp({ doc: h.document_id })}> {h.file_name} <span classNam | onClick | WIRED |
| pages/Ops.tsx | 56 | label | {t("upload")}<input type="file" className="hidden" accept=". | input | WIRED |
| pages/Ops.tsx | 56 | input | upload(e.target.files?.[0] // null)} disabled={busy} /> }> { | onChange | WIRED |
| pages/Ops.tsx | 57 | button | setIdx(i)}> {d.file_name} <Badge label={d.review_st | onClick | WIRED |
| pages/Ops.tsx | 63 | button | setIdx(Math.max(0, idx - 1))} disabled={idx === 0}>{t("previ | onClick | WIRED |
| pages/Ops.tsx | 63 | button | setIdx(Math.min(docs.length - 1, idx + 1))} disabled={idx >= | onClick | WIRED |
| pages/Ops.tsx | 63 | a | file extract< | href | WIRED |
| pages/Ops.tsx | 63 | button | extract }> {doc.document.note // ""} {doc. | onClick | WIRED |
| pages/Ops.tsx | 65 | button | review("approve")} disabled={busy}>{t("approve")} (A) setEdi | onClick | WIRED |
| pages/Ops.tsx | 65 | button | setEditing(!editing)}>{t("edit")} (E) review("reject")} disa | onClick | WIRED |
| pages/Ops.tsx | 65 | button | review("reject")} disabled={busy}>{t("reject")} (R) review(" | onClick | WIRED |
| pages/Ops.tsx | 65 | button | review("unreadable")} disabled={busy}>{t("unreadable")} (U)  | onClick | WIRED |
| pages/Ops.tsx | 65 | button | review("edit")} disabled={busy // !Object.keys(edits).length | onClick | WIRED |
| pages/Ops.tsx | 74 | input | setEdits({ ...edits, [k]: e.target.value })} /> : {v.value = | onChange | WIRED |
| pages/Ops.tsx | 76 | button | `Source p.${v.page | onClick | WIRED |
| pages/Ops.tsx | 127 | a | {t("sample_schema")} nav("/data/imports")}>{t("import | href | WIRED |
| pages/Ops.tsx | 127 | button | nav("/data/imports")}>{t("import_wizard")} {busy && <Progres | onClick | WIRED |
| pages/Ops.tsx | 139 | button | act(c, "connect")} disabled={!!busy}>{busy === c.id + "conne | onClick | WIRED |
| pages/Ops.tsx | 140 | button | act(c, "refresh")} disabled={!!busy}>{t("refresh")} } act(c, | onClick | WIRED |
| pages/Ops.tsx | 141 | button | act(c, "schema")}>{t("view_schema")} {c.connected && act(c,  | onClick | WIRED |
| pages/Ops.tsx | 142 | button | act(c, "sample")}>{t("view_sample")} } {c.connected && c.id  | onClick | WIRED |
| pages/Ops.tsx | 143 | button | act(c, "disconnect")}>{t("disconnect")} } {c.url && <a class | onClick | WIRED |
| pages/Ops.tsx | 144 | a | source ↗ } ))} setPanel(null)} titl | href | WIRED |
| pages/Ops.tsx | 179 | a | {t("sample_schema")} {steps.map((s, i) => <span key= | href | WIRED |
| pages/Ops.tsx | 182 | label | {t("step_upload")} (.csv / .xlsx)<input type="file" classNam | input | WIRED |
| pages/Ops.tsx | 182 | input | { const f = e.target.files?.[0] // null;} /> } {step === 1 & | onChange | WIRED |
| pages/Ops.tsx | 183 | button | {t("back")} setStep(2)}>{t("next")} } {step === 2 && prev | onClick | WIRED |
| pages/Ops.tsx | 183 | button | setStep(2)}>{t("next")} } {step === 2 && prev && <div classN | onClick | WIRED |
| pages/Ops.tsx | 184 | select | setMap({ ...map, [c]: e.target.value })} className="flex-1"> | onChange | WIRED |
| pages/Ops.tsx | 184 | button | setStep(1)}>{t("back")} map[r])}>{t("st | onClick | WIRED |
| pages/Ops.tsx | 184 | button | map[r])}>{t("step_validate")} } {step === 3 && val && {val.e | onClick | WIRED |
| pages/Ops.tsx | 185 | button | setStep(2)}>{t("back")} setStep(mode === "production" ? 4 :  | onClick | WIRED |
| pages/Ops.tsx | 185 | button | setStep(mode === "production" ? 4 : 5)}>{t("next")} } {step  | onClick | WIRED |
| pages/Ops.tsx | 186 | select | setUnits({ ...units, [u]: e.target.value })}>{u === "gas" ?  | onChange | WIRED |
| pages/Ops.tsx | 186 | button | setStep(3)}>{t("back")} setStep(5)}>{t("next")} } {step | onClick | WIRED |
| pages/Ops.tsx | 186 | button | setStep(5)}>{t("next")} } {step === 5 && File {file?.name} | onClick | WIRED |
| pages/Ops.tsx | 187 | label | dataset name setName(e.target.value)} /> } <button className | input | WIRED |
| pages/Ops.tsx | 187 | input | setName(e.target.value)} /> } setStep(mode === "production" | onChange | WIRED |
| pages/Ops.tsx | 187 | button | setStep(mode === "production" ? 4 : 3)}>{t("back")} {busy ?  | onClick | WIRED |
| pages/Ops.tsx | 187 | button | {busy ? t("loading") : t("step_ingest")} } {step === 6 && re | onClick | WIRED |
| pages/Ops.tsx | 188 | button | {t("reset")} } ); } // ------------------------------------- | onClick | WIRED |
| pages/Ops.tsx | 207 | a | {t("export_csv")} }> {!data.decisions.length ? {t("x_no_dec | href | WIRED |
| pages/Ops.tsx | 229 | input | upd(isP ? [...path, "value"] : path, e.target.checked)} /> : | onChange | WIRED |
| pages/Ops.tsx | 229 | input | upd(isP ? [...path, "value"] : path, Number(e.target.value)) | onChange | WIRED |
| pages/Ops.tsx | 229 | input | upd(isP ? [...path, "value"] : path, e.target.value)} />} {u | onChange | WIRED |
| pages/Ops.tsx | 233 | button | {t("save")} {t("reset_defaults")} rebuild( | onClick | WIRED |
| pages/Ops.tsx | 233 | button | {t("reset_defaults")} rebuild(false)} disabled={!!steps}>{t( | onClick | WIRED |
| pages/Ops.tsx | 233 | button | rebuild(false)} disabled={!!steps}>{t("rebuild")} (economics | onClick | WIRED |
| pages/Ops.tsx | 233 | button | rebuild(true)} disabled={!!steps}>{t("rebuild")} (full) {met | onClick | WIRED |
| pages/Ops.tsx | 237 | select | upd(["units", "volume"], ev.target.value)}> bbl m³ <Field pa | onChange | WIRED |
| pages/Ops.tsx | 244 | select | upd(["portfolio", "objective"], ev.target.value)}>{["npv", " | onChange | WIRED |
| pages/Ops.tsx | 245 | select | upd(["archive", "llm_provider"], ev.target.value)}>{["mock", | onChange | WIRED |
| pages/Ops.tsx | 246 | button | { await api.post(`/api/data/activate/${d`); reloadMeta(); to | onClick | WIRED |
| pages/Overview.tsx | 67 | button | nav(`/wells/${a.well_id}`)}>{a.well_id} {iType( | onClick | WIRED |
| pages/Overview.tsx | 76 | button | nav(`/wells/${r.well_id}?tab=causal`)}> {r.well_id} <Badge l | onClick | WIRED |
| pages/Overview.tsx | 111 | button | setFlt(flt === k ? "" : k)}>{t(lbl as Any)} )} } /> )} ); }  | onClick | WIRED |
| pages/Portfolio.tsx | 58 | label | {t("budget")} · {fmt.money(cons.budget)} <input type="range" | input | WIRED |
| pages/Portfolio.tsx | 59 | input | setC("budget", Number(e.target.value))} className="w-full" a | onChange | WIRED |
| pages/Portfolio.tsx | 61 | label | {t(kk as Any)} setC(kk, Num | input | WIRED |
| pages/Portfolio.tsx | 61 | input | setC(kk, Number(e.target.value))} /> )} {t("objective")}< | onChange | WIRED |
| pages/Portfolio.tsx | 64 | select | setObj(e.target.value)} className="w-full">{OBJ.map((o) => { | onChange | WIRED |
| pages/Portfolio.tsx | 65 | label | {kk} setWeights({ ...weights, [kk] | input | WIRED |
| pages/Portfolio.tsx | 65 | input | setWeights({ ...weights, [kk]: Number(e.target.valu)} onBlur | onChange | WIRED |
| pages/Portfolio.tsx | 67 | button | optimise()} disabled={busy}> {t("optimise")} setMa | onClick | WIRED |
| pages/Portfolio.tsx | 68 | button | setManual({ well_id: "", action: "cleanout", cost: 30000, np | onClick | WIRED |
| pages/Portfolio.tsx | 69 | button | {t("compare_plan")} saveScenario(false)}>{t("save_scenario") | onClick | WIRED |
| pages/Portfolio.tsx | 70 | button | saveScenario(false)}>{t("save_scenario")} saveScenario(true) | onClick | WIRED |
| pages/Portfolio.tsx | 71 | button | saveScenario(true)}>{t("duplicate_scenario")} <Icon name="re | onClick | WIRED |
| pages/Portfolio.tsx | 72 | button | {t("reset")} <Icon name="d | onClick | WIRED |
| pages/Portfolio.tsx | 73 | button | {t("export_plan")} {t("tornado")}</button | onClick | WIRED |
| pages/Portfolio.tsx | 74 | button | {t("tornado")} {scenarios.length > 0 && <Card title={t( corn | onClick | WIRED |
| pages/Portfolio.tsx | 100 | button | nav(`/wells/${s.well_id}`)}>{s.well_id} <button className="b | onClick | WIRED |
| pages/Portfolio.tsx | 100 | button | lock(s)} aria-label={s.locked ? t("unlock_job") : t("lock_jo | onClick | WIRED |
| pages/Portfolio.tsx | 100 | button | remove(s)} aria-label={t("remove_job")} title={t("remove_job | onClick | WIRED |
| pages/Portfolio.tsx | 109 | button | { e.stopPropagation(); lock(r); }}>{r.locked ? t("unlock_job | onClick | WIRED |
| pages/Portfolio.tsx | 109 | button | { e.stopPropagation(); remove(r); }}>{t("remove_job")} }]} o | onClick | WIRED |
| pages/Portfolio.tsx | 113 | button | restore(c.candidate_id)}>{t("include")} } )} )} <Draw | onClick | WIRED |
| pages/Portfolio.tsx | 129 | select | setManual({ ...manual, [kk]: e.target.value })}> rigless rig | onChange | WIRED |
| pages/Portfolio.tsx | 129 | input | setManual({ ...manual, [kk]: typeof v === "number")} />} )}< | onChange | WIRED |
| pages/Portfolio.tsx | 129 | label | safety block (leave empty if none) setManual({ ...ma | input | WIRED |
| pages/Portfolio.tsx | 129 | input | setManual({ ...manual, safety_block: e.target.valu)} /> <but | onChange | WIRED |
| pages/Portfolio.tsx | 129 | button | {t("save")} setManual(null)}>{t("cancel")} <div className="c | onClick | WIRED |
| pages/Portfolio.tsx | 129 | button | setManual(null)}>{t("cancel")} {t("x_manual_jobs")} } | onClick | WIRED |
| pages/Portfolio.tsx | 146 | button | del(s.scenario_id)}>{t("remove_job")} )} ); } | onClick | WIRED |
| pages/Presentation.tsx | 39 | button | nav(`/interventions/${ex.intervention_id}`)}>{t("demo_open") | onClick | WIRED |
| pages/Presentation.tsx | 41 | button | nav("/ghost")}>{t("demo_open")} , <Title sub="Every barrel o | onClick | WIRED |
| pages/Presentation.tsx | 42 | button | nav("/water")}>{t("demo_open")} , <Title sub="Move the budge | onClick | WIRED |
| pages/Presentation.tsx | 43 | label | budget · {fmt.money(budget)} <input type="range" min={0} max | input | WIRED |
| pages/Presentation.tsx | 43 | input | setBudget(Number(e.target.value))} className="w-full my-3" / | onChange | WIRED |
| pages/Presentation.tsx | 43 | button | nav("/portfolio")}>{t("demo_open")} , <Title sub={blind.data | onClick | WIRED |
| pages/Presentation.tsx | 44 | button | setReveal(!reveal)}>{reveal ? t("hide") : t("reveal")} metho | onClick | WIRED |
| pages/Presentation.tsx | 45 | button | nav(`/archive?doc=${doc.document.document_id}`)}>{t("x_revie | onClick | WIRED |
| pages/Presentation.tsx | 50 | button | nav("/")}> {t("demo_exit")} {slides[i]} <div className=" | onClick | WIRED |
| pages/Presentation.tsx | 52 | button | setI(Math.max(0, i - 1))} disabled={i === 0}>← {t("previous" | onClick | WIRED |
| pages/Presentation.tsx | 52 | button | setI(j)} aria-label={sname} />)} setI(Math.min(STEPS.length  | onClick | WIRED |
| pages/Presentation.tsx | 52 | button | setI(Math.min(STEPS.length - 1, i + 1))} disabled={i === STE | onClick | WIRED |
| pages/WellDetail.tsx | 36 | button | setSp({ tab: "causal" })}> {t("run_analysis")} {data.idle && | onClick | WIRED |
| pages/WellDetail.tsx | 37 | button | nav(`/idle?well=${id}`)}>{t("compare_scenarios")} } {rec &&  | onClick | WIRED |
| pages/WellDetail.tsx | 38 | button | {t("add_to_plan")} } openCopilot(`Why was ${id} flagged?`)}> | onClick | WIRED |
| pages/WellDetail.tsx | 39 | button | openCopilot(`Why was ${id} flagged?`)}>{t("ask_archive")} <a | onClick | WIRED |
| pages/WellDetail.tsx | 40 | a | {t("export_pdf")} <Tabs value={tab} onChange={(k) | href | WIRED |
| pages/WellDetail.tsx | 47 | button | nav("/data/imports")}>{t("x_import_int")} nav("/archive")}>{ | onClick | WIRED |
| pages/WellDetail.tsx | 47 | button | nav("/archive")}>{t("x_upload_archive")} } } {tab === "causa | onClick | WIRED |
| pages/WellDetail.tsx | 150 | button | { e.stopPropagation(); nav(`/wells/${r.w`); }}>{r.well_id} } | onClick | WIRED |
| pages/WellDetail.tsx | 157 | button | { e.stopPropagation(); toggleDonor(r.wel} disabled={locked}> | onClick | WIRED |
| pages/WellDetail.tsx | 164 | select | = 0 ? events.indexOf(ev) : 0} onChange={(e) => setEv(events[ |  | WIRED |
| pages/WellDetail.tsx | 165 | select | setModel(e.target.value)} aria-label={t("model")}> AUTO {t(" | onChange | WIRED |
| pages/WellDetail.tsx | 166 | button | rerun()} disabled={!!steps}> {t("run_analysis")} {ana | onClick | WIRED |
| pages/WellDetail.tsx | 168 | a | {t("export_json")} } {analysis && download(`${data. | href | WIRED |
| pages/WellDetail.tsx | 169 | button | download(`${data.well_id}_analysis.csv`, toCSV(analysis.mont | onClick | WIRED |
| pages/WellDetail.tsx | 175 | button | setRules(await api.get("/api/eligibility-rules"))}>{t("eligi | onClick | WIRED |
| pages/WellDetail.tsx | 190 | button | { setLocked(!locked); rerun(excl, !locke}> {locked ? t("unlo | onClick | WIRED |
| pages/WellDetail.tsx | 190 | button | rerun()} disabled={!!steps}>{t("rerun")} }> <DataTable id="d | onClick | WIRED |
| pages/WellDetail.tsx | 197 | button | setRules(null)}>{t("close")} }> {rules.rules.map((r: string, | onClick | WIRED |
| pages/WellDetail.tsx | 215 | label | {l} | input | WIRED |
| pages/WellDetail.tsx | 215 | input | setF({ ...f, [k]: Number(e.target.value) })} /> )} {t("app | onChange | WIRED |
| pages/WellDetail.tsx | 217 | button | {t("apply")} {res && {t("net_value")}: {fmt.money(res.exp | onClick | WIRED |
| pages/WellDetail.tsx | 230 | label | {t("upload")} up(e.target.files?.[0] // null)} disable | input | WIRED |
| pages/WellDetail.tsx | 230 | input | up(e.target.files?.[0] // null)} disabled={busy} /> }> {!dat | onChange | WIRED |
| pages/WellDetail.tsx | 232 | button | nav(`/archive?doc=${d.document_id}`)}> {d.file_name} <Badge  | onClick | WIRED |
| pages/WellDetail.tsx | 244 | textarea | setNote(e.target.value)} placeholder={t("add_note")} /> {t(" | onChange | WIRED |
| pages/WellDetail.tsx | 244 | button | {t("add_note")} {data.notes.map((n: Any) => <div key={n. cla | onClick | WIRED |
| pages/map/DataSources.tsx | 63 | button | run(s.kind)}> {s.connected ? "Refresh" : "Install"} {["casin | onClick | WIRED |
| pages/map/DataSources.tsx | 69 | a | {t("x_aer_gwd")} {" "} and run --file {s.kind}=path.csv . | href | WIRED |
| pages/map/DataSources.tsx | 77 | a | the AER catalogue {" "} then run python scripts/update_alber | href | WIRED |
| pages/map/DataSources.tsx | 98 | select | setMonths(Number(e.target.value))} aria-label={t("m_ds_month | onChange | WIRED |
| pages/map/DataSources.tsx | 101 | button | run("petrinex", { months })}> {petrinex ? "Refresh" : "Insta | onClick | WIRED |
| pages/map/WellPanel.tsx | 368 | select | setForm({ ...form, intervention_type: e.target.v)}> {["clean | onChange | WIRED |
| pages/map/WellPanel.tsx | 372 | label | {t("x_oil_uplift_frac")} <input type="number" step="0.01" va | input | WIRED |
| pages/map/WellPanel.tsx | 373 | input | setForm({ ...form, uplift_fraction: Number(e.tar)} /> <span | onChange | WIRED |
| pages/map/WellPanel.tsx | 375 | label | {t("x_success_prob")} <input type="number" step="0.01" min=" | input | WIRED |
| pages/map/WellPanel.tsx | 376 | input | setForm({ ...form, success_probability: Number(e)} /> <s | onChange | WIRED |
| pages/map/WellPanel.tsx | 378 | label | {t("x_horizon")} <input type="number" min="1" max="60" value | input | WIRED |
| pages/map/WellPanel.tsx | 379 | input | setForm({ ...form, horizon_months: Number(e.targ)} /> <butto | onChange | WIRED |
| pages/map/WellPanel.tsx | 382 | button | {busy ? "Running…" : "Run scenario"} {err && } {run && | onClick | WIRED |

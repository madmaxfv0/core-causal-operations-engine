import React, { useMemo, useState } from "react";
import { Any, download, ls, toCSV } from "../lib/api";
import { useT } from "../lib/i18n";
import { Icon } from "./ui";

export type Col = { key: string; label: React.ReactNode; render?: (row: Any) => React.ReactNode; num?: boolean; sortValue?: (row: Any) => Any; hidden?: boolean; width?: number };

export function DataTable({ id, rows, columns, onRow, selectedKey, rowKey = "well_id", pageSize = 40, toolbar, searchKeys, defaultSort, dense }: { id: string; rows: Any[]; columns: Col[]; onRow?: (row: Any) => void; selectedKey?: string | null; rowKey?: string; pageSize?: number; toolbar?: React.ReactNode; searchKeys?: string[]; defaultSort?: { key: string; dir: "asc" | "desc" }; dense?: boolean }) {
  const { t } = useT();
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(defaultSort || null);
  const [q, setQ] = useState("");
  const [hidden, setHidden] = useState<string[]>(ls.get(`core.table.${id}.hidden`, columns.filter((c) => c.hidden).map((c) => c.key)));
  const [showCols, setShowCols] = useState(false);
  const [views, setViews] = useState<Record<string, Any>>(ls.get(`core.table.${id}.views`, {}));
  const [page, setPage] = useState(0);
  const visible = columns.filter((c) => !hidden.includes(c.key));
  const filtered = useMemo(() => {
    let r = rows;
    if (q) { const ql = q.toLowerCase(); const keys = searchKeys || columns.map((c) => c.key); r = r.filter((row) => keys.some((k) => String(row[k] ?? "").toLowerCase().includes(ql))); }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      const gv = (row: Any) => (col?.sortValue ? col.sortValue(row) : row[sort.key]);
      r = [...r].sort((a, b) => { const va = gv(a), vb = gv(b); if (va === vb) return 0; if (va === null || va === undefined) return 1; if (vb === null || vb === undefined) return -1; return (va > vb ? 1 : -1) * (sort.dir === "asc" ? 1 : -1); });
    }
    return r;
  }, [rows, q, sort, columns, searchKeys]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const slice = filtered.slice(page * pageSize, (page + 1) * pageSize);
  const toggleCol = (k: string) => { const h = hidden.includes(k) ? hidden.filter((x) => x !== k) : [...hidden, k]; setHidden(h); ls.set(`core.table.${id}.hidden`, h); };
  const saveView = () => { const name = prompt(t("scenario_name")); if (!name) return; const v = { ...views, [name]: { hidden, sort, q } }; setViews(v); ls.set(`core.table.${id}.views`, v); };
  const applyView = (name: string) => { const v = views[name]; if (!v) return; setHidden(v.hidden); setSort(v.sort); setQ(v.q || ""); };
  const exportCsv = () => download(`${id}.csv`, toCSV(filtered, visible.map((c) => c.key)));
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="relative"><span className="absolute left-3 top-2.5 faint"><Icon name="search" size={14} /></span><input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder={t("search")} className="pl-8" style={{ width: 220 }} aria-label={t("search")} /></div>
        {toolbar}
        <span className="flex-1" />
        <span className="faint text-[12px]">{filtered.length} {t("rows")}</span>
        <div className="relative">
          <button className="btn sm" onClick={() => setShowCols(!showCols)}>{t("columns")}</button>
          {showCols && <div className="glass-strong absolute right-0 top-9 z-30 p-3 w-[220px] fade-in">{columns.map((c) => <label key={c.key} className="flex items-center gap-2 py-1 text-[12px] cursor-pointer"><input type="checkbox" checked={!hidden.includes(c.key)} onChange={() => toggleCol(c.key)} />{c.label}</label>)}</div>}
        </div>
        {Object.keys(views).length > 0 && <select className="text-[12px]" style={{ padding: "5px 8px" }} onChange={(e) => e.target.value && applyView(e.target.value)} defaultValue="" aria-label={t("saved_views")}><option value="">{t("saved_views")}</option>{Object.keys(views).map((v) => <option key={v} value={v}>{v}</option>)}</select>}
        <button className="btn sm" onClick={saveView}>{t("save_view")}</button>
        <button className="btn sm" onClick={exportCsv}><Icon name="download" size={14} />{t("export_csv")}</button>
      </div>
      <div className="overflow-auto" style={{ maxHeight: dense ? 420 : "calc(100vh - 320px)" }}>
        <table className="core">
          <thead><tr>{visible.map((c) => <th key={c.key} onClick={() => setSort(sort?.key === c.key ? { key: c.key, dir: sort.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: c.num ? "desc" : "asc" })} className={c.num ? "num" : ""} style={c.width ? { width: c.width } : undefined}>{c.label}{sort?.key === c.key && <span className="faint"> {sort.dir === "asc" ? "↑" : "↓"}</span>}</th>)}</tr></thead>
          <tbody>
            {slice.map((row, i) => (
              <tr key={row[rowKey] ?? i} className={`row ${selectedKey && row[rowKey] === selectedKey ? "selected" : ""}`} onClick={() => onRow?.(row)} tabIndex={onRow ? 0 : -1} onKeyDown={(e) => { if (e.key === "Enter") onRow?.(row); }}>
                {visible.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{c.render ? c.render(row) : (row[c.key] ?? <span className="faint">—</span>)}</td>)}
              </tr>
            ))}
            {!slice.length && <tr><td colSpan={visible.length} className="subtle text-center py-8">{t("no_results")}</td></tr>}
          </tbody>
        </table>
      </div>
      {pages > 1 && <div className="flex items-center justify-end gap-2 mt-2 text-[12px]"><button className="btn sm ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>{t("previous")}</button><span className="faint">{page + 1} / {pages}</span><button className="btn sm ghost" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>{t("next")}</button></div>}
    </div>
  );
}

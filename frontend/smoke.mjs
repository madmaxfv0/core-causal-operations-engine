import { JSDOM, VirtualConsole } from "jsdom";
import fs from "fs";
// SMOKE_BASE points at a running CORE API, e.g. SMOKE_BASE=http://127.0.0.1:8765
const BASE = (process.env.SMOKE_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const html = fs.readFileSync("dist/index.html", "utf8");
// the entry chunk only; lazily loaded chunks (the map) are imported at runtime
// The entry chunk only; lazily loaded chunks (the map) are fetched at runtime and
// are exercised in the browser instead. `w.eval` cannot run an ES module, so the
// trailing `export{...}` the code-split build emits is stripped.
const js = fs.readFileSync("dist/assets/" + fs.readdirSync("dist/assets").find(f => /^index-.*\.js$/.test(f)), "utf8")
  .replace(/\bexport\s*\{[^}]*\};?\s*$/, "");
const routes = ["/", "/wells", "/wells/SYN-050", "/wells/SYN-050?tab=causal", "/wells/SYN-006?tab=water", "/wells/SYN-031?tab=documents", "/ghost", "/ghost?well=SYN-006", "/idle", "/idle?well=SYN-050", "/network", "/interventions", "/interventions/compare", "/interventions/INT-001", "/water", "/portfolio", "/portfolio/scenarios", "/archive", "/archive/ask", "/model-lab", "/model-lab?tab=placebo", "/model-lab?tab=blind", "/model-lab?tab=calibration", "/model-lab?tab=reason", "/model-lab?tab=sensitivity", "/model-lab?tab=cards", "/quality", "/data", "/data/imports", "/decisions", "/runs", "/settings", "/why", "/present", "/map", "/guide"];
const errors = [];
for (const route of routes) {
  const vc = new VirtualConsole();
  const errs = [];
  vc.on("jsdomError", e => { if (!/Not implemented/.test(String(e.message))) errs.push("jsdomError: " + e.message); });
  vc.on("error", (...a) => { const s = a.map(String).join(" "); if (!/Not implemented|act\(|ResizeObserver|width\(0\)|height\(0\)|Warning:/.test(s)) errs.push("console.error: " + s.slice(0, 300)); });
  const dom = new JSDOM(html.replace(/<script[^>]*src="\/assets\/[^"]*"[^>]*><\/script>/, ""), { url: BASE + route, pretendToBeVisual: true, runScripts: "outside-only", virtualConsole: vc });
  const w = dom.window;
  w.fetch = (u, o) => fetch(typeof u === "string" && u.startsWith("/") ? BASE + u : u, o);
  w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  w.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  w.HTMLElement.prototype.scrollIntoView = () => {};
  // jsdom has no object URLs, workers or WebGL; the map chunk needs them to import.
  w.URL.createObjectURL = () => "blob:smoke"; w.URL.revokeObjectURL = () => {};
  w.Worker = class { postMessage() {} terminate() {} addEventListener() {} removeEventListener() {} };
  w.HTMLCanvasElement.prototype.getContext = () => null;
  w.confirm = () => false; w.prompt = () => null;
  w.addEventListener("error", e => errs.push("window error: " + (e.error?.stack || e.message).slice(0, 400)));
  try { w.eval(js); } catch (e) { errs.push("eval: " + String(e.stack || e).slice(0, 400)); }
  // REAL mode loads a much larger data set; give slow pages time before judging them.
  await new Promise(r => setTimeout(r, Number(process.env.SMOKE_WAIT || 2500)));
  const text = w.document.body.textContent || "";
  const ok = text.length > 200 && !/Something went wrong/.test(text);
  console.log((errs.length || !ok ? "FAIL" : "ok  "), route.padEnd(36), "text", String(text.length).padStart(6), /Something went wrong/.test(text) ? "ERRORBOX" : "");
  errs.forEach(e => console.log("   ", e));
  if (errs.length || !ok) errors.push(route);
  w.close();
}
console.log(errors.length ? `FAILED ${errors.length}: ${errors.join(", ")}` : "ALL ROUTES OK");
process.exit(errors.length ? 1 : 0);

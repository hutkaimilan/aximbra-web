import axios from "axios";

// Railway-en a backend szolgálja ki a frontendet: üres változóval ugyanarról a címről kér.
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const errText = (e) => e?.response?.data?.detail || e?.message || "Ismeretlen hiba";

// --- az alvó Emergent-szerver ébresztése ------------------------------------------------------
// Az Emergent-előnézet használat nélkül elalszik, és csak a tulajdonos ébresztheti fel, bejelentkezve
// az Emergentbe (névtelenül az ébresztő-oldal a belépéshez irányít). Ha a szerver alszik (503 + wake_url),
// egy sáv jelenik meg egy gombbal, ami új lapon megnyitja az ébresztést; közben 5 másodpercenként megnézzük,
// fent van-e, és utána a félbemaradt kérések maguktól újrafutnak.
const WAKE_MAX_MS = 10 * 60 * 1000;
let waking = null;

function wakeBanner(url) {
  const bar = document.createElement("div");
  bar.setAttribute("role", "status");
  bar.style.cssText = "position:fixed;left:12px;right:12px;top:12px;z-index:9999;padding:12px 14px;border-radius:12px;"
    + "background:#1b2230;color:#eef0f3;border:1px solid #f5c518;font:600 14px/1.4 system-ui,sans-serif;"
    + "box-shadow:0 8px 30px rgba(0,0,0,.4);display:flex;gap:10px;align-items:center;flex-wrap:wrap";
  const text = document.createElement("span");
  text.style.flex = "1 1 220px";
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "Emergent ébresztése";
  link.style.cssText = "color:#1a1400;background:#f5c518;border-radius:8px;padding:8px 12px;text-decoration:none;font-weight:800";
  bar.append(text, link);
  document.body.appendChild(bar);
  return { set: (t) => { text.textContent = t; }, remove: () => bar.remove() };
}

function wake(url) {
  if (waking) return waking;
  waking = (async () => {
    const bar = wakeBanner(url);
    const t0 = Date.now();
    try {
      while (Date.now() - t0 < WAKE_MAX_MS) {
        const sec = Math.round((Date.now() - t0) / 1000);
        bar.set(`Az Emergent-szerver alszik. Nyomd meg a gombot (az Emergentbe belépve ébreszti fel), és gyere `
          + `vissza: 1–2 perc múlva magától betölt. Várok… ${sec} mp`);
        await new Promise((r) => setTimeout(r, 5000));
        try {
          const r = await axios.get(`${API}/health`, { __noWake: true });
          if (r.data?.ok) return true;
        } catch { /* még alszik */ }
      }
      return false;
    } finally {
      bar.remove();
    }
  })().finally(() => { waking = null; });
  return waking;
}

axios.interceptors.response.use(undefined, async (err) => {
  const cfg = err.config || {};
  const url = err.response?.status === 503 && err.response?.data?.wake_url;
  if (url && !cfg.__noWake && !cfg.__retried && (await wake(url))) {
    return axios({ ...cfg, __retried: true });
  }
  throw err;
});

export const api = {
  state: (refresh) => axios.get(`${API}/state`, { params: refresh ? { refresh: 1 } : {} }).then((r) => r.data),
  slips: (params) => axios.get(`${API}/slips`, { params }).then((r) => r.data),
  check: (ids, stake) => axios.post(`${API}/check`, { ids, stake }).then((r) => r.data),
  team: (id) => axios.get(`${API}/team/${encodeURIComponent(id)}`).then((r) => r.data),
  accuracy: () => axios.get(`${API}/accuracy`).then((r) => r.data),
  log: () => axios.get(`${API}/log`).then((r) => r.data),
};

export { errText };

export const COMPS = [
  { key: "bl", name: "Bajnokok Ligája", short: "BL" },
  { key: "el", name: "Európa-liga", short: "EL" },
  { key: "pl", name: "Premier League", short: "PL" },
  { key: "laliga", name: "La Liga", short: "La Liga" },
  { key: "bundesliga", name: "Bundesliga", short: "Bundesliga" },
  { key: "portugal", name: "Portugál bajnokság", short: "Portugál" },
];

export const pct = (x, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d).replace(".", ",")}%`);
export const num = (x, d = 2) => (x == null ? "–" : Number(x).toFixed(d).replace(".", ","));
export const ft = (x) => (x == null ? "–" : `${Math.round(x).toLocaleString("hu-HU")} Ft`);
export const signedPct = (x) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(1).replace(".", ",")}%`);

const TZ = "Europe/Budapest";
export const kick = (iso) =>
  new Date(iso).toLocaleString("hu-HU", { timeZone: TZ, month: "short", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
export const dayLabel = (d) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString("hu-HU", { timeZone: TZ, month: "short", day: "numeric", weekday: "short" });
export const shortDate = (iso) => new Date(iso).toLocaleDateString("hu-HU", { timeZone: TZ, year: "2-digit", month: "2-digit", day: "2-digit" });

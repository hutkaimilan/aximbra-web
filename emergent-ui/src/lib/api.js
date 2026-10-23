import axios from "axios";

// Railway-en a backend szolgálja ki a frontendet: üres változóval ugyanarról a címről kér.
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const errText = (e) => e?.response?.data?.detail || e?.message || "Ismeretlen hiba";

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

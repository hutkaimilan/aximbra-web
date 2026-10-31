// A csevegő „ADATOK" része: a felhasználó szelvénye, a szelvény (és a kérdésben említett) meccsek teljes
// modell-elemzése, és a kiírt meccsek tömör listája. A modell csak ebből dolgozhat, böngészni nem tud.
const TZ = "Europe/Budapest";
const pc = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const n1 = (x) => (x == null ? "–" : Number(x).toFixed(1).replace(".", ","));
const n2 = (x) => (x == null ? "–" : Number(x).toFixed(2).replace(".", ","));
const when = (iso) => new Date(iso).toLocaleString("hu-HU", { timeZone: TZ, month: "short", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
const norm = (s) => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

const MAX_MENTIONED = 10;
const MAX_LIST = 120;

function index(state) {
  const out = new Map();
  for (const c of state?.competitions || []) for (const m of c.matches || []) out.set(m.id, { m, c });
  return out;
}

const odds = (m, key, line) => {
  const mk = m.markets?.find((x) => x.key === key && (line === undefined || x.line === line));
  return mk ? mk.outcomes.map((o) => `${o.label} ${n2(o.odds)}`).join(" / ") : null;
};

// Egy meccs teljes elemzése (a szelvény és a kérdésben említett meccsek).
export function matchDetail(m, c) {
  const a = m.analysis || {};
  const lines = [`${m.home} – ${m.away} (${c.name}, ${when(m.kickoff)})`];
  if (a.p_home != null) lines.push(`  Győzelmi esély (modell): ${m.home} ${pc(a.p_home)}, döntetlen ${pc(a.p_draw)}, ${m.away} ${pc(a.p_away)}`);
  if (a.xg_home != null) lines.push(`  Várható gól: ${n1(a.xg_home)} – ${n1(a.xg_away)} (összesen ${n1(a.xg_home + a.xg_away)}); mindkét csapat lő gólt ${pc(a.btts)}; 2,5 gól felett ${pc(a.over25)}`);
  if (a.ht?.p_home != null) lines.push(`  1. félidő: ${m.home} vezet ${pc(a.ht.p_home)}, döntetlen ${pc(a.ht.p_draw)}, ${m.away} vezet ${pc(a.ht.p_away)}`);
  if (a.corners != null || a.cards != null) lines.push(`  Várható szöglet ${n1(a.corners)}, várható lap ${n1(a.cards)}`);
  if (a.top_scores?.length) lines.push(`  Legvalószínűbb eredmények: ${a.top_scores.slice(0, 4).map(([s, p]) => `${s} (${pc(p)})`).join(", ")}`);
  for (const r of a.reasons || []) lines.push(`  ${r}`);
  const mk = [odds(m, "1x2"), odds(m, "dc"), odds(m, "ou", 2.5), odds(m, "btts"), odds(m, "dnb")].filter(Boolean);
  if (mk.length) lines.push(`  TippmixPro-szorzók: ${mk.join(" | ")}`);
  return lines.join("\n");
}

function matchLine(m, c) {
  const a = m.analysis || {};
  const x12 = m.markets?.find((x) => x.key === "1x2");
  const o = x12 ? x12.outcomes.map((x) => n2(x.odds)).join("/") : "–";
  return `${c.name} · ${when(m.kickoff)} · ${m.home} – ${m.away} · 1X2 ${o} · esély ${pc(a.p_home)}/${pc(a.p_draw)}/${pc(a.p_away)}`
    + ` · várható gól ${n1(a.xg_home)}–${n1(a.xg_away)} · mindkét csapat lő ${pc(a.btts)} · 2,5+ ${pc(a.over25)}`;
}

function mentioned(state, question) {
  const q = norm(question);
  if (!q) return [];
  const hits = [];
  for (const c of state?.competitions || []) for (const m of c.matches || []) {
    const words = [m.home, m.away].flatMap((t) => norm(t).split(/[^a-z0-9]+/)).filter((w) => w.length >= 4);
    if (words.some((w) => q.includes(w))) hits.push({ m, c });
  }
  return hits.slice(0, MAX_MENTIONED);
}

export function buildContext(state, slip, question) {
  const out = [];
  const idx = index(state);
  const { legs = [], stake, check } = slip || {};
  if (legs.length) {
    const info = Object.fromEntries((check?.legs || []).map((l) => [l.id, l]));
    out.push(`AZ OLDAL SZELVÉNYPANELJE (jobb oldali szelvény; tét ${stake} Ft, össz-szorzó ${n2(check?.odds)}, lehetséges nyeremény ${check?.payout ?? "–"} Ft):`);
    for (const l of legs) {
      const i = info[l.id] || {};
      out.push(`- ${i.match || l.match}: ${i.label || l.label} — ${i.market || l.market} @ ${n2(i.odds ?? l.odds)}`
        + (i.prob != null ? ` (modell-esély ${pc(i.prob)})` : ""));
    }
    for (const b of check?.bet_builder || []) out.push(`  Fogadásépítő-csoport (egy meccs tippjei), TippmixPro-szorzó: ${n2(b.odds)}`);
    if (check?.forbidden?.length) out.push("  FIGYELEM: a TippmixPro szerint a szelvényen kötéstiltott párosítás van.");
    for (const w of check?.warnings || []) out.push(`  Figyelmeztetés: ${w}`);
    out.push("");
  } else {
    out.push("AZ OLDAL SZELVÉNYPANELJE üres (ha a felhasználó képen vagy szövegben küldött szelvényt, azt értékeld).\n");
  }
  const detailed = new Set();
  const details = [];
  for (const l of legs) {
    const mid = (check?.legs || []).find((x) => x.id === l.id)?.match_id || l.match_id;
    const hit = idx.get(mid);
    if (hit && !detailed.has(mid)) { detailed.add(mid); details.push(matchDetail(hit.m, hit.c)); }
  }
  for (const { m, c } of mentioned(state, question)) {
    if (!detailed.has(m.id)) { detailed.add(m.id); details.push(matchDetail(m, c)); }
  }
  if (details.length) out.push("RÉSZLETES ELEMZÉS (a szelvénypanel és a beszélgetésben említett meccsek):", ...details, "");
  const all = [...idx.values()].sort((x, y) => new Date(x.m.kickoff) - new Date(y.m.kickoff)).slice(0, MAX_LIST);
  if (all.length) out.push(`KIÍRT MECCSEK (a következő ${all.length}, TippmixPro-szorzókkal és a modell becslésével):`, ...all.map(({ m, c }) => `- ${matchLine(m, c)}`));
  out.push("", `Mai dátum: ${new Date().toLocaleDateString("hu-HU", { timeZone: TZ, year: "numeric", month: "long", day: "numeric", weekday: "long" })}.`);
  return out.join("\n");
}

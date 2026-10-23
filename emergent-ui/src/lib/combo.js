// „Papírforma + gólok": a szerver „Győztesek" és „Gólok" szelvénye helyett egyetlen szelvény,
// meccsenként egy (Fogadásépítő-)csoporttal, úgy, ahogy egy rutinos fogadó rakná össze:
//
// - Ha van papírforma-favorit (TippmixPro-szorzója legfeljebb FAV_ODDS): ő nyer, és mellé gólszám,
//   ha a két csapat formája ÉS a várható gól egyértelműen egy irányba mutat.
// - Ha nincs: győztes nélkül a meccsre várható dolgok — gólszám (bármelyik vonalon), mindkét csapat
//   lő gólt, 2. félidős gólszám —, de csak az, amit a két csapat utolsó FORM_N meccse és a várható gól
//   is egyértelműen alátámaszt.
//
// Forrás: a várható gól és a győzelmi esély az Emergent-szerver modelljéből (/emergent/api/state), a
// forma az Emergent-szerver csapatoldaláról (/emergent/api/team), a vonalak a saját TippmixPro-olvasónk
// meccsoldal-lekéréséből (/api/match-markets: 0,5–7,5 gólvonal, félidők), a szorzó és a kötéstiltás a
// TippmixPro-tól (/api/check). Az esély csak a szelvény összerakásához (rangsor) és tájékoztatásnak kell:
// a tippet a forma és a várható gól választja ki.
import axios from "axios";
import { api } from "./api";

const own = {
  matchMarkets: (id) => axios.get("/api/match-markets", { params: { id } }).then((r) => r.data),
  check: (ids, stake) => axios.post("/api/check", { ids, stake }).then((r) => r.data),
};

export const COMBO_NAME = "Papírforma + gólok";
const DESC = "Papírforma-favoritnál (szorzó ≤ 1,70) ő nyer, mellé gólszám, ha egyértelmű. Favorit nélkül győztes "
  + "nélkül: gólszám, mindkét csapat lő gólt, 2. félidős gólok — csak amit a két csapat utolsó 10 meccse és a "
  + "várható gól egyértelműen mutat.";

const FAV_ODDS = 1.7;
const FORM_N = 10;
const MIN_FORM = 6;          // ennél kevesebb ismert meccsnél nem mondunk semmit a formából
const MAX_ANALYSED = 24;     // ennyi meccset elemzünk ablakonként (kezdés szerint)
const CONCURRENCY = 6;
const CANDIDATES = 8;
const MAX_MATCHES = 6;
const MIN_GROUP_ODDS = 1.1;
const MIN_PICK_ODDS = 1.25;  // ennél kisebb szorzójú tipp (pl. „kevesebb mint 4,5" 1,16-on) alig ad hozzá
const AUTO_MIN_PROB = 0.6;
const FIRST_HALF_SHARE = 0.45;  // a gólok kb. 45%-a esik az 1. félidőre
const TZ = "Europe/Budapest";

// Egyértelműségi küszöbök (gól):
const OVER_MARGIN = 0.4;     // „több mint L": a várható gól (modell és forma közül a kisebb) ≥ L + 0,4
const UNDER_MARGIN = 0.6;    // „kevesebb mint L": a várható gól (a nagyobbik) ≤ L − 0,6
const OVER_SHARE = 0.6;      // és mindkét csapat utolsó meccseinek legalább 60%-án L fölött volt
const UNDER_SHARE = 0.7;
const H2_MARGIN = 0.3;

const dayOf = (iso) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: TZ });
const addDays = (d, n) => {
  const t = new Date(`${d}T12:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
};
const fmt = (x) => x.toFixed(1).replace(".", ",");
const prod = (xs) => xs.reduce((p, x) => p * x, 1);

async function pool(items, n, fn) {
  const out = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) {
      const k = i++;
      try { out[k] = await fn(items[k]); } catch { out[k] = null; }
    }
  }));
  return out;
}

// --- forma -----------------------------------------------------------------------------------

const teamCache = new Map();
function teamForm(id) {
  if (!id) return Promise.resolve(null);
  if (!teamCache.has(id)) {
    teamCache.set(id, api.team(id).then(formOf).catch((e) => { teamCache.delete(id); throw e; }));
  }
  return teamCache.get(id);
}

// Az utolsó FORM_N meccs a csapat szemszögéből: lőtt, kapott, és a 2. félidő gólszáma (ha ismert).
export function formOf(data) {
  const id = String(data.id);
  const games = [];
  for (const r of data.results || []) {
    const sc = String(r.score || "").split(/[–-]/).map(Number);
    if (sc.length !== 2 || sc.some((x) => !Number.isFinite(x))) continue;
    const home = String(r.home_id) === id;
    const ht = Array.isArray(r.ht) && r.ht.length === 2 ? r.ht.map(Number) : null;
    games.push({ gf: home ? sc[0] : sc[1], ga: home ? sc[1] : sc[0],
      h2: ht && ht.every(Number.isFinite) ? sc[0] + sc[1] - ht[0] - ht[1] : null });
    if (games.length >= FORM_N) break;
  }
  if (games.length < MIN_FORM) return null;
  const avg = (f) => games.reduce((s, g) => s + f(g), 0) / games.length;
  const h2 = games.filter((g) => g.h2 != null);
  return {
    n: games.length, gf: avg((g) => g.gf), ga: avg((g) => g.ga),
    over: (l) => games.filter((g) => g.gf + g.ga > l).length,
    under: (l) => games.filter((g) => g.gf + g.ga < l).length,
    scored: games.filter((g) => g.gf > 0).length, conceded: games.filter((g) => g.ga > 0).length,
    h2n: h2.length, h2avg: h2.length ? h2.reduce((s, g) => s + g.h2, 0) / h2.length : null,
    h2over: (l) => h2.filter((g) => g.h2 > l).length,
  };
}

// --- modell: a két félidő gólja külön Poisson, a meccs várható góljaiból ------------------------

const MAXG = 7;
function poisson(lam) {
  const p = [Math.exp(-lam)];
  for (let k = 1; k <= MAXG; k++) p.push((p[k - 1] * lam) / k);
  return p;
}
// cond(h1, a1, h2, a2) együttes esélye
export function jointProb(xgH, xgA, conds) {
  const h1 = poisson(xgH * FIRST_HALF_SHARE), a1 = poisson(xgA * FIRST_HALF_SHARE);
  const h2 = poisson(xgH * (1 - FIRST_HALF_SHARE)), a2 = poisson(xgA * (1 - FIRST_HALF_SHARE));
  let s = 0;
  for (let i = 0; i <= MAXG; i++) for (let j = 0; j <= MAXG; j++) {
    const p1 = h1[i] * a1[j];
    for (let k = 0; k <= MAXG; k++) for (let l = 0; l <= MAXG; l++) {
      if (conds.every((c) => c(i, j, k, l))) s += p1 * h2[k] * a2[l];
    }
  }
  return s;
}

const COND = {
  win1: (i, j, k, l) => i + k > j + l,
  win2: (i, j, k, l) => i + k < j + l,
  over: (L) => (i, j, k, l) => i + j + k + l > L,
  under: (L) => (i, j, k, l) => i + j + k + l < L,
  bttsY: (i, j, k, l) => i + k > 0 && j + l > 0,
  bttsN: (i, j, k, l) => i + k === 0 || j + l === 0,
  h2over: (L) => (i, j, k, l) => k + l > L,
};

// --- tippválasztás --------------------------------------------------------------------------

const outcome = (markets, key, line, pick) => {
  const mk = markets.find((m) => m.key === key && (line == null || m.line === line));
  const o = mk?.outcomes.find((x) => x.pick === pick);
  return mk && o && o.odds >= MIN_PICK_ODDS ? { mk, o } : null;
};
const linesOf = (markets, key) => [...new Set(markets.filter((m) => m.key === key).map((m) => m.line))].sort((a, b) => a - b);

// Gólszám a forma és a várható gól alapján (vagy null). Több: a legmagasabb egyértelmű vonal; kevesebb: a legalacsonyabb.
function goalLine(markets, xgTot, formTot, fh, fa) {
  const lines = linesOf(markets, "ou");
  const lo = Math.min(xgTot, formTot), hi = Math.max(xgTot, formTot);
  for (const L of [...lines].reverse()) {
    if (lo >= L + OVER_MARGIN && fh.over(L) >= OVER_SHARE * fh.n && fa.over(L) >= OVER_SHARE * fa.n) {
      const hit = outcome(markets, "ou", L, "Több");
      if (hit) return { ...hit, cond: COND.over(L), why: `várható gól ${fmt(xgTot)} (modell) / ${fmt(formTot)} (forma); `
        + `${L + 0.5}+ gól: ${fh.over(L)}/${fh.n} és ${fa.over(L)}/${fa.n} meccsükön` };
    }
  }
  for (const L of lines) {
    if (hi <= L - UNDER_MARGIN && fh.under(L) >= UNDER_SHARE * fh.n && fa.under(L) >= UNDER_SHARE * fa.n) {
      const hit = outcome(markets, "ou", L, "Kevesebb");
      if (hit) return { ...hit, cond: COND.under(L), why: `várható gól ${fmt(xgTot)} (modell) / ${fmt(formTot)} (forma); `
        + `legfeljebb ${L - 0.5} gól: ${fh.under(L)}/${fh.n} és ${fa.under(L)}/${fa.n} meccsükön` };
    }
  }
  return null;
}

function btts(markets, a, fh, fa) {
  if (fh.scored >= 0.7 * fh.n && fa.scored >= 0.7 * fa.n && fh.conceded >= 0.6 * fh.n && fa.conceded >= 0.6 * fa.n
      && a.xg_home >= 1.1 && a.xg_away >= 1.0) {
    const hit = outcome(markets, "btts", null, "Igen");
    if (hit) return { ...hit, cond: COND.bttsY, why: `gólt szerzett ${fh.scored}/${fh.n} és ${fa.scored}/${fa.n}, `
      + `kapott ${fh.conceded}/${fh.n} és ${fa.conceded}/${fa.n} meccsén` };
  }
  const weak = (f, xg) => f.scored <= 0.5 * f.n && xg <= 0.9;
  if (weak(fh, a.xg_home) || weak(fa, a.xg_away)) {
    const hit = outcome(markets, "btts", null, "Nem");
    const [f, nm] = weak(fh, a.xg_home) ? [fh, "a hazai"] : [fa, "a vendég"];
    if (hit) return { ...hit, cond: COND.bttsN, why: `${nm} csak ${f.scored}/${f.n} meccsén lőtt gólt` };
  }
  return null;
}

function secondHalf(markets, xgTot, fh, fa) {
  if (fh.h2avg == null || fa.h2avg == null || fh.h2n < MIN_FORM || fa.h2n < MIN_FORM) return null;
  const exp = Math.min(xgTot * (1 - FIRST_HALF_SHARE), (fh.h2avg + fa.h2avg) / 2);
  for (const L of [...linesOf(markets, "2hou")].reverse()) {
    if (exp >= L + H2_MARGIN && fh.h2over(L) >= OVER_SHARE * fh.h2n && fa.h2over(L) >= OVER_SHARE * fa.h2n) {
      const hit = outcome(markets, "2hou", L, "Több");
      if (hit) return { ...hit, cond: COND.h2over(L), why: `2. félidőben ${L + 0.5}+ gól: ${fh.h2over(L)}/${fh.h2n} és `
        + `${fa.h2over(L)}/${fa.h2n} meccsükön` };
    }
  }
  return null;
}

const leg = ({ mk, o, why }) => ({ id: o.id, label: o.label, market: why ? `${mk.name} · ${why}` : mk.name, odds: o.odds,
  market_key: mk.key, pick: o.pick, line: mk.line });

// Egy meccs csoportja (szorzó nélkül), vagy null. m: az Emergent-állapot meccse, mm: a meccsoldal piacai.
export function matchGroup(m, compName, mm, fh, fa) {
  const a = m.analysis;
  if (!a || a.xg_home == null || a.xg_away == null) return null;
  const markets = [...m.markets.filter((x) => x.key === "1x2" || x.key === "btts"), ...(mm?.markets || [])];
  const xgTot = a.xg_home + a.xg_away;
  const picks = [];
  const x12 = m.markets.find((x) => x.key === "1x2");
  const favOut = x12?.outcomes.filter((o) => o.pick !== "X").sort((p, q) => p.odds - q.odds)[0];
  const isFav = favOut && favOut.odds <= FAV_ODDS;
  if (isFav) {
    picks.push({ mk: x12, o: favOut, cond: favOut.pick === "1" ? COND.win1 : COND.win2,
      why: `papírforma: ${favOut.label} szorzója ${favOut.odds.toFixed(2).replace(".", ",")}` });
  }
  if (fh && fa) {
    const formTot = (fh.gf + fa.ga) / 2 + (fa.gf + fh.ga) / 2;
    const gl = goalLine(markets, xgTot, formTot, fh, fa);
    if (gl) picks.push(gl);
    if (!isFav) {
      const bt = btts(markets, a, fh, fa);
      if (bt && !(bt.o.pick === "Nem" && gl?.o.pick === "Több" && gl.mk.line >= 2.5)) picks.push(bt);
      if (!(gl && gl.o.pick === "Kevesebb")) {
        const h2 = secondHalf(markets, xgTot, fh, fa);
        if (h2) picks.push(h2);
      }
    }
  }
  if (!picks.length) return null;
  // Esély (rangsorhoz): a két félidő Poisson-modelljéből; favoritnál a szerver győzelmi esélyéhez igazítva.
  let prob = jointProb(a.xg_home, a.xg_away, picks.map((p) => p.cond));
  if (isFav) {
    const pWin = favOut.pick === "1" ? a.p_home : a.p_away;
    const pWinModel = jointProb(a.xg_home, a.xg_away, [picks[0].cond]);
    if (pWinModel > 0 && pWin) prob = Math.min(pWin, prob * (pWin / pWinModel));
  }
  return {
    match: `${m.home} – ${m.away}`, match_id: m.id, competition: compName, kickoff: m.kickoff,
    builder: picks.length > 1, odds: picks.length === 1 ? picks[0].o.odds : null, prob, home: m.home, away: m.away,
    picks: picks.map(leg),
  };
}

// --- szelvény ---------------------------------------------------------------------------------

const teamsOf = (g) => [g.home, g.away];

function* combos(arr, k, start = 0, acc = []) {
  if (acc.length === k) { yield acc; return; }
  for (let i = start; i < arr.length; i++) yield* combos(arr, k, i + 1, [...acc, arr[i]]);
}

function choose(groups, target, floor) {
  if (!target && floor == null) {
    const out = [], used = new Set();
    for (const g of groups) {
      if (teamsOf(g).some((t) => used.has(t))) continue;
      out.push(g); teamsOf(g).forEach((t) => used.add(t));
      if (out.length >= 3) break;
    }
    return out.length ? out : null;
  }
  let best = null, bestKey = null;
  for (let k = 1; k <= Math.min(MAX_MATCHES, groups.length); k++) {
    for (const c of combos(groups, k)) {
      const ts = c.flatMap(teamsOf);
      if (new Set(ts).size !== ts.length) continue;
      const odds = prod(c.map((g) => g.odds)), prob = prod(c.map((g) => g.prob));
      if (floor != null && prob < floor) continue;
      let key;
      if (target) {
        if (odds < target) continue;
        key = [prob, -odds];
      } else key = [odds, prob];
      if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) { best = c; bestKey = key; }
    }
  }
  return best;
}

/**
 * Az összevont szelvény a szelvénykészítő beállításaival. Visszaad: { version, notes }.
 */
export async function buildCombo({ state, window, comps, stake, target, mode }) {
  const notes = [];
  if (!window?.start) return { version: null, notes };
  const end = addDays(window.start, window.days || 1);
  const now = Date.now();
  const matches = [];
  for (const c of state.competitions || []) {
    if (!comps.includes(c.key)) continue;
    for (const m of c.matches || []) {
      const d = dayOf(m.kickoff);
      if (d < window.start || d >= end || new Date(m.kickoff).getTime() <= now || !m.analysis) continue;
      matches.push({ m, c });
    }
  }
  matches.sort((x, y) => new Date(x.m.kickoff) - new Date(y.m.kickoff));
  if (matches.length > MAX_ANALYSED) {
    notes.push(`A „${COMBO_NAME}” szelvényhez az ablak első ${MAX_ANALYSED} meccsét elemeztem (${matches.length}-ből).`);
    matches.length = MAX_ANALYSED;
  }
  if (!matches.length) {
    notes.push(`A „${COMBO_NAME}” szelvényhez nincs meccs a kiválasztott napokon.`);
    return { version: null, notes };
  }
  const analysed = await pool(matches, CONCURRENCY, async ({ m, c }) => {
    const [mm, fh, fa] = await Promise.all([
      own.matchMarkets(m.id).catch(() => null),
      teamForm(m.espn?.home).catch(() => null),
      teamForm(m.espn?.away).catch(() => null),
    ]);
    return matchGroup(m, c.name, mm, fh, fa);
  });
  const groups = analysed.filter(Boolean).sort((x, y) => y.prob - x.prob);
  const cands = [], used = new Set();
  for (const g of groups) {
    if (teamsOf(g).some((t) => used.has(t))) continue;
    cands.push(g); teamsOf(g).forEach((t) => used.add(t));
    if (cands.length >= CANDIDATES) break;
  }
  if (!cands.length) {
    notes.push(`A „${COMBO_NAME}” szelvényhez egyik meccsen sincs egyértelmű favorit vagy egyértelmű gól-tipp.`);
    return { version: null, notes };
  }
  // Fogadásépítő-csoport szorzója és kötéstiltása a TippmixPro-tól; tiltott csoport kimarad.
  const priced = (await pool(cands, CONCURRENCY, async (g) => {
    if (!g.builder) return g;
    const r = await own.check(g.picks.map((p) => p.id), stake);
    if (r.forbidden?.length || r.missing?.length) return null;
    const bb = r.bet_builder?.[0]?.odds;
    return bb ? { ...g, odds: bb } : null;
  })).filter((g) => g && g.odds >= MIN_GROUP_ODDS).sort((x, y) => y.prob - x.prob);
  if (!priced.length) {
    notes.push(`A „${COMBO_NAME}” csoportjait a TippmixPro most nem tudta beárazni.`);
    return { version: null, notes };
  }

  const floor = mode === "auto" ? (target ? null : AUTO_MIN_PROB) : mode === "0" ? null : Number(mode) / 100;
  let pl = priced;
  for (let attempt = 0; attempt < 4 && pl.length; attempt++) {
    let pick = choose(pl, target, floor);
    let low = false;
    if (!pick) {
      pick = [pl[0]];
      low = true;
      const fl = floor != null ? `${Math.round(floor * 100)}%-os` : "";
      notes.push(target
        ? `A „${COMBO_NAME}” szelvénnyel a ${String(target).replace(".", ",")}-es célszorzó ${fl ? `${fl} esély mellett ` : ""}nem érhető el; a legesélyesebb csoportot mutatom.`
        : `A „${COMBO_NAME}” szelvényből nincs ${fl} esélyű; a legesélyesebb csoportot mutatom (${(pl[0].prob * 100).toFixed(0)}%).`);
    }
    pick = [...pick].sort((x, y) => y.prob - x.prob);
    let chk;
    try {
      chk = await own.check(pick.flatMap((g) => g.picks.map((p) => p.id)), stake);
    } catch {
      notes.push(`A „${COMBO_NAME}” szelvényt a TippmixPro most nem tudta ellenőrizni.`);
      return { version: null, notes: [...new Set(notes)] };
    }
    if (chk.forbidden?.length) {
      const bad = new Set(chk.forbidden.flat());
      const owner = pick.filter((g) => g.picks.some((p) => bad.has(p.id)));
      const drop = (owner.length ? owner : pick).reduce((x, y) => (x.prob <= y.prob ? x : y));
      pl = pl.filter((g) => g.match_id !== drop.match_id);
      continue;
    }
    const bb = new Map((chk.bet_builder || []).map((b) => [b.ids.join(","), b.odds]));
    pick = pick.map((g) => ({ ...g, odds: bb.get(g.picks.map((p) => p.id).join(",")) ?? g.odds }));
    const prob = prod(pick.map((g) => g.prob));
    const odds = chk.odds || prod(pick.map((g) => g.odds));
    const st = Math.max(Number(stake) || 0, chk.min_stake || 100);
    return {
      version: {
        name: COMBO_NAME, kind: "win_goals", desc: DESC, groups: pick, odds, prob, ev: prob * odds - 1,
        stake: st, min_stake: chk.min_stake, payout: Math.floor(st * odds), low_prob: low || prob < AUTO_MIN_PROB,
        checked: true, warnings: chk.warnings || [],
      },
      notes: [...new Set(notes)],
    };
  }
  notes.push(`A „${COMBO_NAME}” szelvényhez nem találtam köthető párosítást.`);
  return { version: null, notes: [...new Set(notes)] };
}

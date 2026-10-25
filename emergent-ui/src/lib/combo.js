// „Papírforma szelvény": a szerver „Győztesek" és „Gólok" szelvénye helyett több szelvény, meccsenként
// egy (Fogadásépítő-)csoporttal, úgy, ahogy egy rutinos fogadó rakná össze:
//
// - Ha van papírforma-favorit (TippmixPro-szorzója legfeljebb FAV_ODDS): ő nyer.
// - Mellé (favorit nélkül győztes helyett) minden olyan esemény, amit a két csapat utolsó FORM_N meccse
//   ÉS a várható érték is egyértelműen alátámaszt: gólszám bármelyik vonalon, mindkét csapat lő gólt,
//   1. és 2. félidő gólszáma, szöglet, lap (az utóbbi kettőt a TippmixPro csak a meccsnap körül írja ki).
// - Egymásnak ellentmondó tipp nem kerülhet egy csoportba (a modell szerint együtt sokkal ritkábbak).
// - Több szelvény készül, mindegyik más meccsekből.
//
// Forrás: várható gól, szöglet, lap és győzelmi esély az Emergent-szerver modelljéből (/emergent/api/state),
// forma az Emergent-szerver csapatoldaláról (/emergent/api/team: eredmény, félidő, szöglet, lap meccsenként),
// a vonalak a saját TippmixPro-olvasónk meccsoldal-lekéréséből (/api/match-markets), a szorzó és a kötéstiltás
// a TippmixPro-tól (/api/check). A tippet a forma és a várható érték választja; az esély csak a szelvények
// összerakásához (rangsor) és tájékoztatásnak kell.
import axios from "axios";
import { api } from "./api";

const own = {
  matchMarkets: (id) => axios.get("/api/match-markets", { params: { id } }).then((r) => r.data),
  check: (ids, stake) => axios.post("/api/check", { ids, stake }).then((r) => r.data),
};

export const COMBO_NAME = "Papírforma szelvény";
const DESC = "Alap: a papírforma-favorit győzelme (szorzó ≤ 1,70), a gólszám és a „mindkét csapat lő gólt\", ha a két "
  + "csapat utolsó 10 meccse és a várható gól egyértelmű. Félidő, szöglet, lap csak akkor, ha szinte biztos.";

const FAV_ODDS = 1.7;
const FORM_N = 10;
const MIN_FORM = 6;          // ennél kevesebb ismert meccsnél nem mondunk semmit a formából
const MAX_ANALYSED = 30;     // ennyi meccset elemzünk ablakonként (kezdés szerint)
const CONCURRENCY = 6;
const CANDIDATES = 16;
const SLIPS = 4;             // ennyi szelvény, mindegyik más tippekkel
const MIN_MATCHES = 3;       // egy szelvényen legalább ennyi meccs (ha van ennyi egyértelmű)
const MAX_MATCHES = 6;
const MAX_SHARED = 1;        // két szelvénynek legfeljebb ennyi közös meccse lehet (ha a meccsek elfogynak)
const MAX_PICKS = 4;         // egy meccsen legfeljebb ennyi tipp
// A nem alapvető események (félidők, szöglet, lap) csak „szinte biztosan": a modell szerint legalább
// STRONG_PROB, és mindkét csapat utolsó meccseinek legalább STRONG_SHARE részén bejött. Meccsenként egy.
const STRONG_PROB = 0.85;
const STRONG_SHARE = 0.8;
const STRONG_MIN_ODDS = 1.1;
const MIN_GROUP_ODDS = 1.1;
const MIN_PICK_ODDS = 1.25;  // ennél kisebb szorzójú tipp (pl. „kevesebb mint 4,5" 1,16-on) alig ad hozzá
const AUTO_MIN_PROB = 0.6;
const FIRST_HALF_SHARE = 0.45;  // a gólok kb. 45%-a esik az 1. félidőre
const CONFLICT = 0.6;        // ha két tipp együtt a modell szerint ennyiszer ritkább, mint külön, nem kerülnek együtt
const DISPERSION = { corners: 59.7, cards: 18.3 };  // negatív binomiális szóródás (a saját visszamérésünkből)
const TZ = "Europe/Budapest";

// Egyértelműségi szabály piaconként: „több mint L", ha a várható érték (modell és forma közül a kisebb)
// legalább L + over, és mindkét csapat utolsó meccseinek legalább 60%-án L fölött volt; „kevesebb mint L",
// ha a nagyobbik legfeljebb L − under, és mindkét csapat meccseinek legalább 70%-án L alatt.
const RULES = {
  ou: { over: 0.4, under: 0.6, what: "gól" },
  htou: { over: 0.3, under: 0.5, what: "gól az 1. félidőben" },
  "2hou": { over: 0.3, under: 0.5, what: "gól a 2. félidőben" },
  corners: { over: 1.0, under: 1.5, what: "szöglet" },
  cards: { over: 0.7, under: 1.0, what: "lap" },
};
const OVER_SHARE = 0.6;
const UNDER_SHARE = 0.7;

const dayOf = (iso) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: TZ });
const addDays = (d, n) => {
  const t = new Date(`${d}T12:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
};
const fmt = (x) => x.toFixed(1).replace(".", ",");
const prod = (xs) => xs.reduce((p, x) => p * x, 1);
const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;
const numPair = (v) => (Array.isArray(v) && v.length === 2 && v.every((x) => x != null && Number.isFinite(Number(x)))
  ? v.map(Number) : null);

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

// Az utolsó FORM_N meccs a csapat szemszögéből, meccsenkénti összesítőkkel (ami ismeretlen, az null).
export function formOf(data) {
  const id = String(data.id);
  const games = [];
  for (const r of data.results || []) {
    const sc = numPair(String(r.score || "").split(/[–-]/));
    if (!sc) continue;
    const home = String(r.home_id) === id;
    const ht = numPair(r.ht), co = numPair(r.corners), ca = numPair(r.cards);
    games.push({
      gf: home ? sc[0] : sc[1], ga: home ? sc[1] : sc[0], ou: sc[0] + sc[1],
      htou: ht ? ht[0] + ht[1] : null, "2hou": ht ? sc[0] + sc[1] - ht[0] - ht[1] : null,
      corners: co ? co[0] + co[1] : null, cards: ca ? ca[0] + ca[1] : null,
    });
    if (games.length >= FORM_N) break;
  }
  if (games.length < MIN_FORM) return null;
  return {
    n: games.length, gf: mean(games.map((g) => g.gf)), ga: mean(games.map((g) => g.ga)),
    scored: games.filter((g) => g.gf > 0).length, conceded: games.filter((g) => g.ga > 0).length,
    series: (key) => games.map((g) => g[key]).filter((x) => x != null),
  };
}

// --- modell -----------------------------------------------------------------------------------

const MAXG = 7;
function poisson(lam) {
  const p = [Math.exp(-lam)];
  for (let k = 1; k <= MAXG; k++) p.push((p[k - 1] * lam) / k);
  return p;
}
// A gól-feltételek (h1, a1, h2, a2 → igaz/hamis) együttes esélye: a két félidő gólja külön Poisson.
export function jointProb(xgH, xgA, conds) {
  if (!conds.length) return 1;
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

// Szöglet/lap: negatív binomiális, a gólokétól függetlennek véve.
function nbOver(mu, r, line) {
  let cdf = 0, p = r / (r + mu);
  let pk = Math.pow(p, r);  // P(0)
  for (let k = 0; k <= Math.floor(line); k++) {
    cdf += pk;
    pk *= ((k + r) / (k + 1)) * (1 - p);
  }
  return Math.max(0, Math.min(1, 1 - cdf));
}

const GOAL_COND = {
  ou: (L, over) => (over ? (i, j, k, l) => i + j + k + l > L : (i, j, k, l) => i + j + k + l < L),
  htou: (L, over) => (over ? (i, j) => i + j > L : (i, j) => i + j < L),
  "2hou": (L, over) => (over ? (i, j, k, l) => k + l > L : (i, j, k, l) => k + l < L),
};
const WIN = { 1: (i, j, k, l) => i + k > j + l, 2: (i, j, k, l) => i + k < j + l };
const BTTS = { Igen: (i, j, k, l) => i + k > 0 && j + l > 0, Nem: (i, j, k, l) => i + k === 0 || j + l === 0 };

// --- tippválasztás --------------------------------------------------------------------------

const outcome = (markets, key, line, pick) => {
  const mk = markets.find((m) => m.key === key && (line == null || m.line === line));
  const o = mk?.outcomes.find((x) => x.pick === pick);
  return mk && o && o.odds >= MIN_PICK_ODDS ? { mk, o } : null;
};
const linesOf = (markets, key) => [...new Set(markets.filter((m) => m.key === key).map((m) => m.line))].sort((a, b) => a - b);
const cnt = (xs, f) => xs.filter(f).length;

// Egy vonalas piac (gólszám, félidők, szöglet, lap) egyértelmű tippje, vagy null.
// Több: a legmagasabb egyértelmű vonal; kevesebb: a legalacsonyabb (ott van a nagyobb szorzó).
function lineRule(markets, key, model, fh, fa, a) {
  const rule = RULES[key];
  const sh = fh.series(key), sa = fa.series(key);
  if (sh.length < MIN_FORM || sa.length < MIN_FORM) return null;
  const form = key === "ou" ? (fh.gf + fa.ga) / 2 + (fa.gf + fh.ga) / 2 : (mean(sh) + mean(sa)) / 2;
  const lo = model == null ? form : Math.min(model, form), hi = model == null ? form : Math.max(model, form);
  const exp = model == null ? `${fmt(form)} (forma)` : `${fmt(model)} (modell) / ${fmt(form)} (forma)`;
  const lines = linesOf(markets, key);
  const mk = (L, over) => {
    const hit = outcome(markets, key, L, over ? "Több" : "Kevesebb");
    if (!hit) return null;
    const share = over ? `${L + 0.5}+ ${rule.what}: ${cnt(sh, (x) => x > L)}/${sh.length} és ${cnt(sa, (x) => x > L)}/${sa.length}`
      : `legfeljebb ${L - 0.5} ${rule.what}: ${cnt(sh, (x) => x < L)}/${sh.length} és ${cnt(sa, (x) => x < L)}/${sa.length}`;
    const out = { ...hit, why: `várható ${exp}; ${share} meccsükön` };
    if (GOAL_COND[key]) out.cond = GOAL_COND[key](L, over);
    else {
      const mu = key === "corners" ? a.corners : a.cards;
      const p = nbOver(mu ?? form, DISPERSION[key], L);
      out.p = over ? p : 1 - p;
    }
    return out;
  };
  for (const L of [...lines].reverse()) {
    if (lo >= L + rule.over && cnt(sh, (x) => x > L) >= OVER_SHARE * sh.length && cnt(sa, (x) => x > L) >= OVER_SHARE * sa.length) {
      const hit = mk(L, true);
      if (hit) return hit;
    }
  }
  for (const L of lines) {
    if (hi <= L - rule.under && cnt(sh, (x) => x < L) >= UNDER_SHARE * sh.length && cnt(sa, (x) => x < L) >= UNDER_SHARE * sa.length) {
      const hit = mk(L, false);
      if (hit) return hit;
    }
  }
  return null;
}

// Nem alapvető esemény (félidő, szöglet, lap) csak szinte biztosan: a legnagyobb szorzójú ilyen vonal, vagy null.
function strongRule(markets, key, a, fh, fa) {
  const rule = RULES[key];
  const sh = fh.series(key), sa = fa.series(key);
  if (sh.length < MIN_FORM || sa.length < MIN_FORM) return null;
  const xgTot = a.xg_home + a.xg_away;
  let best = null;
  for (const L of linesOf(markets, key)) {
    for (const over of [true, false]) {
      const okH = cnt(sh, (x) => (over ? x > L : x < L)), okA = cnt(sa, (x) => (over ? x > L : x < L));
      if (okH < STRONG_SHARE * sh.length || okA < STRONG_SHARE * sa.length) continue;
      let p, cond = null;
      if (GOAL_COND[key]) {
        cond = GOAL_COND[key](L, over);
        p = jointProb(a.xg_home, a.xg_away, [cond]);
      } else {
        const mu = key === "corners" ? a.corners : a.cards;
        if (mu == null) continue;
        const po = nbOver(mu, DISPERSION[key], L);
        p = over ? po : 1 - po;
      }
      if (p < STRONG_PROB) continue;
      const mk = markets.find((m) => m.key === key && m.line === L);
      const o = mk?.outcomes.find((x) => x.pick === (over ? "Több" : "Kevesebb"));
      if (!o || o.odds < STRONG_MIN_ODDS) continue;
      if (best && o.odds <= best.o.odds) continue;
      const what = over ? `${L + 0.5}+ ${rule.what}` : `legfeljebb ${L - 0.5} ${rule.what}`;
      best = { mk, o, cond, p: cond ? null : p, prob: p,
        why: `szinte biztos: modell ${Math.round(p * 100)}%; ${what}: ${okH}/${sh.length} és ${okA}/${sa.length} meccsükön`
          + (key === "htou" || key === "2hou" ? ` (várható gól ${fmt(xgTot)})` : "") };
    }
  }
  return best;
}

function bttsRule(markets, a, fh, fa) {
  if (fh.scored >= 0.7 * fh.n && fa.scored >= 0.7 * fa.n && fh.conceded >= 0.6 * fh.n && fa.conceded >= 0.6 * fa.n
      && a.xg_home >= 1.1 && a.xg_away >= 1.0) {
    const hit = outcome(markets, "btts", null, "Igen");
    if (hit) return { ...hit, cond: BTTS.Igen, why: `gólt szerzett ${fh.scored}/${fh.n} és ${fa.scored}/${fa.n}, `
      + `kapott ${fh.conceded}/${fh.n} és ${fa.conceded}/${fa.n} meccsén; várható gól ${fmt(a.xg_home)} – ${fmt(a.xg_away)}` };
  }
  const weak = (f, xg) => f.scored <= 0.5 * f.n && xg <= 0.9;
  if (weak(fh, a.xg_home) || weak(fa, a.xg_away)) {
    const hit = outcome(markets, "btts", null, "Nem");
    const [f, nm, xg] = weak(fh, a.xg_home) ? [fh, "a hazai", a.xg_home] : [fa, "a vendég", a.xg_away];
    if (hit) return { ...hit, cond: BTTS.Nem, why: `${nm} csak ${f.scored}/${f.n} meccsén lőtt gólt; várható gólja ${fmt(xg)}` };
  }
  return null;
}

const leg = ({ mk, o, why }) => ({ id: o.id, label: o.label, market: why ? `${mk.name} · ${why}` : mk.name, odds: o.odds,
  market_key: mk.key, pick: o.pick, line: mk.line });

// A csoport esélye a modell szerint: gól-feltételek együtt, szöglet/lap függetlenül.
const modelProb = (a, picks) => jointProb(a.xg_home, a.xg_away, picks.filter((p) => p.cond).map((p) => p.cond))
  * prod(picks.filter((p) => p.p != null).map((p) => p.p));

// Egy meccs csoportja (szorzó nélkül), vagy null. m: az Emergent-állapot meccse, mm: a meccsoldal piacai.
export function matchGroup(m, compName, mm, fh, fa) {
  const a = m.analysis;
  if (!a || a.xg_home == null || a.xg_away == null) return null;
  const markets = [...m.markets.filter((x) => x.key === "1x2" || x.key === "btts"), ...(mm?.markets || [])];
  const xgTot = a.xg_home + a.xg_away;
  const x12 = m.markets.find((x) => x.key === "1x2");
  const favOut = x12?.outcomes.filter((o) => o.pick !== "X").sort((p, q) => p.odds - q.odds)[0];
  const isFav = favOut && favOut.odds <= FAV_ODDS;
  const cands = [];
  if (isFav) {
    cands.push({ mk: x12, o: favOut, cond: WIN[favOut.pick],
      why: `papírforma: ${favOut.label} szorzója ${favOut.odds.toFixed(2).replace(".", ",")}` });
  }
  if (fh && fa) {
    // alap: gólszám és „mindkét csapat lő gólt", ha egyértelmű
    cands.push(lineRule(markets, "ou", xgTot, fh, fa, a));
    cands.push(bttsRule(markets, a, fh, fa));
    // minden más csak szinte biztosan, csak alaptipp mellé, és meccsenként legfeljebb egy (a legnagyobb esélyű)
    const extra = ["htou", "2hou", "corners", "cards"].map((k) => strongRule(markets, k, a, fh, fa))
      .filter(Boolean).sort((x, y) => y.prob - x.prob)[0];
    if (extra && cands.some(Boolean)) cands.push(extra);
  }
  // Ellentmondó tipp kimarad: ha az eddigiekkel együtt a modell szerint jóval ritkább, mint külön.
  const picks = [];
  for (const c of cands) {
    if (!c || picks.length >= MAX_PICKS) continue;
    if (picks.length) {
      const before = modelProb(a, picks), alone = modelProb(a, [c]), together = modelProb(a, [...picks, c]);
      if (together < CONFLICT * before * alone) continue;
    }
    picks.push(c);
  }
  if (!picks.length) return null;
  // Esély (rangsorhoz): a modellből; favoritnál a szerver győzelmi esélyéhez igazítva.
  let prob = modelProb(a, picks);
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

// --- szelvények -------------------------------------------------------------------------------

const teamsOf = (g) => [g.home, g.away];

function* combos(arr, k, start = 0, acc = []) {
  if (acc.length === k) { yield acc; return; }
  for (let i = start; i < arr.length; i++) yield* combos(arr, k, i + 1, [...acc, arr[i]]);
}

// A legjobb kombináció legalább minK meccsből. Célszorzóval a legnagyobb esélyű, ami eléri; küszöbbel a legnagyobb
// szorzójú, ami a küszöb fölött marad; egyik nélkül a minK legesélyesebb. A korábbi szelvényekkel (prior)
// legfeljebb MAX_SHARED közös meccs lehet, hogy minden szelvény más tippekből álljon.
export function choose(groups, target, floor, minK, prior) {
  const okPrior = (c) => prior.every((ids) => c.filter((g) => ids.has(g.match_id)).length <= MAX_SHARED);
  let best = null, bestKey = null;
  const hi = target || floor != null ? Math.min(MAX_MATCHES, groups.length) : minK;
  for (let k = minK; k <= hi; k++) {
    for (const c of combos(groups, k)) {
      const ts = c.flatMap(teamsOf);
      if (new Set(ts).size !== ts.length || !okPrior(c)) continue;
      const odds = prod(c.map((g) => g.odds)), prob = prod(c.map((g) => g.prob));
      if (floor != null && prob < floor) continue;
      let key;
      if (target) {
        if (odds < target) continue;
        key = [prob, -odds];
      } else if (floor != null) key = [odds, prob];
      else key = [prob, odds];
      if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) { best = c; bestKey = key; }
    }
  }
  return best;
}

// Egy szelvény a csoportokból, a TippmixPro végső ellenőrzésével (tiltott párnál a gyengébb csoport kiesik).
async function oneSlip(groups, { target, floor, stake, minK, prior, idx, notes }) {
  let pl = groups;
  for (let attempt = 0; attempt < 4 && pl.length >= minK; attempt++) {
    let pick = choose(pl, target, floor, minK, prior);
    let low = false;
    if (!pick) {
      // A beállítást egyik legalább minK meccses kombináció sem éri el: a legesélyesebb minK csoport, narancssárgán.
      pick = choose(pl, null, null, minK, prior);
      if (!pick) return null;
      low = true;
      const fl = floor != null ? `${Math.round(floor * 100)}%-os` : "";
      notes.push(target
        ? `A ${minK} meccses papírforma-szelvények a ${String(target).replace(".", ",")}-es célszorzót ${fl ? `${fl} esély mellett ` : ""}nem érik el; a legesélyesebb csoportokból raktam össze őket (narancssárga címke).`
        : `${minK} meccsel ${fl ? `${fl} ` : ""}papírforma-szelvény nem jön ki; a legesélyesebb csoportokból raktam össze őket (narancssárga címke).`);
    }
    pick = [...pick].sort((x, y) => y.prob - x.prob);
    const chk = await own.check(pick.flatMap((g) => g.picks.map((p) => p.id)), stake);
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
      name: `${COMBO_NAME} ${idx}.`, kind: `combo-${idx}`, desc: DESC, groups: pick, odds, prob, ev: prob * odds - 1,
      stake: st, min_stake: chk.min_stake, payout: Math.floor(st * odds), low_prob: low || prob < AUTO_MIN_PROB,
      checked: true, warnings: chk.warnings || [],
    };
  }
  return null;
}

/**
 * Papírforma-szelvények a szelvénykészítő beállításaival. Visszaad: { versions, notes }.
 */
export async function buildCombo({ state, window, comps, stake, target, mode }) {
  const notes = [];
  const done = (versions) => ({ versions, notes: [...new Set(notes)] });
  if (!window?.start) return done([]);
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
    notes.push(`A „${COMBO_NAME}”-hez az ablak első ${MAX_ANALYSED} meccsét elemeztem (${matches.length}-ből).`);
    matches.length = MAX_ANALYSED;
  }
  if (!matches.length) {
    notes.push(`A „${COMBO_NAME}”-hez nincs meccs a kiválasztott napokon.`);
    return done([]);
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
    notes.push(`A „${COMBO_NAME}”-hez egyik meccsen sincs egyértelmű favorit vagy egyértelmű esemény.`);
    return done([]);
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
    return done([]);
  }

  const floor = mode === "auto" ? (target ? null : AUTO_MIN_PROB) : mode === "0" ? null : Number(mode) / 100;
  const minK = Math.min(MIN_MATCHES, priced.length);
  if (minK < MIN_MATCHES) notes.push(`Csak ${priced.length} meccsen van egyértelmű tipp, ezért a szelvények ${minK} meccsesek.`);
  const versions = [], prior = [];
  let rest = priced;   // előbb teljesen külön meccsekből; ha elfogynak, legfeljebb MAX_SHARED közös meccsel
  for (let k = 1; k <= SLIPS; k++) {
    const fromRest = rest.length >= minK;
    let v;
    try {
      v = await oneSlip(fromRest ? rest : priced, { target, floor, stake, minK, prior: fromRest ? [] : prior, idx: k, notes });
    } catch {
      notes.push(`A „${COMBO_NAME}” szelvényeit a TippmixPro most nem tudta ellenőrizni.`);
      break;
    }
    if (!v) break;
    versions.push(v);
    const ids = new Set(v.groups.map((g) => g.match_id));
    prior.push(ids);
    const usedTeams = new Set(v.groups.flatMap(teamsOf));
    rest = rest.filter((g) => !ids.has(g.match_id) && !teamsOf(g).some((t) => usedTeams.has(t)));
  }
  if (versions.length && versions.length < SLIPS) {
    notes.push(`${versions.length} papírforma-szelvény készült: a kiválasztott napokon nincs több meccs egyértelmű tippel. Válassz 2–3 napot a több szelvényhez.`);
  }
  return done(versions);
}

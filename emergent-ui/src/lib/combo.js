// „Győztes + gólok": a „Győztesek" és a „Gólok" szelvény helyett egyetlen szelvény.
// Meccsenként egy Fogadásépítő-csoport: a favorit győzelme + az a gólpiaci tipp (gólszám vagy
// „mindkét csapat szerez gólt"), amelyik a győzelemmel EGYÜTT a legvalószínűbb.
//
// Az együttes esély: a szerver győzelmi esélye × a gól-tipp feltételes esélye a győzelem mellett,
// a meccs Dixon–Coles-eredménymátrixából (a szerver várható góljaiból és ρ-jából). A két tipp nem
// független (ha a favorit nyer, több a gól), ezért nem szorozzuk össze egyszerűen a két esélyt.
// A csoport szorzóját és a kötéstiltást a TippmixPro adja a szerver /api/check végpontján keresztül.
import { api } from "./api";

const MAX_GOALS = 10;
const CANDIDATES = 8;        // ennyi legesélyesebb meccset árazunk be (egyenként egy /api/check)
const MAX_MATCHES = 6;
const MIN_GROUP_ODDS = 1.1;
const MIN_PICK_ODDS = 1.3;   // ennél kisebb szorzójú gól-tipp (pl. „Kevesebb, mint 4,5") alig ad hozzá
const AUTO_MIN_PROB = 0.6;
const TZ = "Europe/Budapest";

export const COMBO_NAME = "Győztes + gólok";
const DESC = "Meccsenként a favorit győzelme és a vele együtt legvalószínűbb gól-tipp, Fogadásépítőben.";

const dayOf = (iso) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: TZ });
const addDays = (d, n) => {
  const t = new Date(`${d}T12:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
};

function poisson(lam) {
  const p = [Math.exp(-lam)];
  for (let k = 1; k <= MAX_GOALS; k++) p.push((p[k - 1] * lam) / k);
  return p;
}

// Dixon–Coles: a 0–0, 1–0, 0–1, 1–1 eredmények korrekciója ρ-val.
export function scoreMatrix(lh, la, rho = 0) {
  const a = poisson(lh), b = poisson(la);
  return a.map((x, i) => b.map((y, j) => {
    let t = 1;
    if (i === 0 && j === 0) t = 1 - lh * la * rho;
    else if (i === 0 && j === 1) t = 1 + lh * rho;
    else if (i === 1 && j === 0) t = 1 + la * rho;
    else if (i === 1 && j === 1) t = 1 - rho;
    return x * y * Math.max(t, 0);
  }));
}

const mass = (m, f) => {
  let s = 0;
  for (let i = 0; i <= MAX_GOALS; i++) for (let j = 0; j <= MAX_GOALS; j++) if (f(i, j)) s += m[i][j];
  return s;
};

const WIN = { 1: (i, j) => i > j, 2: (i, j) => i < j };
function goalCond(key, pick, line) {
  if (key === "ou") return pick === "Több" ? (i, j) => i + j > line : (i, j) => i + j < line;
  if (key === "btts") return pick === "Igen" ? (i, j) => i > 0 && j > 0 : (i, j) => i === 0 || j === 0;
  return null;
}

const rhoOf = (a) => {
  for (const r of a.reasons || []) {
    const m = /ρ\s*=\s*(-?[0-9]+[.,][0-9]+)/.exec(r);
    if (m) return Number(m[1].replace(",", "."));
  }
  return 0;
};

const leg = (mk, o, prob) => ({ id: o.id, label: o.label, market: mk.name, odds: o.odds, prob,
  market_key: mk.key, pick: o.pick, line: mk.line });

// Egy meccs csoportja (még szorzó nélkül), vagy null.
export function matchGroup(m, compName) {
  const a = m.analysis;
  if (!a || a.xg_home == null || a.xg_away == null) return null;
  const x12 = m.markets.find((mk) => mk.key === "1x2");
  if (!x12) return null;
  const fav = a.p_home >= a.p_away ? "1" : "2";
  const winOut = x12.outcomes.find((o) => o.pick === fav);
  if (!winOut) return null;
  const pWin = fav === "1" ? a.p_home : a.p_away;
  const mat = scoreMatrix(a.xg_home, a.xg_away, rhoOf(a));
  const pWinModel = mass(mat, WIN[fav]);
  if (pWinModel <= 0) return null;
  let best = null;
  for (const mk of m.markets) {
    if (mk.key !== "ou" && mk.key !== "btts") continue;
    if (mk.key === "ou" && !(mk.line >= 1.5 && mk.line <= 3.5)) continue;
    for (const o of mk.outcomes) {
      const c = goalCond(mk.key, o.pick, mk.line);
      if (!c || o.odds < MIN_PICK_ODDS) continue;
      const cond = mass(mat, (i, j) => WIN[fav](i, j) && c(i, j)) / pWinModel;
      const joint = pWin * cond;
      if (!best || joint > best.prob) best = { mk, o, prob: joint };
    }
  }
  if (!best) return null;
  return {
    match: `${m.home} – ${m.away}`, match_id: m.id, competition: compName, kickoff: m.kickoff, builder: true,
    odds: null, prob: best.prob, home: m.home, away: m.away,
    picks: [leg(x12, winOut, pWin), leg(best.mk, best.o, best.prob)],
  };
}

const teamsOf = (g) => [g.home, g.away];
const prod = (xs) => xs.reduce((p, x) => p * x, 1);

function* combos(arr, k, start = 0, acc = []) {
  if (acc.length === k) { yield acc; return; }
  for (let i = start; i < arr.length; i++) yield* combos(arr, k, i + 1, [...acc, arr[i]]);
}

// A legjobb kombináció (a szerver szelvénykészítőjének szabályaival).
function choose(pool, target, floor) {
  if (!target && floor == null) {
    const out = [], used = new Set();
    for (const g of pool) {
      if (teamsOf(g).some((t) => used.has(t))) continue;
      out.push(g); teamsOf(g).forEach((t) => used.add(t));
      if (out.length >= 3) break;
    }
    return out.length ? out : null;
  }
  let best = null, bestKey = null;
  for (let k = 1; k <= Math.min(MAX_MATCHES, pool.length); k++) {
    for (const c of combos(pool, k)) {
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
 * Az összevont szelvény a szerver állapotából, a szelvénykészítő beállításaival.
 * Visszaad: { version, notes } — version null, ha nincs ilyen szelvény.
 */
export async function buildCombo({ state, window, comps, stake, target, mode }) {
  const notes = [];
  if (!window?.start) return { version: null, notes };
  const end = addDays(window.start, window.days || 1);
  const now = Date.now();
  const groups = [];
  for (const c of state.competitions || []) {
    if (!comps.includes(c.key)) continue;
    for (const m of c.matches || []) {
      const d = dayOf(m.kickoff);
      if (d < window.start || d >= end || new Date(m.kickoff).getTime() <= now) continue;
      const g = matchGroup(m, c.name);
      if (g) groups.push(g);
    }
  }
  groups.sort((x, y) => y.prob - x.prob);
  // csapatismétlés nélkül a legesélyesebb jelöltek (több napnál ugyanaz a csapat kétszer is játszhat)
  const cands = [], used = new Set();
  for (const g of groups) {
    if (teamsOf(g).some((t) => used.has(t))) continue;
    cands.push(g); teamsOf(g).forEach((t) => used.add(t));
    if (cands.length >= CANDIDATES) break;
  }
  if (!cands.length) {
    notes.push(`A „${COMBO_NAME}” szelvényhez nincs meccs a kiválasztott napokon.`);
    return { version: null, notes };
  }
  // A TippmixPro Fogadásépítő-szorzója csoportonként; tiltott pár kimarad.
  const priced = (await Promise.all(cands.map(async (g) => {
    try {
      const r = await api.check(g.picks.map((p) => p.id), stake);
      if (r.forbidden?.length || r.missing?.length) return null;
      const bb = r.bet_builder?.[0]?.odds;
      return bb ? { ...g, odds: bb } : null;
    } catch {
      return null;
    }
  }))).filter((g) => g && g.odds >= MIN_GROUP_ODDS).sort((x, y) => y.prob - x.prob);
  if (!priced.length) {
    notes.push(`A „${COMBO_NAME}” csoportjait a TippmixPro most nem tudta beárazni.`);
    return { version: null, notes };
  }

  const floor = mode === "auto" ? (target ? null : AUTO_MIN_PROB) : mode === "0" ? null : Number(mode) / 100;
  let pool = priced;
  for (let attempt = 0; attempt < 4 && pool.length; attempt++) {
    let pick = choose(pool, target, floor);
    let low = false;
    if (!pick) {
      // A küszöböt egyetlen kombináció sem éri el: a legesélyesebb csoport, narancssárga jelzéssel.
      pick = [pool[0]];
      low = true;
      const fl = floor != null ? `${Math.round(floor * 100)}%-os` : "";
      notes.push(target
        ? `A „${COMBO_NAME}” szelvénnyel a ${String(target).replace(".", ",")}-es célszorzó ${fl ? `${fl} esély mellett ` : ""}nem érhető el; a legesélyesebb csoportot mutatom.`
        : `A „${COMBO_NAME}” szelvényből nincs ${fl} esélyű; a legesélyesebb csoportot mutatom (${(pool[0].prob * 100).toFixed(0)}%).`);
    }
    pick = [...pick].sort((x, y) => y.prob - x.prob);
    let chk;
    try {
      chk = await api.check(pick.flatMap((g) => g.picks.map((p) => p.id)), stake);
    } catch {
      notes.push(`A „${COMBO_NAME}” szelvényt a TippmixPro most nem tudta ellenőrizni.`);
      return { version: null, notes };
    }
    if (chk.forbidden?.length) {
      const bad = new Set(chk.forbidden.flat());
      const owner = pick.filter((g) => g.picks.some((p) => bad.has(p.id)));
      const drop = (owner.length ? owner : pick).reduce((a, b) => (a.prob <= b.prob ? a : b));
      pool = pool.filter((g) => g.match_id !== drop.match_id);
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
  return { version: null, notes };
}

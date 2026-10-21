"use strict";
// Szelvényépítő — a szerver adataiból rajzol; minden külső szöveg textContent-tel kerül a DOM-ba.

const $ = (s) => document.querySelector(s);
const TZ = "Europe/Budapest";
const fmtDay = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, weekday: "long", month: "long", day: "numeric" });
const fmtTime = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtShort = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, month: "2-digit", day: "2-digit" });
const fmtIsoDay = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fmtDayLabel = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, month: "short", day: "numeric", weekday: "long" });
const odds = (x) => (x == null ? "–" : Number(x).toFixed(2).replace(".", ","));
const pct = (x, d = 1) => (x == null ? "–" : (x * 100).toFixed(d).replace(".", ",") + "%");
const signedPct = (x) => (x == null ? "" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1).replace(".", ",") + "%");
const ft = (n) => Math.round(n).toLocaleString("hu-HU") + " Ft";

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privát mód: nem baj */ } },
};

const S = {
  state: null,
  tab: store.get("tab", "best"),
  query: "",
  slip: store.get("slip", []),      // [{id, match, market, pick, odds, matchId}]
  stake: store.get("stake", 500),
  expanded: new Set(),
  check: null,
  bestBy: {},   // szelvénykészítő eredménye fülenként
};

async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opts });
  let data = null;
  try { data = await res.json(); } catch { /* üres válasz */ }
  if (res.status === 401) { showLogin(); throw new Error((data && data.error) || "Jelentkezz be."); }
  if (!res.ok) throw new Error((data && data.error) || `Hiba (${res.status})`);
  return data;
}

// --- belépés ---------------------------------------------------------------------------------
function showLogin() { $("#app").hidden = true; $("#login").hidden = false; $("#pw").focus(); }
async function boot() {
  try {
    const me = await api("/api/me");
    if (!me.authed) return showLogin();
    $("#logout").hidden = !!me.open;
  } catch (e) { $("#login-err").textContent = e.message; return showLogin(); }
  $("#login").hidden = true; $("#app").hidden = false;
  load(false);
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-err").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ password: $("#pw").value }) });
    $("#pw").value = "";
    boot();
  } catch (err) { $("#login-err").textContent = err.message; }
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {}); showLogin(); });

// --- adatok ----------------------------------------------------------------------------------
async function load(refresh) {
  $("#status").textContent = "Betöltés…";
  $("#refresh").disabled = true;
  try {
    S.state = await api("/api/state" + (refresh ? "?refresh=1" : ""));
    if (refresh) S.bestBy = {};
    renderAll();
    if (S.slip.length) runCheck();
  } catch (e) {
    $("#status").textContent = "";
    $("#content").replaceChildren(h("div", { class: "empty" }, "Nem sikerült betölteni: ", e.message));
  } finally { $("#refresh").disabled = false; }
}
$("#refresh").addEventListener("click", () => load(true));
setInterval(() => { if (!document.hidden && S.state) load(false); }, 3 * 60 * 1000);

function renderAll() { renderStatus(); renderTabs(); renderNotices(); renderContent(); renderSlip(); }

function renderStatus() {
  const st = S.state;
  const n = st.competitions.reduce((a, c) => a + c.matches.length, 0);
  const age = st.age < 60 ? "most" : `${Math.round(st.age / 60)} perce`;
  $("#status").textContent = `${n} meccs · frissítve ${age}${st.stale ? " (elavult)" : ""}`;
}

function renderTabs() {
  const tabs = [{ key: "best", name: "Szelvénykészítő" }, ...S.state.competitions.map((c) => ({ key: c.key, name: c.name, n: c.matches.length })),
    { key: "journal", name: "Napló", n: journal.list().length || null }, { key: "accuracy", name: "Mennyire pontos?" }];
  if (!tabs.some((t) => t.key === S.tab)) S.tab = "best";
  $("#tabs").replaceChildren(...tabs.map((t) => h("button", {
    class: "tab", role: "tab", "aria-selected": String(t.key === S.tab),
    onclick: () => { S.tab = t.key; store.set("tab", t.key); renderTabs(); renderContent(); window.scrollTo({ top: 0 }); },
  }, t.name, t.n != null ? h("span", { class: "n" }, t.n) : null)));
}

function renderNotices() {
  const st = S.state, out = [];
  for (const e of st.errors) out.push(e);
  for (const c of st.competitions) if (c.error) out.push(`${c.name}: ${c.error}`);
  if (!st.fair.enabled) out.push("Valós esély nélkül fut (nincs ODDS_API_KEY): a szorzókat és a kötéstiltást látod, de azt nem, melyik tipp ér többet a szorzójánál.");
  $("#notices").replaceChildren(...out.map((t) => h("div", { class: "notice" }, t)));
}

// --- meccslista ------------------------------------------------------------------------------
function matchesFor(compKey) {
  const q = S.query.trim().toLowerCase();
  const comps = compKey === "search" ? S.state.competitions : S.state.competitions.filter((c) => c.key === compKey);
  const out = [];
  for (const c of comps) for (const m of c.matches) {
    if (q && !(m.home.toLowerCase().includes(q) || m.away.toLowerCase().includes(q))) continue;
    out.push({ ...m, comp: c });
  }
  return out.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
}

function renderContent() {
  const root = $("#content");
  if (S.query.trim()) return renderList(root, matchesFor("search"), true);
  if (S.tab === "best") return renderBest(root);
  if (S.tab === "accuracy") return renderAccuracy(root);
  if (S.tab === "journal") return renderJournal(root);
  renderList(root, matchesFor(S.tab), false);
  const comp = S.state.competitions.find((c) => c.key === S.tab);
  if (comp && comp.matches.length) root.prepend(slipMaker({ key: comp.key, fixed: comp.key, auto: false }));
}

function renderList(root, list, showComp) {
  if (!list.length) {
    root.replaceChildren(h("div", { class: "empty" }, S.query ? "Nincs találat." : "Most nincs meccs ebben a sorozatban a TippmixPro kínálatában."));
    return;
  }
  const nodes = [];
  let lastDay = "";
  for (const m of list) {
    const day = fmtDay.format(new Date(m.kickoff));
    if (day !== lastDay) { nodes.push(h("div", { class: "day" }, day)); lastDay = day; }
    nodes.push(matchCard(m, showComp));
  }
  root.replaceChildren(...nodes);
}

function teamButton(name, id, logo, league) {
  return h("button", { class: "team-link", onclick: () => openTeam({ id, name, league }) },
    logo ? h("img", { src: logo, alt: "", loading: "lazy" }) : null, h("span", {}, name));
}

function matchCard(m, showComp) {
  const open = S.expanded.has(m.id);
  // Alapnézetben az 1X2; ha az éppen nincs kiírva (felfüggesztették), az első elérhető piac.
  const main = m.markets.filter((x) => x.key === "1x2");
  const mks = open ? m.markets : (main.length ? main : m.markets.slice(0, 1));
  const card = h("article", { class: "match" },
    h("div", { class: "match-head" },
      h("div", { class: "teams" },
        teamButton(m.home, m.espn.home, m.espn.home_logo, m.espn.league),
        teamButton(m.away, m.espn.away, m.espn.away_logo, m.espn.league)),
      h("div", { class: "meta" },
        h("span", {}, fmtTime.format(new Date(m.kickoff))),
        showComp ? h("span", { class: "chip" }, m.comp.name) : null,
        m.margin != null ? h("span", { class: "chip", title: "A TippmixPro árrése az 1X2 piacon" }, "árrés " + pct(m.margin)) : null)),
    analysisBlock(m),
    ...mks.map((mk) => h("div", { class: "mk" },
      h("div", { class: "mk-name" }, mk.name),
      h("div", { class: "odds-row" }, ...mk.outcomes.map((o) => oddButton(m, mk, o))))),
    m.markets.length > 1 ? h("button", {
      class: "more", onclick: () => { open ? S.expanded.delete(m.id) : S.expanded.add(m.id); card.replaceWith(matchCard(m, showComp)); },
    }, open ? "Kevesebb piac ▲" : `További piacok (${m.markets.length - 1}) ▼`) : null,
    open && m.sharp ? h("div", { class: "sharp" },
      `Várható gólok: ${m.sharp.xg[0].toFixed(2).replace(".", ",")} – ${m.sharp.xg[1].toFixed(2).replace(".", ",")} · `,
      `Legvalószínűbb: ${m.sharp.top_scores.map(([s, p]) => `${s} (${pct(p, 0)})`).join(", ")} · forrás: ${m.sharp.sources.join(", ")}`) : null);
  return card;
}

function analysisBlock(m) {
  const a = m.analysis;
  if (!a) return null;
  const n = (x) => x.toFixed(1).replace(".", ",");
  return h("div", { class: "insight" },
    h("div", {}, h("b", {}, "Ki nyer? "), `${m.home} ${pct(a.p_home, 0)} · döntetlen ${pct(a.p_draw, 0)} · ${m.away} ${pct(a.p_away, 0)}`),
    h("div", {}, h("b", {}, "Várható gólok: "), `${m.home} ${n(a.xg_home)}, ${m.away} ${n(a.xg_away)} (összesen ${n(a.xg_home + a.xg_away)})`),
    h("div", {}, h("b", {}, "Mindkét csapat lő gólt: "), pct(a.btts, 0), " · ", h("b", {}, "Legalább 3 gól: "), pct(a.over25, 0)),
    h("div", {}, h("b", {}, "Legvalószínűbb eredmény: "), a.top_scores.map(([sc, p]) => `${sc.replace("-", "–")} (${pct(p, 0)})`).join(", ")),
    a.corners_mu != null || a.cards_mu != null ? h("div", {},
      a.corners_mu != null ? [h("b", {}, "Várható szöglet: "), n(a.corners_mu)] : null,
      a.corners_mu != null && a.cards_mu != null ? " · " : null,
      a.cards_mu != null ? [h("b", {}, "Várható lap: "), n(a.cards_mu),
        h("span", { class: "src", title: "A becslés minden sárga és piros lapot egynek számol; a TippmixPro szabálya a második sárgánál eltérhet." }, " (minden lap 1-nek számít)")] : null) : null,
    h("div", { class: "src" }, "Forrás: ", a.source,
      a.corners_mu != null ? " · szöglet/lap: csapatátlagok (football-data.co.uk)" : ""));
}

function oddButton(m, mk, o) {
  const on = S.slip.some((s) => s.id === o.id);
  const label = o.label || o.pick;
  const title = o.prob != null
    ? `Valós esély ${pct(o.prob)} · fair szorzó ${odds(o.fair)} · min. szorzó ${odds(o.min_odds)} · EV ${signedPct(o.ev)}`
    : "Nincs valós esély ehhez a tipphez";
  return h("button", {
    class: "odd" + (o.value ? " value" : "") + (on ? " on" : ""), title, "aria-pressed": String(on),
    onclick: () => toggleLeg(m, mk, o),
  }, h("span", { class: "p" }, label), h("span", { class: "o" }, odds(o.odds)),
  o.ev != null ? h("span", { class: "ev" }, signedPct(o.ev)) : null);
}

$("#search").addEventListener("input", (e) => { S.query = e.target.value; renderContent(); });

// --- csapatoldal -----------------------------------------------------------------------------
async function openTeam({ id, name, league }) {
  const dlg = $("#team"), body = $("#team-body");
  body.replaceChildren(h("div", { class: "spinner" }, `${name} — eredmények betöltése…`));
  if (!dlg.open) dlg.showModal();
  const q = id ? `id=${encodeURIComponent(id)}` : `name=${encodeURIComponent(name)}&league=${encodeURIComponent(league)}`;
  try {
    const t = await api("/api/team?" + q);
    body.replaceChildren(
      h("div", { class: "team-top" }, t.logo ? h("img", { src: t.logo, alt: "" }) : null,
        h("div", {}, h("h2", {}, t.name || name),
          h("div", { class: "form", title: "Utolsó 5 meccs (legújabb balra)" }, ...[...t.form].map((r) => h("span", { class: "res " + (r === "G" ? "GY" : r) }, r === "G" ? "GY" : r))))),
      t.results.length ? h("div", { class: "results" }, ...t.results.map((r) => {
        const opp = r.is_home ? r.away : r.home;
        return h("div", { class: "result" },
          h("span", { class: "d" }, fmtShort.format(new Date(r.date))),
          h("div", {}, h("div", {}, (r.is_home ? "vs " : "@ ") + opp), h("div", { class: "c" }, r.competition)),
          h("span", { class: "sc" }, `${r.home_score}–${r.away_score}`),
          h("span", { class: "res " + r.result }, r.result));
      })) : h("p", { class: "muted" }, "Nincs lejátszott meccs az adatforrásban."),
      h("p", { class: "muted tiny" }, "Forrás: ESPN. GY = győzelem, D = döntetlen, V = vereség (rendes játékidő)."));
  } catch (e) {
    body.replaceChildren(h("p", { class: "err" }, e.message));
  }
}

// --- szelvény --------------------------------------------------------------------------------
function toggleLeg(m, mk, o) {
  const i = S.slip.findIndex((s) => s.id === o.id);
  if (i >= 0) S.slip.splice(i, 1);
  else {
    if (S.slip.length >= 20) { alert("Egy szelvényen legfeljebb 20 esemény lehet."); return; }
    S.slip.push(slipLeg(m, mk, o, m.comp || compOf(m.id)));
  }
  store.set("slip", S.slip);
  renderContent(); renderSlip(); runCheck();
}

// A szelvény egy tippje, a naplóhoz szükséges meccsazonosítással (sorozat, csapatok, kezdés, piac, vonal).
function slipLeg(m, mk, o, c) {
  return { id: o.id, match: `${m.home} – ${m.away}`, market: mk.name, pick: o.label || o.pick, odds: o.odds, matchId: m.id,
    home: m.home, away: m.away, kickoff: m.kickoff, comp: c ? c.key : null, mk: mk.key, rawPick: o.pick, line: mk.line };
}

function compOf(matchId) {
  return S.state.competitions.find((c) => c.matches.some((m) => m.id === matchId)) || null;
}

function addLegs(legs, opts = {}) {
  const idx = indexState();
  if (opts.replace) S.slip = [];   // kész szelvény: ez lesz a szelvény, nem keveredik a korábbival
  if (opts.stake) { S.stake = opts.stake; store.set("stake", S.stake); }
  for (const l of legs) {
    if (S.slip.some((s) => s.id === l.id)) continue;
    const hit = idx.get(l.id);
    if (hit) S.slip.push(slipLeg(hit.m, hit.mk, hit.o, hit.c));
  }
  store.set("slip", S.slip);
  renderContent(); renderSlip(); runCheck();
  $("#slip").classList.add("open");
}

function indexState() {
  const idx = new Map();
  for (const c of S.state.competitions) for (const m of c.matches) for (const mk of m.markets) for (const o of mk.outcomes) idx.set(o.id, { m, mk, o, c });
  return idx;
}

let checkTimer = null, checkSeq = 0;
function runCheck() {
  clearTimeout(checkTimer);
  if (!S.slip.length) { S.check = null; renderSlip(); return; }
  checkTimer = setTimeout(async () => {
    const seq = ++checkSeq;
    $("#slip-result").replaceChildren(h("div", { class: "muted" }, "Ellenőrzés a TippmixPro-nál…"));
    try {
      const r = await api("/api/check", { method: "POST", body: JSON.stringify({ ids: S.slip.map((s) => s.id), stake: Number(S.stake) || 0 }) });
      if (seq !== checkSeq) return;   // közben változott a szelvény
      if (r.missing.length) { S.slip = S.slip.filter((s) => !r.missing.includes(s.id)); store.set("slip", S.slip); }
      for (const l of r.legs) { const s = S.slip.find((x) => x.id === l.id); if (s) s.odds = l.odds; }
      S.check = r;
    } catch (e) {
      if (seq !== checkSeq) return;
      S.check = { error: e.message };
    }
    renderSlip();
  }, 450);
}

function renderSlip() {
  const forbidden = new Set((S.check && S.check.forbidden || []).flat());
  const builder = new Set((S.check && S.check.bet_builder || []).flatMap((b) => b.ids));
  $("#slip-count").textContent = S.slip.length;
  $("#slip-odds").textContent = S.check && S.check.odds ? odds(S.check.odds) : "";
  const bbOdds = new Map();
  for (const b of (S.check && S.check.bet_builder) || []) for (const id of b.ids) bbOdds.set(id, b.odds);
  const byMatch = new Map();
  for (const leg of S.slip) { if (!byMatch.has(leg.matchId)) byMatch.set(leg.matchId, []); byMatch.get(leg.matchId).push(leg); }
  const removeLeg = (id) => { S.slip = S.slip.filter((x) => x.id !== id); store.set("slip", S.slip); renderContent(); renderSlip(); runCheck(); };
  $("#slip-legs").replaceChildren(...[...byMatch.values()].map((legs) => {
    const isBB = legs.length > 1 && legs.every((l) => builder.has(l.id));
    const head = h("div", { class: "thead" },
      h("div", {}, isBB ? h("div", { class: "tbb" }, "Fogadásépítő") : null, h("div", { class: "tmatch" }, legs[0].match)),
      h("b", {}, odds(isBB ? bbOdds.get(legs[0].id) : legs.length === 1 ? legs[0].odds : null)));
    return h("li", { class: "tgroup" + (isBB ? " bb" : "") + (legs.some((l) => forbidden.has(l.id)) ? " forbidden" : "") }, head,
      ...legs.map((l) => h("div", { class: "tpick" + (forbidden.has(l.id) ? " forbidden" : "") },
        h("span", { class: "tcheck", "aria-hidden": "true" }, "✓"),
        h("div", {}, h("div", { class: "tname" }, l.pick), h("div", { class: "tmarket" }, l.market)),
        h("span", { class: "todd" }, odds(l.odds)),
        h("button", { class: "x", "aria-label": "Tipp törlése", onclick: () => removeLeg(l.id) }, "✕"))));
  }));
  if (!S.slip.length) $("#slip-legs").replaceChildren(h("li", { class: "muted" }, "Kattints egy szorzóra, hogy a szelvényre kerüljön."));
  $("#stake").value = S.stake;
  const out = [];
  const c = S.check;
  if (c && c.error) out.push(h("div", { class: "bad" }, c.error));
  else if (c && c.legs && c.legs.length) {
    if (c.forbidden.length) out.push(h("div", { class: "bad" }, "✗ Kötéstiltás: a pirossal jelölt tippek nem köthetők egymással a TippmixPro-n."));
    else out.push(h("div", { class: "ok" }, "✓ A TippmixPro szerint köthető"));
    if (c.bet_builder.length) out.push(h("div", { class: "muted tiny" }, "Az egy meccsre tett tippeket a TippmixPro Fogadásépítőként árazza, a saját szorzójával."));
    out.push(h("div", { class: "row big" }, h("span", {}, "Odds összesen"), h("b", {}, odds(c.odds))));
    out.push(h("div", { class: "row" }, h("span", {}, "Lehetséges nyeremény"), h("b", {}, ft(c.payout || 0))));
    out.push(h("div", { class: "row" }, h("span", {}, "Minimális tét"), h("span", {}, ft(c.min_stake))));
    if (c.prob != null) {
      out.push(h("div", { class: "row" }, h("span", {}, "Valós nyerési esély"), h("span", {}, pct(c.prob))));
      out.push(h("div", { class: "row" }, h("span", {}, "Várható érték"), h("b", { class: c.ev >= 0 ? "ok" : "bad" }, signedPct(c.ev))));
    }
    for (const w of c.warnings) out.push(h("div", { class: "warn" }, w));
    if (!c.forbidden.length) out.push(saveButton(() => journalFromSlip(c)));
  }
  $("#slip-result").replaceChildren(...out);
}

$("#stake").addEventListener("input", (e) => { S.stake = Math.max(0, parseInt(e.target.value || "0", 10) || 0); store.set("stake", S.stake); runCheck(); });
$("#slip-clear").addEventListener("click", () => { S.slip = []; S.check = null; store.set("slip", []); renderContent(); renderSlip(); });
$("#slip-head").addEventListener("click", (e) => { if (window.innerWidth < 980) $("#slip").classList.toggle("open"); });

// --- értékkereső -----------------------------------------------------------------------------
const season = (s) => (s && s.length === 4 ? `20${s.slice(0, 2)}/${s.slice(2)}` : s || "");

async function renderAccuracy(root) {
  root.replaceChildren(h("div", { class: "spinner" }, "Visszamérés betöltése…"));
  try {
    if (!S.accuracy) S.accuracy = await api("/api/accuracy");
  } catch (e) { root.replaceChildren(h("p", { class: "err" }, e.message)); return; }
  const a = S.accuracy;
  const ms = Object.entries(a.markets || {});
  if (!ms.length) { root.replaceChildren(h("div", { class: "empty" }, "Még nincs visszamérés (calibration.json).")); return; }
  const rows = ms.map(([key, m]) => {
    const gain = m.brier_base ? (m.brier_base - (m.use_map ? m.brier : m.brier_raw)) / m.brier_base : 0;
    const details = h("details", { class: "acc-more" },
      h("summary", {}, "Megbízhatósági tábla"),
      h("table", { class: "acc-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Kiírt esély"), h("th", {}, "Átlagosan kiírt"), h("th", {}, "Valóban bejött"), h("th", {}, "Tippek"))),
        h("tbody", {}, ...m.curve.map(([lo, hi, pred, obs, n]) => h("tr", {},
          h("td", {}, `${Math.round(lo * 100)}–${Math.round(hi * 100)}%`), h("td", {}, pct(pred)),
          h("td", { class: Math.abs(obs - pred) > 0.05 && n >= 50 ? "bad" : "" }, pct(obs)), h("td", {}, n))))));
    return h("div", { class: "acc-row" },
      h("div", { class: "acc-head" },
        h("b", {}, m.name || key),
        h("span", { class: "pchip" + (m.ok ? "" : " low") }, m.ok ? "✓ ajánlja" : "✗ kikapcsolva")),
      h("div", { class: "acc-stats" },
        h("span", {}, `Átlagos eltérés: `, h("b", {}, pct(m.ece_used ?? m.ece)), m.use_map ? " (korrigálva)" : ""),
        h("span", {}, `${m.n_test} tipp a mérési évadban`),
        h("span", {}, gain > 0.01 ? `${pct(gain, 0)}-kal pontosabb, mint a puszta alapgyakoriság` : "alig pontosabb a puszta alapgyakoriságnál")),
      details);
  });
  root.replaceChildren(
    h("div", { class: "panel" },
      h("h2", {}, "Mennyire pontos?"),
      h("p", { class: "muted tiny" }, `Visszamérés régi meccseken: ${(a.leagues || []).join(", ")}. A korrekciót a ${season(a.fit_season)} évadon állítottam be, és a ${season(a.test_season)} évadon mértem, hogy ne a saját adatán mérje magát. Egy piac akkor ajánlható, ha az átlagos eltérés legfeljebb ${pct(a.max_ece || 0.03, 0)}. Forrás: ${a.source || "football-data.co.uk"}.`),
      h("p", { class: "muted tiny" }, "A mérés a záró piaci átlagszorzókból készült, élesben viszont a TippmixPro korábbi szorzóiból számolunk, ezért élesben az eltérés valamivel nagyobb is lehet. Az átlagos eltérés azt mutatja, mennyivel tér el átlagosan a kiírt esély a valóságtól; a pontosság (Brier) azt, mennyivel jobb a tipp a puszta alapgyakoriságnál.")),
    h("div", { class: "acc-list" }, ...rows));
}

function renderBest(root) {
  root.replaceChildren(slipMaker({ key: "best", fixed: null, auto: true }));
}

// Szelvénykészítő panel. fixed: egyetlen sorozat (a sorozat fülén) vagy null (a fő fülön, választható sorozatokkal).
function slipMaker({ key, fixed, auto }) {
  const fairOn = S.state && S.state.fair.enabled;
  const allComps = S.state.competitions.filter((c) => c.matches.length);
  let comps = fixed ? [fixed] : store.get("comps", allComps.map((c) => c.key)).filter((k) => allComps.some((c) => c.key === k));
  if (!comps.length) comps = allComps.map((c) => c.key);
  const stakeIn = h("input", { type: "number", inputmode: "numeric", min: "100", step: "100", value: store.get("bstake", 1000) });
  const targetIn = h("input", { type: "text", inputmode: "decimal", placeholder: "nem kötelező, pl. 8", value: store.get("target", "") });
  const bankIn = h("input", { type: "number", inputmode: "numeric", min: "1000", step: "1000", value: store.get("bank", 50000) });
  const dayIn = h("select", { "aria-label": "Melyik naptól" });
  // Automatikus: célszorzó nélkül legalább 60%, célszorzóval a célszorzót éri el a lehető legnagyobb eséllyel.
  const PROB_OPTS = [["auto", "Automatikus (60%)"], ["70", "legalább 70%"], ["80", "legalább 80%"], ["0", "60% alatti is"]];
  let minProb = store.get("esely", "auto");
  if (!PROB_OPTS.some(([v]) => v === minProb)) minProb = "auto";
  const probIn = h("select", { "aria-label": "Esély" }, ...PROB_OPTS
    .map(([v, t]) => h("option", { value: v, selected: v === minProb }, t)));
  probIn.addEventListener("change", () => store.set("esely", probIn.value));
  const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": "Hány napra" });
  const chips = h("div", { class: "comp-chips", role: "group", "aria-label": "Sorozatok" });
  const result = h("div", {});
  let start = null, ndays = store.get("napok", 1);

  // Meccsnapok budapesti idő szerint, a kiválasztott sorozatokból, meccsszámmal.
  const drawDays = () => {
    const count = new Map();
    for (const c of S.state.competitions) if (comps.includes(c.key)) for (const m of c.matches) {
      const d = fmtIsoDay.format(new Date(m.kickoff));
      count.set(d, (count.get(d) || 0) + 1);
    }
    const days = [...count.keys()].sort();
    // Ha a felhasználó nem választott napot (vagy a választottján nincs meccs), az első olyan napra
    // állunk, ahol legalább 3 meccs van: egy-két meccsből nem lehet érdemi szelvényt rakni.
    const firstGood = days.find((d) => count.get(d) >= 3) || days[0];
    start = store.get("kezd", null);
    if (!days.includes(start)) start = firstGood;
    dayIn.replaceChildren(...days.map((d) => h("option", { value: d, selected: d === start },
      `${fmtDayLabel.format(new Date(d + "T12:00:00Z"))} (${count.get(d)} meccs)`)));
  };
  const drawSeg = () => seg.replaceChildren(...[1, 2, 3].map((n) => h("button", {
    type: "button", role: "radio", "aria-checked": String(n === ndays), class: n === ndays ? "on" : "",
    onclick: () => { ndays = n; store.set("napok", n); drawSeg(); },
  }, `${n} nap`)));
  const drawChips = () => {
    const all = comps.length === allComps.length;
    chips.replaceChildren(
      h("button", { type: "button", class: "chip-btn" + (all ? " on" : ""), "aria-pressed": String(all),
        onclick: () => { comps = allComps.map((c) => c.key); store.set("comps", comps); drawChips(); drawDays(); } }, "Mind"),
      ...allComps.map((c) => {
        const on = comps.includes(c.key);
        return h("button", { type: "button", class: "chip-btn" + (on && !all ? " on" : ""), "aria-pressed": String(on && !all),
          onclick: () => {
            // „Mind" állapotból egy kattintás = csak ez; különben ki-be kapcsol, de legalább egy marad.
            if (all) comps = [c.key];
            else if (on) comps = comps.length > 1 ? comps.filter((k) => k !== c.key) : comps;
            else comps = [...comps, c.key];
            store.set("comps", comps); drawChips(); drawDays();
          } }, c.name);
      }));
  };
  dayIn.addEventListener("change", () => { start = dayIn.value; store.set("kezd", start); });
  // Gépelés közben mentjük: egy szorzóra kattintás újrarajzolja a panelt, a beírt érték ne vesszen el.
  stakeIn.addEventListener("input", () => store.set("bstake", Number(stakeIn.value)));
  targetIn.addEventListener("input", () => store.set("target", targetIn.value));
  bankIn.addEventListener("input", () => store.set("bank", Number(bankIn.value)));
  drawDays(); drawSeg(); if (!fixed) drawChips();

  const run = async () => {
    store.set("bstake", Number(stakeIn.value)); store.set("target", targetIn.value); store.set("bank", Number(bankIn.value));
    result.replaceChildren(h("div", { class: "spinner" }, "Szelvények összerakása a TippmixPro kínálatából…"));
    try {
      const qs = new URLSearchParams({ tet: String(Math.max(100, parseInt(stakeIn.value, 10) || 1000)),
        keret: String(parseInt(bankIn.value, 10) || 50000), napok: String(ndays), sorozat: comps.join(",") });
      if (start) qs.set("kezd", start);
      if (targetIn.value.trim()) qs.set("cel", targetIn.value.trim().replace(",", "."));
      qs.set("esely", probIn.value);
      S.bestBy[key] = await api("/api/best?" + qs);
      result.replaceChildren(bestView(S.bestBy[key]));
    } catch (e) { result.replaceChildren(h("p", { class: "err" }, e.message)); }
  };
  const compName = fixed && S.state.competitions.find((c) => c.key === fixed).name;
  const panel = h("div", {},
    h("div", { class: "panel" },
      h("h2", {}, fixed ? `Szelvénykészítő — ${compName}` : "Szelvénykészítő"),
      h("p", { class: "muted tiny" }, fixed
        ? `Csak ${compName}-meccsekből: hat stratégia, a legesélyesebb tippekkel, a TippmixPro szorzóival és kötéstiltás-ellenőrzésével.`
        : "Válaszd ki a sorozatokat és a napokat: hat stratégiát rak össze a legesélyesebb tippekből (Fogadásépítővel, ahol kell), a TippmixPro szorzóival és kötéstiltás-ellenőrzésével."),
      fixed ? null : h("div", { class: "field" }, h("span", { class: "flabel" }, "Sorozatok"), chips),
      h("div", { class: "day-row" },
        h("label", {}, "Melyik naptól", dayIn),
        h("div", { class: "day-seg" }, h("span", {}, "Hány napra szóljon"), seg)),
      h("div", { class: "form-row" + (fairOn ? " three" : "") },
        h("label", {}, "Tét (Ft)", stakeIn),
        h("label", {}, "Célszorzó", targetIn),
        h("label", {}, "Esély", probIn),
        fairOn ? h("label", {}, "Keret az értékkereséshez (Ft)", bankIn) : null,
        h("button", { class: "primary", onclick: run }, "Szelvények készítése"))),
    result);
  if (S.bestBy[key]) result.replaceChildren(bestView(S.bestBy[key]));
  else if (auto) run();
  return panel;
}

function slipCard(v, i) {
  const when = (k) => `${fmtShort.format(new Date(k))} ${fmtTime.format(new Date(k))}`;
  return h("div", { class: "tslip" },
    h("div", { class: "tslip-head" },
      h("div", { class: "row" }, h("b", {}, `${i + 1}. ${v.name}`),
        h("span", { class: "pchip" + (v.prob < 0.6 ? " low" : ""), title: v.prob < 0.6 ? "60% alatti esély" : "" }, `${pct(v.prob, 0)} esély`)),
      h("span", { class: "muted tiny" }, v.desc)),
    ...v.groups.map((g) => h("div", { class: "tgroup" + (g.builder ? " bb" : "") },
      h("div", { class: "thead" },
        h("div", {}, g.builder ? h("div", { class: "tbb" }, "Fogadásépítő") : null,
          h("div", { class: "tmatch" }, g.match), h("div", { class: "tmarket" }, `${g.competition} · ${when(g.kickoff)}`)),
        h("b", {}, odds(g.odds))),
      ...g.picks.map((p) => h("div", { class: "tpick" },
        h("span", { class: "tcheck", "aria-hidden": "true" }, "✓"),
        h("div", {}, h("div", { class: "tname" }, p.label), h("div", { class: "tmarket" }, `${p.market} - Rendes játékidő`)))),
      h("div", { class: "tprob" }, `Esély, hogy ez a csoport bejön: ${pct(g.prob, 0)}`))),
    h("div", { class: "tfoot" },
      h("div", { class: "row big" }, h("span", {}, "Odds összesen"), h("b", {}, odds(v.odds))),
      h("div", { class: "row" }, h("span", {}, "Tét"), h("span", {}, ft(v.stake))),
      h("div", { class: "row" }, h("span", {}, "Lehetséges nyeremény"), h("b", {}, ft(v.payout))),
      h("div", { class: "row" }, h("span", {}, "Becsült esély, hogy a szelvény nyer"), h("b", {}, pct(v.prob))),
      h("div", { class: "muted tiny" }, `Várható érték ${signedPct(v.ev)}: ennyit visz el hosszú távon a Tippmix árrése.`),
      h("div", { class: "btn-row" },
        h("button", { class: "primary", onclick: () => addLegs(v.groups.flatMap((g) => g.picks), { replace: true, stake: v.stake }) }, "Szelvényre"),
        saveButton(() => journalFromVersion(v)))));
}

function bestView(b) {
  const nodes = [];
  for (const n of b.notes || []) nodes.push(h("div", { class: "notice" }, n));
  if (b.versions && b.versions.length) nodes.push(h("div", { class: "tslips" }, ...b.versions.map(slipCard)));
  if (!b.enabled) {
    nodes.push(h("p", { class: "muted tiny" }, "Az esélyeket most a TippmixPro saját szorzóiból számolom (árrés nélkül). Egy ingyenes The Odds API-kulccsal a Pinnacle árait használná, és azt is megmutatná, melyik Tippmix-szorzó ér többet a valós esélynél."));
    return h("div", {}, ...nodes);
  }
  nodes.push(h("div", { class: "panel" }, h("h2", {}, `Értékes tippek (${b.picks.length})`),
    b.picks.length ? null : h("p", { class: "muted" }, "Most egyetlen TippmixPro-szorzó sem éri el a valós esélyből számolt minimumot. Ilyenkor a kihagyás a nyerő döntés."),
    ...b.picks.slice(0, 40).map((p) => h("div", { class: "pick" },
      h("div", {}, h("div", { class: "t" }, p.label || `${p.market}: ${p.pick}`), h("div", { class: "s" }, `${p.match} · ${p.competition} · ${fmtShort.format(new Date(p.kickoff))} ${fmtTime.format(new Date(p.kickoff))}`),
        h("div", { class: "s" }, `valós esély ${pct(p.prob)} · fair ${odds(p.fair)} · min. ${odds(p.min_odds)}${p.source === "modell" ? " · gólmodell" : ""}`)),
      h("div", { class: "r" }, h("b", {}, odds(p.odds)), h("div", { class: "ok" }, signedPct(p.ev)),
        h("button", { class: "ghost small", onclick: () => addLegs([p]) }, "+ szelvény"))))));
  const betBlock = (title, bets) => h("div", { class: "panel" }, h("h2", {}, title),
    bets.length ? null : h("p", { class: "muted" }, "Nincs ilyen javaslat."),
    ...bets.map((x) => h("div", { class: "bet" },
      h("div", { class: "row" }, h("span", {}, `Tét ${ft(x.stake)} · szorzó ${odds(x.odds)}`), h("b", { class: "ok" }, signedPct(x.ev))),
      h("div", { class: "muted tiny" }, `nyerési esély ${pct(x.prob)} · lehetséges nyeremény ${ft(x.payout)}${x.note ? " · " + x.note : ""}`),
      h("ul", {}, ...x.legs.map((l) => h("li", {}, `${l.match} — ${l.label} @ ${odds(l.odds)}`))),
      h("button", { class: "ghost small", onclick: () => addLegs(x.legs, { replace: true, stake: x.stake }) }, "Szelvényre"))));
  nodes.push(betBlock("A terv — egyesek (ajánlott)", b.singles));
  nodes.push(betBlock("B terv — kötések (TippmixPro által ellenőrizve)", b.combos));
  nodes.push(h("p", { class: "muted tiny" }, "Az A és a B terv ugyanazokból a tippekből áll: az egyiket érdemes megjátszani, nem mindkettőt. Tétméret: negyed Kelly, fogadásonként max. a keret 2%-a, összesen max. 5%."));
  return h("div", {}, ...nodes);
}

// --- szelvénynapló ---------------------------------------------------------------------------
// A böngészőben tárolódik (a szerveren nincs adatbázis, a Railway fájlrendszere ideiglenes).
// Kiértékelés: /api/settle, az ESPN-eredményekből; a tippek állapota: won | lost | void | pending | unknown.
const JOURNAL_MAX = 300;
const FINAL = new Set(["won", "lost", "void", "unknown"]);
const SETTLE_AFTER_MS = (2 * 60 + 15) * 60 * 1000;
const journal = {
  list() { const v = store.get("naplo", []); return Array.isArray(v) ? v : []; },
  save(list) {
    // A legrégebbi lezártak esnek ki először, ha betelik.
    while (list.length > JOURNAL_MAX) {
      const i = list.map((r) => slipStatus(r) !== "pending").lastIndexOf(true);
      list.splice(i >= 0 ? i : list.length - 1, 1);
    }
    store.set("naplo", list);
  },
  add(rec) {
    const list = journal.list();
    if (list.some((r) => r.sig === rec.sig)) return false;
    list.unshift(rec);
    journal.save(list);
    return true;
  },
};

const legSig = (p, g) => JSON.stringify([g.comp, g.home, g.away, g.kickoff, p.mk, p.pick, p.line ?? null]);
const recSig = (groups, stake) => groups.flatMap((g) => g.picks.map((p) => legSig(p, g))).sort().join("|") + "#" + stake;

function journalFromVersion(v) {
  const groups = v.groups.map((g) => ({ match: g.match, competition: g.competition, comp: g.comp, home: g.home, away: g.away,
    kickoff: g.kickoff, odds: g.odds, prob: g.prob, builder: g.builder,
    picks: g.picks.map((p) => ({ label: p.label, market: p.market, mk: p.mk, pick: p.pick, line: p.line, odds: p.odds })) }));
  return { name: v.name, stake: v.stake, odds: v.odds, prob: v.prob, groups };
}

function journalFromSlip(c) {
  const bb = new Map();
  for (const b of c.bet_builder || []) for (const id of b.ids) bb.set(id, b.odds);
  const byMatch = new Map();
  for (const l of S.slip) { if (!byMatch.has(l.matchId)) byMatch.set(l.matchId, []); byMatch.get(l.matchId).push(l); }
  const groups = [...byMatch.values()].map((legs) => ({
    match: legs[0].match, competition: (S.state.competitions.find((x) => x.key === legs[0].comp) || {}).name || "",
    comp: legs[0].comp, home: legs[0].home, away: legs[0].away, kickoff: legs[0].kickoff,
    odds: legs.length > 1 ? bb.get(legs[0].id) ?? null : legs[0].odds, prob: null, builder: legs.length > 1,
    picks: legs.map((l) => ({ label: l.pick, market: l.market, mk: l.mk, pick: l.rawPick, line: l.line, odds: l.odds })) }));
  if (groups.some((g) => !g.comp || !g.home)) return null;  // régi, azonosítás nélküli tipp a szelvényen
  return { name: "Saját szelvény", stake: Math.max(Number(S.stake) || 0, c.min_stake || 0), odds: c.odds, prob: c.prob ?? null, groups };
}

function saveButton(make) {
  const btn = h("button", { class: "ghost small save" }, "Mentés a naplóba");
  btn.addEventListener("click", () => {
    const rec = make();
    if (!rec) { btn.textContent = "Ez a szelvény nem menthető (töröld és rakd össze újra)"; return; }
    rec.sig = recSig(rec.groups, rec.stake);
    rec.id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    rec.saved = new Date().toISOString();
    btn.textContent = journal.add(rec) ? "✓ Mentve a naplóba" : "✓ Már a naplóban van";
    btn.disabled = true;
    renderTabs();
  });
  return btn;
}

// Csoport: minden (nem visszajáró) tipp nyer → nyer; bármelyik veszít → veszít; csak visszajáró → visszajár.
function groupStatus(g) {
  const st = g.picks.map((p) => (p.res && p.res.status) || "pending");
  if (st.includes("lost")) return "lost";
  if (st.some((x) => x === "pending")) return "pending";
  if (st.includes("unknown")) return "unknown";
  if (st.every((x) => x === "void")) return "void";
  return "won";
}
function slipStatus(r) {
  const st = r.groups.map(groupStatus);
  if (st.includes("lost")) return "lost";
  if (st.includes("pending")) return "pending";
  if (st.includes("unknown")) return "unknown";
  return st.every((x) => x === "void") ? "void" : "won";
}
// Visszajáró csoport 1,00-s szorzóval számít (a Fogadásépítő részleges visszajárását a TippmixPro újraárazza: közelítés).
function slipReturn(r) {
  const st = slipStatus(r);
  if (st === "lost") return 0;
  if (st === "void") return r.stake;
  if (st !== "won") return null;
  return r.stake * r.groups.reduce((a, g) => a * (groupStatus(g) === "void" ? 1 : (g.odds || 1)), 1);
}

let settling = null;
async function settleJournal(force) {
  if (settling) return settling;
  const list = journal.list(), now = Date.now();
  const want = new Map();
  for (const r of list) for (const g of r.groups) for (const p of g.picks) {
    if (p.res && FINAL.has(p.res.status)) continue;
    if (!force && now < new Date(g.kickoff).getTime() + SETTLE_AFTER_MS) continue;
    const k = legSig(p, g);
    if (!want.has(k)) want.set(k, { comp: g.comp, home: g.home, away: g.away, kickoff: g.kickoff, mk: p.mk, pick: p.pick, line: p.line ?? null });
  }
  if (!want.size) return 0;
  settling = (async () => {
    const keys = [...want.keys()], got = new Map();
    for (let i = 0; i < keys.length; i += 200) {
      const chunk = keys.slice(i, i + 200);
      const r = await api("/api/settle", { method: "POST", body: JSON.stringify({ legs: chunk.map((k) => want.get(k)) }) });
      chunk.forEach((k, j) => got.set(k, r.results[j]));
    }
    // Közben a felhasználó törölhetett vagy menthetett: a friss listán frissítünk.
    const fresh = journal.list();
    let changed = 0;
    for (const r of fresh) for (const g of r.groups) for (const p of g.picks) {
      const res = got.get(legSig(p, g));
      if (res && (!p.res || p.res.status !== res.status)) { p.res = res; changed++; } else if (res) p.res = res;
    }
    journal.save(fresh);
    return changed;
  })();
  try { return await settling; } finally { settling = null; }
}

const STATUS_TXT = { won: "✓ Nyert", lost: "✗ Vesztett", void: "↺ Visszajár", pending: "⏳ Folyamatban", unknown: "? Nem értékelhető" };

function journalStats(list) {
  const settled = list.filter((r) => ["won", "lost"].includes(slipStatus(r)));
  const won = settled.filter((r) => slipStatus(r) === "won");
  const staked = settled.reduce((a, r) => a + r.stake, 0);
  const returned = settled.reduce((a, r) => a + (slipReturn(r) || 0), 0);
  const withProb = settled.filter((r) => r.prob != null);
  // Esélysávok csoportonként (több minta, mint szelvényenként): a kiírt esély átlaga vs. a valós találati arány.
  const BANDS = [[0, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 0.9], [0.9, 1.01]];
  const bands = BANDS.map(([lo, hi]) => ({ lo, hi, n: 0, hit: 0, pred: 0 }));
  for (const r of list) for (const g of r.groups) {
    const st = groupStatus(g);
    if (g.prob == null || !["won", "lost"].includes(st)) continue;
    const b = bands.find((x) => g.prob >= x.lo && g.prob < x.hi);
    b.n++; b.pred += g.prob; if (st === "won") b.hit++;
  }
  return { n: list.length, settled: settled.length, won: won.length, staked, returned,
    predicted: withProb.length ? withProb.reduce((a, r) => a + r.prob, 0) / withProb.length : null,
    actual: withProb.length ? withProb.filter((r) => slipStatus(r) === "won").length / withProb.length : null,
    bands: bands.filter((b) => b.n) };
}

async function renderJournal(root) {
  const draw = (msg) => {
    const list = journal.list();
    const st = journalStats(list);
    const profit = st.returned - st.staked;
    const nodes = [h("div", { class: "panel" },
      h("h2", {}, "Szelvénynapló"),
      h("p", { class: "muted tiny" }, "A mentett szelvényeket a meccsek után magától kiértékeli (ESPN-eredmények: végeredmény, félidő, szöglet, lap). A napló csak ebben a böngészőben tárolódik."),
      msg ? h("div", { class: "muted tiny" }, msg) : null,
      list.length ? h("div", { class: "jstats" },
        h("div", {}, h("span", {}, "Lezárt szelvény"), h("b", {}, `${st.won} / ${st.settled} nyert`)),
        h("div", {}, h("span", {}, "Megtett tét"), h("b", {}, ft(st.staked))),
        h("div", {}, h("span", {}, "Visszakapott"), h("b", {}, ft(st.returned))),
        h("div", {}, h("span", {}, "Eredmény"), h("b", { class: profit >= 0 ? "ok" : "bad" }, (profit >= 0 ? "+" : "") + ft(profit))),
        st.predicted != null ? h("div", {}, h("span", {}, "Kiírt esély átlaga → valóban nyert"), h("b", {}, `${pct(st.predicted, 0)} → ${pct(st.actual, 0)}`)) : null) : null,
      st.bands.length ? h("table", { class: "acc-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Csoport kiírt esélye"), h("th", {}, "Átlag"), h("th", {}, "Valóban bejött"), h("th", {}, "Csoport"))),
        h("tbody", {}, ...st.bands.map((b) => h("tr", {},
          h("td", {}, b.lo === 0 ? "60% alatt" : `${Math.round(b.lo * 100)}–${Math.min(100, Math.round(b.hi * 100))}%`),
          h("td", {}, pct(b.pred / b.n, 0)),
          h("td", { class: b.n >= 20 && Math.abs(b.hit / b.n - b.pred / b.n) > 0.1 ? "bad" : "" }, pct(b.hit / b.n, 0)),
          h("td", {}, b.n))))) : null,
      st.bands.length && st.bands.reduce((a, b) => a + b.n, 0) < 50 ? h("p", { class: "muted tiny" }, "Kevés még a lezárt tipp: legalább 50–100 kell, hogy a találati arány többet mutasson a véletlennél.") : null,
      h("div", { class: "btn-row" },
        h("button", { class: "ghost small", onclick: async (e) => { e.target.disabled = true; await run(true); } }, "Kiértékelés most"),
        list.length ? h("button", { class: "ghost small", onclick: () => { if (confirm("Biztosan törlöd a teljes naplót?")) { journal.save([]); renderTabs(); draw(); } } }, "Napló törlése") : null))];
    if (!list.length) nodes.push(h("div", { class: "empty" }, "Még nincs mentett szelvény. A szelvénykészítőben vagy a jobb oldali szelvényen a „Mentés a naplóba” gombbal kerül ide."));
    for (const r of list) nodes.push(journalCard(r, () => { journal.save(journal.list().filter((x) => x.id !== r.id)); renderTabs(); draw(); }));
    root.replaceChildren(...nodes);
  };
  const run = async (force) => {
    try {
      const n = await settleJournal(force);
      if (S.tab === "journal") draw(n ? `${n} tipp eredménye frissült.` : (force ? "Nincs új eredmény." : ""));
    } catch (e) { if (S.tab === "journal") draw(`A kiértékelés most nem sikerült: ${e.message}`); }
  };
  draw();
  run(false);
}

function journalCard(r, onDelete) {
  const when = (k) => `${fmtShort.format(new Date(k))} ${fmtTime.format(new Date(k))}`;
  const st = slipStatus(r), ret = slipReturn(r);
  return h("div", { class: "tslip jslip " + st },
    h("div", { class: "tslip-head" },
      h("div", { class: "row" }, h("b", {}, r.name), h("span", { class: "jstatus " + st }, STATUS_TXT[st])),
      h("span", { class: "muted tiny" }, `Mentve ${when(r.saved)} · szorzó ${odds(r.odds)} · tét ${ft(r.stake)}${r.prob != null ? ` · kiírt esély ${pct(r.prob, 0)}` : ""}`)),
    ...r.groups.map((g) => h("div", { class: "tgroup" + (g.builder ? " bb" : "") },
      h("div", { class: "thead" },
        h("div", {}, h("div", { class: "tmatch" }, g.match), h("div", { class: "tmarket" }, `${g.competition} · ${when(g.kickoff)}`
          + (resLine(g) ? ` · ${resLine(g)}` : ""))),
        h("b", {}, odds(g.odds))),
      ...g.picks.map((p) => {
        const s = (p.res && p.res.status) || "pending";
        return h("div", { class: "tpick j-" + s },
          h("span", { class: "tcheck", "aria-hidden": "true" }, { won: "✓", lost: "✗", void: "↺", unknown: "?", pending: "…" }[s]),
          h("div", {}, h("div", { class: "tname" }, p.label), h("div", { class: "tmarket" }, p.market + (p.res && p.res.note ? ` · ${p.res.note}` : ""))));
      }))),
    h("div", { class: "tfoot" },
      h("div", { class: "row" }, h("span", {}, st === "won" ? "Nyeremény" : "Lehetséges nyeremény"),
        h("b", {}, ft(ret != null && st !== "lost" ? ret : r.stake * r.odds))),
      h("button", { class: "ghost small", onclick: onDelete }, "Törlés")));
}

// Az első kiértékelt tipp eredménye a meccsről: „1–1 (félidő 0–1) · 16 szöglet · 10 lap".
function resLine(g) {
  const res = g.picks.map((p) => p.res).find((x) => x && x.score);
  if (!res) return "";
  return [res.score + (res.ht ? ` (félidő ${res.ht})` : ""), res.corners != null ? `${res.corners} szöglet` : "",
    res.cards != null ? `${res.cards} lap` : ""].filter(Boolean).join(" · ");
}

boot();

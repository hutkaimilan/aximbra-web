"use strict";
// Szelvényépítő — a szerver adataiból rajzol; minden külső szöveg textContent-tel kerül a DOM-ba.

const $ = (s) => document.querySelector(s);
const TZ = "Europe/Budapest";
const fmtDay = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, weekday: "long", month: "long", day: "numeric" });
const fmtTime = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtShort = new Intl.DateTimeFormat("hu-HU", { timeZone: TZ, month: "2-digit", day: "2-digit" });
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
  best: null,
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
  const tabs = [{ key: "best", name: "Értékkereső" }, ...S.state.competitions.map((c) => ({ key: c.key, name: c.name, n: c.matches.length }))];
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
  renderList(root, matchesFor(S.tab), false);
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

function oddButton(m, mk, o) {
  const on = S.slip.some((s) => s.id === o.id);
  const label = mk.key === "ou" ? `${o.pick}` : o.pick;
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
    S.slip.push({ id: o.id, match: `${m.home} – ${m.away}`, market: mk.name, pick: o.pick, odds: o.odds, matchId: m.id });
  }
  store.set("slip", S.slip);
  renderContent(); renderSlip(); runCheck();
}

function addLegs(legs) {
  const idx = indexState();
  for (const l of legs) {
    if (S.slip.some((s) => s.id === l.id)) continue;
    const hit = idx.get(l.id);
    if (hit) S.slip.push({ id: l.id, match: `${hit.m.home} – ${hit.m.away}`, market: hit.mk.name, pick: hit.o.pick, odds: hit.o.odds, matchId: hit.m.id });
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
  $("#slip-legs").replaceChildren(...S.slip.map((s) => h("li", { class: "leg" + (forbidden.has(s.id) ? " forbidden" : "") + (builder.has(s.id) ? " builder" : "") },
    h("div", {}, h("div", {}, `${s.market}: `, h("b", {}, s.pick)), h("div", { class: "m" }, s.match)),
    h("b", {}, odds(s.odds)),
    h("button", { class: "x", "aria-label": "Tipp törlése", onclick: () => { S.slip = S.slip.filter((x) => x.id !== s.id); store.set("slip", S.slip); renderContent(); renderSlip(); runCheck(); } }, "✕"))));
  if (!S.slip.length) $("#slip-legs").replaceChildren(h("li", { class: "muted" }, "Kattints egy szorzóra, hogy a szelvényre kerüljön."));
  $("#stake").value = S.stake;
  const out = [];
  const c = S.check;
  if (c && c.error) out.push(h("div", { class: "bad" }, c.error));
  else if (c && c.legs && c.legs.length) {
    if (c.forbidden.length) out.push(h("div", { class: "bad" }, "✗ Kötéstiltás: a pirossal jelölt tippek nem köthetők egymással a TippmixPro-n."));
    else out.push(h("div", { class: "ok" }, "✓ A TippmixPro szerint köthető"));
    if (c.bet_builder.length) out.push(h("div", { class: "warn" }, "Ugyanarról a meccsről több tipp: a TippmixPro Fogadásépítőként árazza (sárga keret), a saját szorzójával."));
    out.push(h("div", { class: "row" }, h("span", {}, "Eredő szorzó"), h("b", {}, odds(c.odds))));
    out.push(h("div", { class: "row" }, h("span", {}, "Lehetséges nyeremény"), h("b", {}, ft(c.payout || 0))));
    out.push(h("div", { class: "row" }, h("span", {}, "Minimális tét"), h("span", {}, ft(c.min_stake))));
    if (c.prob != null) {
      out.push(h("div", { class: "row" }, h("span", {}, "Valós nyerési esély"), h("span", {}, pct(c.prob))));
      out.push(h("div", { class: "row" }, h("span", {}, "Várható érték"), h("b", { class: c.ev >= 0 ? "ok" : "bad" }, signedPct(c.ev))));
    }
    for (const w of c.warnings) out.push(h("div", { class: "warn" }, w));
  }
  $("#slip-result").replaceChildren(...out);
}

$("#stake").addEventListener("input", (e) => { S.stake = Math.max(0, parseInt(e.target.value || "0", 10) || 0); store.set("stake", S.stake); runCheck(); });
$("#slip-clear").addEventListener("click", () => { S.slip = []; S.check = null; store.set("slip", []); renderContent(); renderSlip(); });
$("#slip-head").addEventListener("click", (e) => { if (window.innerWidth < 980) $("#slip").classList.toggle("open"); });

// --- értékkereső -----------------------------------------------------------------------------
function renderBest(root) {
  const bank = store.get("bank", 50000), target = store.get("target", "");
  const bankIn = h("input", { type: "number", inputmode: "numeric", min: "1000", step: "1000", value: bank });
  const targetIn = h("input", { type: "text", inputmode: "decimal", placeholder: "pl. 3,5", value: target });
  const result = h("div", {});
  const run = async () => {
    store.set("bank", Number(bankIn.value)); store.set("target", targetIn.value);
    result.replaceChildren(h("div", { class: "spinner" }, "Keresés a teljes kínálatban…"));
    try {
      const qs = new URLSearchParams({ keret: String(parseInt(bankIn.value, 10) || 50000) });
      if (targetIn.value.trim()) qs.set("cel", targetIn.value.trim().replace(",", "."));
      S.best = await api("/api/best?" + qs);
      result.replaceChildren(bestView(S.best));
    } catch (e) { result.replaceChildren(h("p", { class: "err" }, e.message)); }
  };
  root.replaceChildren(
    h("div", { class: "panel" },
      h("h2", {}, "Értékkereső"),
      h("p", { class: "muted tiny" }, "Végignézi mind a hat sorozat TippmixPro-kínálatát, és azokat a tippeket keresi, ahol a Tippmix szorzója nagyobb, mint amit a valós esély indokol. A javasolt kötéseket a TippmixPro kötéstiltás-ellenőrzése is jóváhagyja."),
      h("div", { class: "form-row" },
        h("label", {}, "Keret (Ft)", bankIn),
        h("label", {}, "Célszorzó (kötés, opcionális)", targetIn),
        h("button", { class: "primary", onclick: run }, "Keresés"))),
    result);
  if (S.best) result.replaceChildren(bestView(S.best)); else run();
}

function bestView(b) {
  const nodes = [];
  for (const n of b.notes || []) nodes.push(h("div", { class: "notice" }, n));
  if (!b.enabled) {
    nodes.push(h("div", { class: "panel" }, h("h2", {}, "Valós esély nélkül"),
      h("p", { class: "muted" }, "Az értékkereséshez egy ingyenes The Odds API-kulcs kell (ODDS_API_KEY a szerveren). Addig a legalacsonyabb árrésű meccseket mutatom: ezeken veszi el a Tippmix a legkevesebbet, de ez még nem jelent pozitív várható értéket."),
      ...b.low_margin.map((r) => h("div", { class: "pick" },
        h("div", {}, h("div", { class: "t" }, r.match), h("div", { class: "s" }, `${r.competition} · ${fmtShort.format(new Date(r.kickoff))} ${fmtTime.format(new Date(r.kickoff))}`)),
        h("div", { class: "r" }, h("b", {}, pct(r.margin)), h("div", { class: "s" }, "árrés"))))));
    return h("div", {}, ...nodes);
  }
  nodes.push(h("div", { class: "panel" }, h("h2", {}, `Értékes tippek (${b.picks.length})`),
    b.picks.length ? null : h("p", { class: "muted" }, "Most egyetlen TippmixPro-szorzó sem éri el a valós esélyből számolt minimumot. Ilyenkor a kihagyás a nyerő döntés."),
    ...b.picks.slice(0, 40).map((p) => h("div", { class: "pick" },
      h("div", {}, h("div", { class: "t" }, `${p.market}: ${p.pick}`), h("div", { class: "s" }, `${p.match} · ${p.competition} · ${fmtShort.format(new Date(p.kickoff))} ${fmtTime.format(new Date(p.kickoff))}`),
        h("div", { class: "s" }, `valós esély ${pct(p.prob)} · fair ${odds(p.fair)} · min. ${odds(p.min_odds)}${p.source === "modell" ? " · gólmodell" : ""}`)),
      h("div", { class: "r" }, h("b", {}, odds(p.odds)), h("div", { class: "ok" }, signedPct(p.ev)),
        h("button", { class: "ghost small", onclick: () => addLegs([p]) }, "+ szelvény"))))));
  const betBlock = (title, bets) => h("div", { class: "panel" }, h("h2", {}, title),
    bets.length ? null : h("p", { class: "muted" }, "Nincs ilyen javaslat."),
    ...bets.map((x) => h("div", { class: "bet" },
      h("div", { class: "row" }, h("span", {}, `Tét ${ft(x.stake)} · szorzó ${odds(x.odds)}`), h("b", { class: "ok" }, signedPct(x.ev))),
      h("div", { class: "muted tiny" }, `nyerési esély ${pct(x.prob)} · lehetséges nyeremény ${ft(x.payout)}${x.note ? " · " + x.note : ""}`),
      h("ul", {}, ...x.legs.map((l) => h("li", {}, `${l.match} — ${l.label} @ ${odds(l.odds)}`))),
      h("button", { class: "ghost small", onclick: () => addLegs(x.legs) }, "Szelvényre"))));
  nodes.push(betBlock("A terv — egyesek (ajánlott)", b.singles));
  nodes.push(betBlock("B terv — kötések (TippmixPro által ellenőrizve)", b.combos));
  nodes.push(h("p", { class: "muted tiny" }, "Az A és a B terv ugyanazokból a tippekből áll: az egyiket érdemes megjátszani, nem mindkettőt. Tétméret: negyed Kelly, fogadásonként max. a keret 2%-a, összesen max. 5%."));
  return h("div", {}, ...nodes);
}

boot();

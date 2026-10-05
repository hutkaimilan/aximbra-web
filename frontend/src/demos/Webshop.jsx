import { useEffect, useMemo, useState } from "react";
import { ShoppingBag, Minus, Plus, X, Search, Check, Truck, RotateCcw, ShieldCheck, Repeat } from "lucide-react";
import "./webshop.css";
import { DemoBar } from "./DemoBar";
import { Rise, ScriptedChat, money, reduceMotion, useDemo, useFonts } from "./kit";
import C from "./content/webshop";

const ROAST_COLORS = ["#C99A68", "#8A5A35", "#3E2416"];
const mix = (a, b, t) => {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = [p(a), p(b)];
  return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(",")})`;
};
const roastColor = (v) => (v <= 50 ? mix(ROAST_COLORS[0], ROAST_COLORS[1], v / 50) : mix(ROAST_COLORS[1], ROAST_COLORS[2], (v - 50) / 50));

const Bean = ({ color, className = "" }) => (
  <svg viewBox="0 0 100 130" className={className} aria-hidden="true">
    <ellipse cx="50" cy="65" rx="40" ry="56" fill={color} style={{ transition: "fill .4s" }} />
    <path d="M50 12C30 40 70 90 50 118" stroke="rgba(0,0,0,.35)" strokeWidth="6" fill="none" strokeLinecap="round" />
    <ellipse cx="34" cy="40" rx="9" ry="16" fill="rgba(255,255,255,.18)" />
  </svg>
);

/** A védjegy: gőzölgő csésze, körülötte lassan keringő szemek. */
const Cup = () => (
  <div className="shop-cup" aria-hidden="true">
    <svg viewBox="0 0 300 300">
      <g className="shop-steam">
        <path d="M120 110c-14-16 14-26 0-44s12-28 2-40" />
        <path d="M150 104c-14-16 14-26 0-44s12-28 2-40" />
        <path d="M180 110c-14-16 14-26 0-44s12-28 2-40" />
      </g>
      <ellipse cx="150" cy="250" rx="110" ry="16" fill="rgba(43,26,18,.12)" />
      <path d="M68 128h164l-14 96a30 30 0 0 1-30 26h-76a30 30 0 0 1-30-26z" fill="#F7F1E8" stroke="#2B1A12" strokeWidth="3" />
      <path d="M232 146c34 0 34 52 0 54" fill="none" stroke="#2B1A12" strokeWidth="10" strokeLinecap="round" />
      <ellipse cx="150" cy="128" rx="82" ry="14" fill="#3E2416" stroke="#2B1A12" strokeWidth="3" />
      <ellipse cx="140" cy="126" rx="34" ry="5" fill="#8A5A35" className="shop-crema" />
      <rect x="96" y="168" width="108" height="34" rx="4" fill="#C8643B" />
      <text x="150" y="191" textAnchor="middle" fontFamily="DM Serif Display, serif" fontSize="18" fill="#F7F1E8" letterSpacing="4">ŐRLŐ</text>
    </svg>
    {[0, 1, 2, 3, 4].map((i) => <span key={i} className="shop-orb" style={{ "--i": i }}><Bean color={ROAST_COLORS[i % 3]} /></span>)}
  </div>
);

const Bag = ({ r }) => (
  <svg viewBox="0 0 120 150" className="shop-bag" aria-hidden="true">
    <path d="M22 22h76l10 118H12z" fill={["#E9DCC8", "#D6B48C", "#4A2E1F"][r]} />
    <path d="M22 22h76v14H22z" fill="rgba(0,0,0,.12)" />
    <path d="M22 22l8-12h60l8 12" fill="none" stroke="rgba(0,0,0,.3)" strokeWidth="2" />
    <rect x="30" y="62" width="60" height="44" rx="3" fill="#F7F1E8" />
    <text x="60" y="82" textAnchor="middle" fontFamily="DM Serif Display, serif" fontSize="13" fill="#2B1A12" letterSpacing="2">ŐRLŐ</text>
    <circle cx={42 + r * 18} cy="96" r="4" fill="#C8643B" />
    <path d="M42 96h36" stroke="#2B1A12" strokeWidth="1" opacity=".3" />
  </svg>
);

const AGENT_URL = "https://aximbra-webshop-production.up.railway.app/api/demo/reply";

/** Élő agent: a valódi webshop-agent válaszol a demóbolt rendeléseiből. Nem küld semmit, csak tervezetet ad. */
const LiveAgent = ({ d }) => {
  const [from, setFrom] = useState(d.liveSamples[0][0]);
  const [msg, setMsg] = useState(d.liveSamples[0][1]);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const send = async (e) => {
    e.preventDefault();
    if (busy || msg.trim().length < 3) return;
    setBusy(true); setErr(""); setRes(null);
    try {
      const r = await fetch(AGENT_URL, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_email: from.trim(), subject: "", body: msg.trim() }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || d.liveErr);
      setRes(j);
    } catch (x) { setErr(x.message || d.liveErr); } finally { setBusy(false); }
  };
  return (
    <div className="shop-live">
      <div className="shop-live-samples">
        {d.liveSamples.map(([f, m], i) => (
          <button key={i} type="button" className="shop-chip" onClick={() => { setFrom(f); setMsg(m); setRes(null); }}>{f}</button>
        ))}
      </div>
      <form onSubmit={send} className="shop-live-f">
        <label><span>{d.liveFrom}</span><input value={from} onChange={(e) => setFrom(e.target.value)} maxLength={200} /></label>
        <label><span>{d.liveMsg}</span><textarea rows={3} value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={2000} /></label>
        <button type="submit" className="shop-btn solid" disabled={busy}>{busy ? d.liveSending : d.liveSend}</button>
        <p className="shop-note" style={{ textAlign: "left" }}>{d.liveHint}</p>
      </form>
      {err && <p className="shop-track-no" role="status">{err}</p>}
      {res && (
        <div className="shop-live-out" role="status">
          <div className="shop-live-tags">
            <span className={res.verified ? "ok" : res.order_found ? "warn" : ""}>{res.verified ? d.liveOk : res.order_found ? d.liveNo : d.liveNone}</span>
            {res.needs_human && <span className="warn">{d.liveHuman}</span>}
          </div>
          <div className="shop-live-h">{d.liveDraft}</div>
          <pre>{res.body}</pre>
        </div>
      )}
    </div>
  );
};

const Tracker = ({ d }) => {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [stage, setStage] = useState(-1);
  useEffect(() => {
    if (res !== "ok") return;
    if (reduceMotion()) { setStage(3); return; }
    setStage(-1);
    let k = -1;
    const id = setInterval(() => { k += 1; setStage(k); if (k >= 3) clearInterval(id); }, 420);
    return () => clearInterval(id);
  }, [res]);
  const script = useMemo(() => [{ from: "user", text: q.trim().toUpperCase() || "ORL-1042" }, { from: "bot", text: d.agent }],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [res, d.agent]);
  const go = (e) => {
    e.preventDefault();
    setRes(null);
    setTimeout(() => setRes(q.trim().toUpperCase().replace(/\s/g, "") === "ORL-1042" ? "ok" : "no"), 10);
  };
  return (
    <div className="shop-track">
      <form className="shop-track-f" onSubmit={go}>
        <Search size={18} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={d.trackPh} aria-label={d.trackTitle} />
        <button type="submit" className="shop-btn solid">{d.trackBtn}</button>
      </form>
      <button type="button" className="shop-hint" onClick={() => setQ("ORL-1042")}>{d.trackHint}</button>
      {res === "no" && <p className="shop-track-no" role="status">{d.notFound}</p>}
      {res === "ok" && (
        <div className="shop-track-ok">
          <ol className="shop-tl">
            {d.steps.map((s, i) => (
              <li key={s} className={i <= stage ? (i === 3 ? "on now" : "on") : ""}>
                <span>{i < 3 || (i === 3 && stage >= 3) ? (i === 3 ? <Truck size={15} /> : <Check size={15} />) : null}</span>{s}
              </li>
            ))}
          </ol>
          <ScriptedChat script={script} cls="shop" start />
          <span className="shop-badge">{d.badge}</span>
        </div>
      )}
    </div>
  );
};

export default function Webshop() {
  const { d } = useDemo(C, "/demo/webshop");
  useFonts("https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap");
  const [roast, setRoast] = useState(30);
  const [cart, setCart] = useState({});
  const [open, setOpen] = useState(false);
  const [flash, setFlash] = useState("");
  const [bump, setBump] = useState(0);
  const ri = roast < 34 ? 0 : roast < 67 ? 1 : 2;
  const pick = d.products.find((p) => p.r === ri);
  const items = d.products.filter((p) => cart[p.id]);
  const count = items.reduce((a, p) => a + cart[p.id], 0);
  const total = items.reduce((a, p) => a + cart[p.id] * p.p, 0);
  const add = (id) => {
    setCart((c) => ({ ...c, [id]: (c[id] || 0) + 1 }));
    setFlash(id); setBump((b) => b + 1);
    setTimeout(() => setFlash((f) => (f === id ? "" : f)), 1400);
  };
  const setQty = (id, n) => setCart((c) => { const x = { ...c }; if (n <= 0) delete x[id]; else x[id] = n; return x; });
  useEffect(() => {
    if (!open) return;
    const k = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);
  const pct = Math.min(100, (total / d.freeAt) * 100);

  return (
    <div className="shop-page demo-page" data-testid="demo-webshop">
      <DemoBar prefix="shop" />
      <div className="shop-ship">{d.ship.replace("{x}", money(d.freeAt, d.cur))}</div>

      <header className="shop-hero">
        <div className="shop-wrap shop-hero-in">
          <div>
            <div className="shop-logo">{d.brand}<span>{d.brandSub}</span></div>
            <div className="shop-eyebrow">{d.eyebrow}</div>
            <h1 className="shop-title">{d.title}</h1>
            <p className="shop-sub">{d.sub}</p>
            <div className="shop-cta">
              <a href="#kavek" className="shop-btn solid">{d.cta}</a>
              <a href="#kovetes" className="shop-btn">{d.ghost}</a>
            </div>
          </div>
          <Cup />
        </div>
      </header>

      <section className="shop-sec shop-finder">
        <div className="shop-wrap shop-finder-in">
          <Rise>
            <span className="shop-tag">{d.roastTag}</span>
            <h2 className="shop-h2">{d.roastTitle}</h2>
            <p className="shop-lead">{d.roastSub}</p>
            <div className="shop-range">
              <input type="range" min="0" max="100" value={roast} onChange={(e) => setRoast(+e.target.value)}
                aria-label={d.roastTitle} style={{ "--c": roastColor(roast) }} />
              <div className="shop-range-l">{d.roasts.map((r, i) => <span key={r.n} className={i === ri ? "on" : ""}>{r.n}</span>)}</div>
            </div>
          </Rise>
          <div className="shop-finder-vis">
            <Bean color={roastColor(roast)} className="shop-bigbean" />
            <ul className="shop-notes">{d.roasts[ri].notes.map((n) => <li key={n}>{n}</li>)}</ul>
            <p className="shop-hint2">{d.roasts[ri].hint}</p>
            <div className="shop-match">
              <span>{d.match}</span> <b>{pick.n}</b>
              <button type="button" className="shop-btn solid sm" onClick={() => add(pick.id)}>{flash === pick.id ? d.added : d.add}</button>
            </div>
          </div>
        </div>
      </section>

      <section className="shop-sec" id="kavek">
        <div className="shop-wrap">
          <Rise><h2 className="shop-h2">{d.shopTitle}</h2></Rise>
          <div className="shop-grid">
            {d.products.map((p, i) => (
              <Rise key={p.id} delay={i * 80} className={`shop-card ${p.id === pick.id ? "match" : ""}`}>
                <div className="shop-card-img"><Bag r={p.r} /><span className="shop-roast">{d.roasts[p.r].n}</span></div>
                <div className="shop-card-b">
                  <div className="shop-o">{p.o}</div>
                  <h3>{p.n}</h3>
                  <p>{p.notes}</p>
                  <div className="shop-card-f">
                    <span><b>{money(p.p, d.cur)}</b> / {d.size}</span>
                    <button type="button" className={`shop-add ${flash === p.id ? "ok" : ""}`} onClick={() => add(p.id)}>
                      {flash === p.id ? <><Check size={16} />{d.added}</> : <><Plus size={16} />{d.add}</>}
                    </button>
                  </div>
                </div>
              </Rise>
            ))}
          </div>
          <ul className="shop-perks">
            {[Truck, RotateCcw, ShieldCheck].map((Ic, i) => <li key={i}><Ic size={18} />{d.perks[i]}</li>)}
          </ul>
        </div>
      </section>

      <section className="shop-sec shop-dark" id="kovetes">
        <div className="shop-wrap shop-track-in">
          <Rise>
            <span className="shop-tag">{d.trackTag}</span>
            <h2 className="shop-h2">{d.trackTitle}</h2>
            <p className="shop-lead">{d.trackSub}</p>
          </Rise>
          <Tracker d={d} />
        </div>
      </section>

      <section className="shop-sec" id="ugyfelszolgalat">
        <div className="shop-wrap shop-track-in">
          <Rise>
            <span className="shop-tag">{d.liveTag}</span>
            <h2 className="shop-h2">{d.liveTitle}</h2>
            <p className="shop-lead">{d.liveSub}</p>
          </Rise>
          <LiveAgent d={d} />
        </div>
      </section>

      <section className="shop-sec">
        <Rise className="shop-wrap shop-subs">
          <Repeat size={30} />
          <h2 className="shop-h2">{d.subTitle}</h2>
          <p className="shop-lead">{d.subText}</p>
          <a href={`mailto:${d.email}`} className="shop-btn" onClick={(e) => e.preventDefault()}>{d.subCta}</a>
        </Rise>
      </section>

      <footer className="shop-footer">© {d.brand} {d.brandSub} · {d.address} · {d.email}</footer>

      <button type="button" className="shop-fab" onClick={() => setOpen(true)} aria-label={`${d.cart} (${count})`}>
        <ShoppingBag size={22} />
        {count > 0 && <span key={bump} className="shop-count">{count}</span>}
      </button>

      <div className={`shop-drawer-bg ${open ? "on" : ""}`} onClick={() => setOpen(false)} aria-hidden="true" />
      <aside className={`shop-drawer ${open ? "on" : ""}`} aria-hidden={!open} aria-label={d.cart}>
        <div className="shop-drawer-h"><h3>{d.cart} ({count})</h3>
          <button type="button" onClick={() => setOpen(false)} aria-label={d.close}><X size={20} /></button></div>
        <div className="shop-free">
          <p>{total >= d.freeAt ? d.freeOk : d.freeLeft.replace("{x}", money(d.freeAt - total, d.cur))}</p>
          <div className="shop-free-bar"><span style={{ width: `${pct}%` }} /></div>
        </div>
        <div className="shop-lines">
          {!items.length && <p className="shop-empty">{d.empty}</p>}
          {items.map((p) => (
            <div key={p.id} className="shop-line">
              <Bag r={p.r} />
              <div><b>{p.n}</b><small>{d.size} · {money(p.p, d.cur)}</small>
                <div className="shop-qty">
                  <button type="button" onClick={() => setQty(p.id, cart[p.id] - 1)} aria-label={d.remove}><Minus size={14} /></button>
                  <span>{cart[p.id]}</span>
                  <button type="button" onClick={() => setQty(p.id, cart[p.id] + 1)} aria-label="+"><Plus size={14} /></button>
                </div>
              </div>
              <span className="shop-line-p">{money(p.p * cart[p.id], d.cur)}</span>
            </div>
          ))}
        </div>
        <div className="shop-drawer-f">
          <div className="shop-sum"><span>{d.total}</span><b>{money(total, d.cur)}</b></div>
          <button type="button" className="shop-btn solid wide" disabled>{d.checkout}</button>
          <p className="shop-note">{d.checkoutNote}</p>
        </div>
      </aside>
    </div>
  );
}

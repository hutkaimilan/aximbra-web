import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import "./neked.css";
import { useDocumentMeta } from "../seo";
import { bcp47 } from "../i18n";
import { agentName, textFor } from "./nekedText";

/**
 * aximbra.hu/neked/:slug — egy megkeresett cégnek készült demóoldal.
 *
 * A tartalmat a sales agent állítja össze (sales-agent/demopage.py): mit
 * csinál a cég a saját oldala szerint, melyik agent illik hozzá, és ahhoz
 * példaadatos demó. Itt csak megjelenítjük, és visszajelezzük, ha megnyitották
 * vagy rákattintottak valamire — az első megnyitásról azonnal értesítés megy.
 *
 * ?preview=1: a saját ellenőrzésünk, nem számít megnyitásnak.
 */

const SALES = process.env.REACT_APP_SALES_URL || "https://aximbra-sales-production.up.railway.app";
const EMAIL = "aximbra@gmail.com";
// A díjak forintban jönnek; nem magyar oldalon euróban mutatjuk, kerekítve.
const HUF_PER_EUR = 400;

const preview = () => new URLSearchParams(window.location.search).get("preview") === "1";

function sendEvent(slug, type) {
  if (preview()) return;
  try {
    fetch(`${SALES}/public/neked/${encodeURIComponent(slug)}/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type }),
      keepalive: true,
    }).catch(() => {});
  } catch { /* a számláló soha nem ronthatja el az oldalt */ }
}

/** Betöltés: a sales agent alszik, ha nincs forgalom, az első kérés lassú lehet. */
function usePage(slug) {
  const [state, setState] = useState({ status: "loading", slow: false, data: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    const slowTimer = setTimeout(() => alive && setState((s) => ({ ...s, slow: true })), 4000);
    (async () => {
      for (let i = 0; i < 3 && alive; i++) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 30000);
        try {
          const r = await fetch(`${SALES}/public/neked/${encodeURIComponent(slug)}`, { signal: ctrl.signal });
          clearTimeout(timer);
          if (r.status === 404) { if (alive) setState({ status: "gone", data: null }); return; }
          if (!r.ok) throw new Error(String(r.status));
          const data = await r.json();
          if (alive) setState({ status: "ready", data });
          return;
        } catch {
          clearTimeout(timer);
          await new Promise((res) => setTimeout(res, 1500 * (i + 1)));
        }
      }
      if (alive) setState({ status: "error", data: null });
    })();
    return () => { alive = false; clearTimeout(slowTimer); };
  }, [slug, attempt]);

  const retry = useCallback(() => { setState({ status: "loading", slow: false, data: null }); setAttempt((a) => a + 1); }, []);
  return [state, retry];
}

/** Lépésenként felfedő animáció: run() után 0-tól n-ig számol. */
function useReveal(n, ms = 520) {
  const [shown, setShown] = useState(-1); // -1: még nem indult
  const timer = useRef(null);
  const run = useCallback(() => {
    clearInterval(timer.current);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setShown(n); return; }
    setShown(0);
    let i = 0;
    timer.current = setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= n) clearInterval(timer.current);
    }, ms);
  }, [n, ms]);
  useEffect(() => () => clearInterval(timer.current), []);
  return [shown, run];
}

function RunBar({ t, shown, onRun }) {
  return (
    <div className="nk-runbar">
      <button type="button" className="nk-run" onClick={onRun}>
        {shown < 0 ? t.run : t.again}
      </button>
      <span className="nk-note">{t.demoNote}</span>
    </div>
  );
}

function Inbox({ d, t, onUse }) {
  const [shown, run] = useReveal(d.items.length);
  const [open, setOpen] = useState(null);
  const done = shown >= d.items.length;
  const items = done ? [...d.items].map((x, i) => ({ ...x, i })).sort((a, b) => b.urgency - a.urgency)
    : d.items.map((x, i) => ({ ...x, i }));
  return (
    <>
      <RunBar t={t} shown={shown} onRun={() => { onUse(); setOpen(null); run(); }} />
      <ul className="nk-list">
        {items.map((m) => {
          const tagged = shown > m.i;
          return (
            <li key={m.i} className={`nk-mail${tagged ? " is-tagged" : ""}${open === m.i ? " is-open" : ""}`}>
              <button type="button" className="nk-mail-head" onClick={() => { onUse(); setOpen(open === m.i ? null : m.i); }}
                aria-expanded={open === m.i}>
                <span className="nk-from">{m.from}</span>
                <span className="nk-subj">{m.subject}</span>
                <span className="nk-snip">{m.snippet}</span>
                {tagged && (
                  <span className="nk-tags">
                    <span className="nk-chip">{m.category}</span>
                    <span className="nk-urg" aria-label={`${t.urgency}: ${m.urgency}/5`}>
                      {[1, 2, 3, 4, 5].map((k) => <i key={k} className={k <= m.urgency ? "on" : ""} />)}
                    </span>
                  </span>
                )}
              </button>
              {open === m.i && m.reply && (
                <div className="nk-reply"><b>{t.draft}</b><p>{m.reply}</p></div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Leads({ d, t, onUse }) {
  const [shown, run] = useReveal(d.items.length);
  return (
    <>
      <RunBar t={t} shown={shown} onRun={() => { onUse(); run(); }} />
      <ul className="nk-list">
        {d.items.map((l, i) => {
          const on = shown > i;
          return (
            <li key={i} className={`nk-lead${on ? " is-scored" : ""}`}>
              <div className="nk-lead-top">
                <span className="nk-from">{l.name}</span>
                <span className={`nk-grade g-${on ? l.grade : "x"}`}>{on ? l.grade : "·"}</span>
              </div>
              <p className="nk-snip">{l.need}</p>
              <div className="nk-bar" aria-label={`${t.score}: ${on ? l.score : "?"}`}>
                <span style={{ width: on ? `${l.score}%` : 0 }} />
              </div>
              {on && l.next && <p className="nk-next"><b>{t.next}:</b> {l.next}</p>}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Document({ d, t, onUse }) {
  const [shown, run] = useReveal(d.clauses.length);
  return (
    <>
      <RunBar t={t} shown={shown} onRun={() => { onUse(); run(); }} />
      {d.title && <h4 className="nk-doc-title">{d.title}</h4>}
      <ol className="nk-doc">
        {d.clauses.map((c, i) => {
          const on = shown > i;
          return (
            <li key={i} className={on ? `risk-${c.risk}` : ""}>
              <p>{c.text}</p>
              {on && (
                <div className="nk-risk">
                  <span className="nk-chip">{t.risk[c.risk] || t.risk.none}</span>
                  {c.note && <span>{c.note}</span>}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </>
  );
}

function Report({ d, t, onUse }) {
  const parts = d.metrics.length + d.findings.length + d.actions.length;
  const [shown, run] = useReveal(parts, 380);
  let k = 0;
  const on = () => shown > k++;
  return (
    <>
      <RunBar t={t} shown={shown} onRun={() => { onUse(); run(); }} />
      <div className="nk-report">
        {(d.title || d.period) && <h4 className="nk-doc-title">{d.title} <span>{d.period}</span></h4>}
        <div className="nk-metrics">
          {d.metrics.map((m, i) => (
            <div key={i} className={`nk-metric${on() ? " is-on" : ""}`}>
              <span className="nk-m-label">{m.label}</span>
              <span className="nk-m-value">{m.value}</span>
              {m.change && <span className="nk-m-change">{m.change}</span>}
            </div>
          ))}
        </div>
        <h5>{t.findings}</h5>
        <ul className="nk-bullets">{d.findings.map((f, i) => <li key={i} className={on() ? "is-on" : ""}>{f}</li>)}</ul>
        {d.actions.length > 0 && <h5>{t.actions}</h5>}
        <ul className="nk-bullets act">{d.actions.map((a, i) => <li key={i} className={on() ? "is-on" : ""}>{a}</li>)}</ul>
      </div>
    </>
  );
}

function Dialogue({ lines, t, onUse, roleOf, labelOf, after, afterTitle }) {
  const [shown, run] = useReveal(lines.length + 1, 900);
  const box = useRef(null);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [shown]);
  return (
    <>
      <RunBar t={t} shown={shown} onRun={() => { onUse(); run(); }} />
      <div className="nk-chat" ref={box} aria-live="polite">
        {lines.map((m, i) => (shown > i || shown < 0) && (
          <div key={i} className={`nk-msg ${roleOf(m) === "agent" ? "is-agent" : "is-them"}${shown < 0 ? " is-dim" : ""}`}>
            <span className="nk-who">{labelOf(m)}</span>
            <p>{m.text}</p>
          </div>
        ))}
      </div>
      {after && shown > lines.length && (
        <div className="nk-reply"><b>{afterTitle}</b><p>{after}</p></div>
      )}
    </>
  );
}

function Content({ d, t, onUse }) {
  const [tab, setTab] = useState(0);
  const it = d.items[tab] || d.items[0];
  return (
    <>
      <div className="nk-runbar"><span className="nk-note">{t.demoNote}</span></div>
      <div className="nk-tabs" role="tablist">
        {d.items.map((x, i) => (
          <button key={i} type="button" role="tab" aria-selected={tab === i}
            className={tab === i ? "is-on" : ""} onClick={() => { onUse(); setTab(i); }}>
            {x.channel}
          </button>
        ))}
      </div>
      <article className="nk-post" role="tabpanel">
        {it.title && <h4>{it.title}</h4>}
        <p>{it.text}</p>
      </article>
    </>
  );
}

function Timeline({ d, t, onUse }) {
  const [after, setAfter] = useState(false);
  const rows = after ? d.after : d.before;
  return (
    <>
      <div className="nk-runbar"><span className="nk-note">{t.demoNote}</span></div>
      <div className="nk-toggle" role="group">
        <button type="button" className={!after ? "is-on" : ""} aria-pressed={!after}
          onClick={() => { onUse(); setAfter(false); }}>{t.before}</button>
        <button type="button" className={after ? "is-on" : ""} aria-pressed={after}
          onClick={() => { onUse(); setAfter(true); }}>{t.after}</button>
      </div>
      <ol className={`nk-time${after ? " is-after" : ""}`}>
        {rows.map((r, i) => <li key={`${after}-${i}`}><span>{r.time}</span><p>{r.task}</p></li>)}
      </ol>
    </>
  );
}

function Demo({ demo, t, onUse }) {
  switch (demo.kind) {
    case "inbox": return <Inbox d={demo} t={t} onUse={onUse} />;
    case "leads": return <Leads d={demo} t={t} onUse={onUse} />;
    case "document": return <Document d={demo} t={t} onUse={onUse} />;
    case "report": return <Report d={demo} t={t} onUse={onUse} />;
    case "chat":
      return <Dialogue lines={demo.messages} t={t} onUse={onUse} roleOf={(m) => m.role}
        labelOf={(m) => (m.role === "agent" ? t.agent : t.customer)} after={demo.handoff} afterTitle={t.handoff} />;
    case "call":
      return <Dialogue lines={demo.lines} t={t} onUse={onUse} roleOf={(m) => m.who}
        labelOf={(m) => (m.who === "agent" ? t.agent : t.caller)} after={demo.summary} afterTitle={t.callSummary} />;
    case "content": return <Content d={demo} t={t} onUse={onUse} />;
    default: return <Timeline d={demo} t={t} onUse={onUse} />;
  }
}

function Roi({ main, lang, t }) {
  const huf = lang === "hu";
  const [hours, setHours] = useState(main.hours || 25);
  const [rate, setRate] = useState(huf ? 6000 : 35);
  const money = useMemo(() => new Intl.NumberFormat(t.locale, {
    style: "currency", currency: huf ? "HUF" : "EUR", maximumFractionDigits: 0,
  }), [t.locale, huf]);
  const conv = (v) => (huf ? v : Math.round(v / HUF_PER_EUR / 100) * 100);
  const convMonthly = (v) => (huf ? v : Math.round(v / HUF_PER_EUR / 10) * 10);

  const saving = hours * rate;
  const monthly = main.monthly ? convMonthly(main.monthly) : null;
  const price = main.price ? [conv(main.price[0]), conv(main.price[1])] : null;
  const net = saving - (monthly || 0);
  const payback = price && net > 0 ? Math.max(1, Math.round(((price[0] + price[1]) / 2 / net) * 10) / 10) : null;

  return (
    <section className="nk-card nk-roi">
      <h2>{t.roiTitle}</h2>
      <label className="nk-slider">
        <span>{t.hours}<b>{hours} {t.hoursUnit}</b></span>
        <input type="range" min="5" max="160" step="5" value={hours} onChange={(e) => setHours(+e.target.value)} />
      </label>
      <label className="nk-slider">
        <span>{t.rate}<b>{money.format(rate)}</b></span>
        <input type="range" min={huf ? 2000 : 15} max={huf ? 20000 : 120} step={huf ? 500 : 5} value={rate}
          onChange={(e) => setRate(+e.target.value)} />
      </label>
      <dl className="nk-figs">
        <div className="big"><dt>{t.saving}</dt><dd>{money.format(saving)}</dd></div>
        <div><dt>{t.build}</dt><dd>{price ? `${money.format(price[0])} – ${money.format(price[1])}` : t.onQuote}</dd>
          {main.weeks && <small>{main.weeks[0]}–{main.weeks[1]} {t.weeks}</small>}</div>
        <div><dt>{t.monthly}</dt><dd>{monthly ? money.format(monthly) : t.onQuote}</dd></div>
        {price && <div><dt>{t.payback}</dt><dd>{payback ? `${payback.toLocaleString(t.locale)} ${t.months}` : "—"}</dd></div>}
      </dl>
      {price && !payback && <p className="nk-warn">{t.noPayback}</p>}
      <p className="nk-note">{t.estimate}</p>
    </section>
  );
}

function LiveLink({ href, t, onClick, small }) {
  if (!href) return null;
  const phone = href.startsWith("tel:");
  return (
    <a className={`nk-live${small ? " small" : ""}`} href={href} onClick={onClick}
      {...(phone ? {} : { target: "_blank", rel: "noopener" })}>
      {phone ? t.phoneLive : t.live} →
    </a>
  );
}

export default function Neked() {
  const { slug = "" } = useParams();
  const [{ status, slow, data }, retry] = usePage(slug);
  const lang = data?.lang || "hu";
  const t = textFor(lang);

  useDocumentMeta({
    title: data ? `${data.company} · AXIMBRA` : "AXIMBRA",
    description: data ? t.madeFor(data.company) : "AXIMBRA",
    path: `/neked/${slug}`,
    lang,
    noindex: true,
    translated: false,
  });
  useEffect(() => { document.documentElement.lang = bcp47(lang); }, [lang]);

  const opened = useRef(false);
  const used = useRef(false);
  useEffect(() => {
    if (status === "ready" && !opened.current) { opened.current = true; sendEvent(slug, "open"); }
  }, [status, slug]);
  const onUse = useCallback(() => {
    if (!used.current) { used.current = true; sendEvent(slug, "demo"); }
  }, [slug]);

  if (status !== "ready") {
    const tt = textFor((navigator.language || "hu").slice(0, 2));
    return (
      <div className="nk">
        <header className="nk-top"><a className="nk-logo" href="https://aximbra.hu"><i />AXIMBRA</a></header>
        <main className="nk-state">
          {status === "loading" && (<><div className="nk-spin" aria-hidden="true" /><p>{tt.loading}</p>{slow && <p className="nk-note">{tt.slow}</p>}</>)}
          {status === "gone" && (<><h1>{tt.goneTitle}</h1><p>{tt.goneText}</p><a className="nk-cta" href={`mailto:${EMAIL}`}>{EMAIL}</a></>)}
          {status === "error" && (<><p>{tt.errorText}</p><button type="button" className="nk-run" onClick={retry}>{tt.retry}</button></>)}
        </main>
      </div>
    );
  }

  const { main } = data;
  const mainName = agentName(lang, main.id, main.name);
  const pageUrl = `https://aximbra.hu/neked/${data.slug}`;
  const mailto = `mailto:${EMAIL}?subject=${encodeURIComponent(t.mailSubject(data.company))}&body=${encodeURIComponent(t.mailBody(pageUrl))}`;
  const until = new Date(data.expires_at).toLocaleDateString(t.locale, { year: "numeric", month: "long", day: "numeric" });

  return (
    <div className="nk" data-testid="neked-page">
      <header className="nk-top">
        <a className="nk-logo" href="https://aximbra.hu"><i />AXIMBRA</a>
        <a className="nk-top-cta" href={mailto} onClick={() => sendEvent(slug, "cta")}>{t.cta}</a>
      </header>

      <main className="nk-main">
        <section className="nk-hero">
          <span className="nk-eyebrow">{t.madeFor(data.company)}</span>
          <h1>{data.generic ? t.genericTitle : t.title}</h1>
          {data.summary && <p className="nk-intro">{data.summary}</p>}
        </section>

        {(data.quote || data.work.length > 0) && (
          <section className="nk-card">
            <h2>{t.seen}</h2>
            {data.quote && (
              <figure className="nk-quote">
                <blockquote>„{data.quote.text}”</blockquote>
                <figcaption><a href={data.quote.url} target="_blank" rel="noopener nofollow">— {t.quoteFrom}</a></figcaption>
              </figure>
            )}
            {data.work.length > 0 && <ul className="nk-bullets is-static">{data.work.map((w, i) => <li key={i}>{w}</li>)}</ul>}
          </section>
        )}

        <section className="nk-card nk-agent">
          <span className="nk-eyebrow">{t.recommend}</span>
          <h2 className="nk-agent-name">{mainName}</h2>
          {main.reason && <p>{main.reason}</p>}
          {main.custom_idea && <p><b>{t.idea}:</b> {main.custom_idea}</p>}
          {main.steps.length > 0 && (
            <>
              <h3>{t.how}</h3>
              <ol className="nk-steps">{main.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </>
          )}
          {main.legal && <p className="nk-warn">{t.legal}</p>}
        </section>

        <section className="nk-card nk-demo">
          <h2>{t.demoTitle}</h2>
          <Demo demo={data.demo} t={t} onUse={onUse} />
          <LiveLink href={main.live} t={t} onClick={() => sendEvent(slug, "live")} />
        </section>

        <Roi main={main} lang={lang} t={t} />

        {data.extras.length > 0 && (
          <section className="nk-card">
            <h2>{t.extras}</h2>
            <div className="nk-extras">
              {data.extras.map((e) => (
                <div key={e.id} className="nk-extra">
                  <h3>{agentName(lang, e.id, e.name)}</h3>
                  {e.reason && <p>{e.reason}</p>}
                  <LiveLink href={e.live} t={t} small onClick={() => sendEvent(slug, "live")} />
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="nk-final">
          <h2>{t.ctaTitle}</h2>
          <p>{t.ctaText}</p>
          <a className="nk-cta" href={mailto} onClick={() => sendEvent(slug, "cta")}>{t.cta}</a>
          <p className="nk-note"><a href={`mailto:${EMAIL}`}>{EMAIL}</a></p>
        </section>
      </main>

      <footer className="nk-foot">
        <p>{data.generic ? t.genericFooter : t.footer(data.domain)}</p>
        <p>{t.expires(until)}</p>
        <p><a href="https://aximbra.hu">aximbra.hu</a> · <a href="https://aximbra.hu/impresszum">Impresszum</a> · <a href="https://aximbra.hu/adatkezeles">Adatkezelés</a></p>
      </footer>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { Reveal } from "./Reveal";
import { useLang } from "../i18n";
import { formatPrice, parseToken } from "../money";

/** Mikor olcsobb az agent, mint ugyanazt a munkaidot berkent fizetni.
 *
 *  Minden szam ellenorizheto vagy a latogato allitja be: a bereket a KSH es a
 *  2026-os berminimum adja, az agent arat a kartyak sava (a felso vege, tehat a
 *  rosszabb eset), a havidijat a lenti savok. Ha egy feladatmeretnel nem terul
 *  meg, azt is kiirja - egy kalkulator, ami mindig igent mond, reklam. */

const HORIZON = 24;
// A multi-agent rendszer több ember munkáját veszi át egy folyamaton: egy
// ember heti 40 órájával mérve sosem térülne meg, és ez nem is igaz rá.
// A 6 millió fölötti ár csak a multi-agentnél fordul elő.
const TEAM_PRICE = 5000000;
const MAX_SOLO = 40, MAX_BIG = 80, MAX_TEAM = 200, TEAM_DEFAULT = 80;
const isTeam = (a) => (parseToken(a?.price)?.to || 0) > TEAM_PRICE;

/** Az alapbeállítás az, amennyi munkát egy ilyen méretű agent jellemzően
 *  kivált. Korábban mindegyik heti 10 órával indult: egy 4 milliós
 *  ügyfélszolgálati agent így 266 hónapot mutatott — mintha nem térülne meg,
 *  pedig nem napi két órára építjük, hanem egy teljes állás munkájára.
 *  A csúszkát le lehet húzni; ha akkor nem térül meg, azt is kiírja. */
export function defaultHours(build, team) {
  if (team) return TEAM_DEFAULT;
  if (build <= 400000) return 10;
  if (build <= 1500000) return 20;
  if (build <= 2000000) return 25;
  return 40;
}
// 2 millió fölött az agent egy egész folyamatot visz (ügyfélszolgálat, könyvelés
// előkészítése): ott két ember munkaidejéig engedjük a csúszkát.
export const maxHours = (build, team) => (team ? MAX_TEAM : build > 2000000 ? MAX_BIG : MAX_SOLO);
const HOURS_PER_MONTH = 174; // havi munkaido-alap (HU: 174; DE: ~173, ugyanigy szamolunk)
const WEEKS_PER_MONTH = 52 / 12;
const SZOCHO = 1.13;
// Brutto havi ber, 2026: garantalt berminimum es a KSH januari atlagkeresete.
export const WAGES = { min: 373200, avg: 840600 };

/** Piaconkent mas a ber es a munkaltatoi teher: egy nemet cegvezeto nem a
 *  magyar minimalberrel szamol. Minden forintban, hogy a money.js ugyanugy
 *  valtsa at, mint az agent arat (RATES.EUR = 400).
 *  DE: Mindestlohn 2026 = 13,90 EUR/ora x 174 ora; Destatis 2025. aprilisi
 *  teljes munkaideju atlag 4784 EUR; munkaltatoi tarsadalombiztositasi resz ~21 %. */
const EUR = 400;
export const MARKETS = {
  hu: { wages: WAGES, load: SZOCHO },
  de: { wages: { min: Math.round(13.9 * HOURS_PER_MONTH * EUR), avg: 4784 * EUR }, load: 1.21 },
};
export const marketFor = (lang) => MARKETS[lang] || MARKETS.hu;

/** Havidij az agent aranak felso vege szerint. */
export function monthlyFee(buildPrice) {
  if (buildPrice <= 400000) return 25000;
  if (buildPrice <= 2000000) return 50000;
  return 90000;
}

export function payback({ build, fee, hours, gross, load = SZOCHO }) {
  const hourly = (gross * load) / HOURS_PER_MONTH;
  const staffPerMonth = hourly * hours * WEEKS_PER_MONTH;
  const net = staffPerMonth - fee;
  const month = net > 0 ? build / net : null; // folytonos metszespont
  return { staffPerMonth, month };
}

const niceStep = (max) => {
  const raw = max / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
};

// A rajz a doboz valodi szelessegen keszul, nem nagyitva: igy a tengelyfelirat
// minden kepernyon 11px marad, nem no egyutt az abraval.
const L = 62, R = 14, T = 12, B = 30;

export const Payback = () => {
  const { t, lang } = useLang();
  const p = t.payback;
  const agents = useMemo(
    () => (t.agents || []).filter((a) => parseToken(a.price)?.to),
    [t.agents]
  );
  const [pick, setPick] = useState(0);
  const [hours, setHours] = useState(null);   // null: az agent alapórája
  const [wage, setWage] = useState("min");
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);
  const boxRef = useRef(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (!p || !agents.length) return null;
  const H = W < 520 ? 220 : 280;

  const agent = agents[Math.min(pick, agents.length - 1)];
  const build = parseToken(agent.price).to;
  const fee = monthlyFee(build);
  const team = isTeam(agent);
  const maxH = maxHours(build, team);
  const h = Math.min(hours ?? defaultHours(build, team), maxH);
  const market = marketFor(lang);
  const { staffPerMonth, month } = payback({ build, fee, hours: h, gross: market.wages[wage], load: market.load });

  const agentAt = (m) => build + fee * m;
  const staffAt = (m) => staffPerMonth * m;
  // Forintban ezresre kerekitunk: egy becsles nem lehet pontosabb a bemeneteinel.
  const money = (v, unit = 1000) => formatPrice(String(Math.round(v / unit) * unit), lang, "full");
  const compact = (v) => formatPrice(String(Math.round(v)), lang, "compact");

  const top = Math.max(agentAt(HORIZON), staffAt(HORIZON));
  const step = niceStep(top);
  const yMax = Math.ceil(top / step) * step;
  const x = (m) => L + (m / HORIZON) * (W - L - R);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  const ticks = [];
  for (let v = 0; v <= yMax + 1; v += step) ticks.push(v);

  const within = month != null && month <= HORIZON;
  const whole = within ? Math.max(1, Math.ceil(month)) : null;
  const saved = staffAt(HORIZON) - agentAt(HORIZON);

  const onMove = (e) => {
    const svg = svgRef.current;
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const m = Math.round(((px - L) / (W - L - R)) * HORIZON);
    setHover(m < 0 || m > HORIZON ? null : m);
  };

  const fmt = (s, vals) => s.replace(/\{(\w+)\}/g, (_, k) => vals[k] ?? "");
  const table = [0, 3, 6, 12, 18, 24];

  return (
    <section className="container" id="megterules" data-testid="payback-section">
      <Reveal>
        <span className="tag">{p.tag}</span>
        <h2 className="h-sec">{p.heading}</h2>
        <p className="sub">{p.sub}</p>
      </Reveal>
      <Reveal delay={90}>
        <div className="pb-card">
          <div className="pb-controls">
            <label className="pb-field">
              <span>{p.agentLabel}</span>
              <select value={pick} onChange={(e) => {
                const i = Number(e.target.value);
                setPick(i);
                setHours(null);   // új agentnél az ő jellemző munkamennyiségével indulunk
              }} data-testid="payback-agent">
                {agents.map((a, i) => <option key={a.title} value={i}>{a.title}</option>)}
              </select>
            </label>
            <label className="pb-field">
              <span>{p.hoursLabel}: <b>{h} {p.hoursUnit}</b></span>
              <input type="range" min={team ? 5 : 1} max={maxH} step={team ? 5 : 1} value={h}
                onChange={(e) => setHours(Number(e.target.value))} data-testid="payback-hours" />
            </label>
            <label className="pb-field">
              <span>{p.wageLabel}</span>
              <select value={wage} onChange={(e) => setWage(e.target.value)} data-testid="payback-wage">
                {Object.keys(market.wages).map((k) => (
                  <option key={k} value={k}>{fmt(p.wages[k], { v: money(market.wages[k], 1) })}</option>
                ))}
              </select>
            </label>
          </div>

          {team && p.teamNote && <p className="pb-team-note" data-testid="payback-team-note">{p.teamNote}</p>}

          <div className="pb-result" aria-live="polite" data-testid="payback-result">
            {within ? (
              <>
                <p className="pb-hero">{fmt(p.result, { m: whole })}</p>
                <p className="pb-hero-sub">{fmt(p.resultSub, { s: money(saved, 10000), n: HORIZON })}</p>
              </>
            ) : (
              <p className="pb-hero pb-never">{month == null ? p.never : fmt(p.late, { n: HORIZON })}</p>
            )}
          </div>

          <ul className="pb-legend">
            <li><i className="pb-key pb-key-agent" />{p.seriesAgent}</li>
            <li><i className="pb-key pb-key-staff" />{p.seriesStaff}</li>
          </ul>

          <div ref={boxRef} className="pb-chart-box">
          <svg ref={svgRef} className="pb-chart" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
            aria-label={p.heading} onPointerMove={onMove} onPointerDown={onMove}
            onPointerLeave={() => setHover(null)} data-testid="payback-chart">
            {ticks.map((v) => (
              <g key={v}>
                <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="pb-grid" />
                <text x={L - 8} y={y(v) + 4} textAnchor="end" className="pb-axis">{v === 0 ? "0" : compact(v)}</text>
              </g>
            ))}
            {[0, 6, 12, 18, 24].map((m) => (
              <text key={m} x={x(m)} y={H - 8} textAnchor={m === 0 ? "start" : m === HORIZON ? "end" : "middle"} className="pb-axis">
                {m === 0 ? "0" : fmt(p.monthTick, { m })}
              </text>
            ))}
            <polyline className="pb-line pb-line-staff"
              points={`${x(0)},${y(0)} ${x(HORIZON)},${y(staffAt(HORIZON))}`} />
            <polyline className="pb-line pb-line-agent"
              points={`${x(0)},${y(agentAt(0))} ${x(HORIZON)},${y(agentAt(HORIZON))}`} />
            {within && (
              <g data-testid="payback-cross">
                <line x1={x(month)} x2={x(month)} y1={T} y2={H - B} className="pb-cross" />
                <circle cx={x(month)} cy={y(agentAt(month))} r="5" className="pb-dot pb-dot-cross" />
              </g>
            )}
            <circle cx={x(HORIZON)} cy={y(staffAt(HORIZON))} r="4" className="pb-dot pb-dot-staff" />
            <circle cx={x(HORIZON)} cy={y(agentAt(HORIZON))} r="4" className="pb-dot pb-dot-agent" />
            {hover != null && (
              <g pointerEvents="none">
                <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="pb-hair" />
                <circle cx={x(hover)} cy={y(staffAt(hover))} r="4" className="pb-dot pb-dot-staff" />
                <circle cx={x(hover)} cy={y(agentAt(hover))} r="4" className="pb-dot pb-dot-agent" />
              </g>
            )}
          </svg>
          </div>

          <div className="pb-tip" data-testid="payback-tip" style={{ visibility: hover == null ? "hidden" : "visible" }}>
            {hover != null && (
              <>
                <b>{fmt(p.monthLabel, { m: hover })}</b>
                <span><i className="pb-key pb-key-agent" />{money(agentAt(hover))}</span>
                <span><i className="pb-key pb-key-staff" />{money(staffAt(hover))}</span>
              </>
            )}
          </div>

          <details className="pb-table">
            <summary>{p.tableToggle}</summary>
            <table>
              <thead><tr><th>{p.colMonth}</th><th>{p.seriesAgent}</th><th>{p.seriesStaff}</th></tr></thead>
              <tbody>
                {table.map((m) => (
                  <tr key={m}><td>{m}</td><td>{money(agentAt(m))}</td><td>{money(staffAt(m))}</td></tr>
                ))}
              </tbody>
            </table>
          </details>

          <ul className="pb-notes">
            {p.notes.map((n) => <li key={n}>{fmt(n, { fee: money(fee) })}</li>)}
          </ul>
        </div>
      </Reveal>
    </section>
  );
};

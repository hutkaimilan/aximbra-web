import { useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import { kick, num, pct, signedPct } from "../lib/api";
import { useSlip } from "../lib/slip";

const Metric = ({ label, value, sub, testid }) => (
  <div className="min-w-0 rounded-lg bg-[var(--surface)] border border-[var(--line-soft)] px-2.5 py-2" data-testid={testid}>
    <div className="text-[10px] uppercase tracking-wider faint font-semibold truncate">{label}</div>
    <div className="mono font-bold text-sm mt-0.5 truncate">{value}</div>
    {sub && <div className="text-[11px] faint truncate">{sub}</div>}
  </div>
);

const WinBar = ({ a }) => (
  <div className="bar" aria-label="Győzelmi esélyek">
    <div style={{ width: pct(a.p_home), background: "var(--yellow)" }} />
    <div style={{ width: pct(a.p_draw), background: "var(--tx3)" }} />
    <div style={{ width: pct(a.p_away), background: "var(--blue)" }} />
  </div>
);

function Markets({ m }) {
  const { legs, toggle } = useSlip();
  const on = new Set(legs.map((l) => l.id));
  return (
    <div className="space-y-3" data-testid={`match-${m.id}-markets`}>
      {m.markets.map((mk) => (
        <div key={`${mk.key}-${mk.line}`}>
          <div className="flex items-center gap-2 text-xs font-semibold muted mb-1.5">
            {mk.name}
            {mk.verified === false && <span className="text-[10px] px-1.5 rounded bg-[var(--orange)] text-white" data-testid="market-unverified">nem ellenőrzött – nem kerül szelvényre</span>}
            {mk.calibrated === false && <span className="text-[10px] px-1.5 rounded bg-[var(--accent-s)] faint">nem kalibrált – nem ajánljuk</span>}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {mk.outcomes.map((o) => (
              <button key={o.id} className="odd-btn" data-on={on.has(o.id)} data-testid={`odd-${o.id}`}
                onClick={() => toggle({ id: o.id, label: o.label, market: mk.name, odds: o.odds, match: `${m.home} – ${m.away}`, match_id: m.id })}>
                <span className="text-xs font-semibold w-full truncate">{o.label}</span>
                <span className="flex items-baseline justify-between w-full gap-1">
                  <span className="mono font-bold">{num(o.odds)}</span>
                  <span className="text-[10px] faint mono">{pct(o.prob)} · EV {signedPct(o.ev)}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function MatchCard({ m, onTeam, idx }) {
  const [open, setOpen] = useState(false);
  const a = m.analysis;
  const team = (side) => {
    const id = m.espn?.[side];
    const name = side === "home" ? m.home : m.away;
    return id ? (
      <button className="font-display font-bold text-left hover:text-[var(--yellow)] transition-colors break-words" onClick={() => onTeam(id)}
        data-testid={`match-${m.id}-team-${side}`}>{name}</button>
    ) : <span className="font-display font-bold break-words">{name}</span>;
  };
  return (
    <article className="card p-4 hover:border-[color-mix(in_srgb,var(--yellow)_50%,var(--line))] transition-colors fade-up"
      style={{ animationDelay: `${Math.min(idx, 10) * 30}ms` }} data-testid={`match-${m.id}`}>
      <div className="flex items-center justify-between text-xs faint mb-2">
        <span>{kick(m.kickoff)}</span>
        {!m.espn && <span title="Nincs ESPN-pár: csak piaci becslés">csak piaci becslés</span>}
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="min-w-0">{team("home")}</div>
        <span className="faint text-xs">–</span>
        <div className="min-w-0 text-right">{team("away")}</div>
      </div>
      {a ? (
        <>
          <div className="mt-3"><WinBar a={a} /></div>
          <div className="flex justify-between text-xs mono mt-1" data-testid={`match-${m.id}-1x2`}>
            <span className="text-[var(--yellow)] font-bold">{pct(a.p_home)}</span>
            <span className="faint">X {pct(a.p_draw)}</span>
            <span className="text-[var(--blue)] font-bold">{pct(a.p_away)}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
            <Metric label="Várható gólok" value={`${num(a.xg_home)} – ${num(a.xg_away)}`} testid={`match-${m.id}-xg`} />
            <Metric label="Mindkét csapat lő" value={pct(a.btts)} testid={`match-${m.id}-btts`} />
            <Metric label="Legalább 3 gól" value={pct(a.over25)} testid={`match-${m.id}-over25`} />
            <Metric label="Szöglet / lap" value={`${num(a.corners, 1)} / ${num(a.cards, 1)}`} sub="várható" testid={`match-${m.id}-cc`} />
          </div>
          <div className="flex flex-wrap gap-1.5 mt-3" data-testid={`match-${m.id}-scores`}>
            {a.top_scores.map(([s, p]) => (
              <span key={s} className="text-[11px] mono px-2 py-0.5 rounded-md bg-[var(--accent-s)]">{s} · {pct(p, 1)}</span>
            ))}
          </div>
        </>
      ) : <p className="text-sm faint mt-3">Ehhez a meccshez most nincs becslés.</p>}
      <button className="btn-ghost w-full mt-3 text-xs inline-flex items-center justify-center gap-1.5" onClick={() => setOpen(!open)}
        data-testid={`match-${m.id}-toggle`}>
        {open ? "Kevesebb" : "Indoklás és összes piac"} <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-3 space-y-4" data-testid={`match-${m.id}-details`}>
          {a && (
            <div className="text-sm space-y-1.5" data-testid={`match-${m.id}-reasons`}>
              <div className="font-semibold text-xs uppercase tracking-wider faint flex items-center gap-1.5"><Info size={13} /> Indoklás</div>
              <ul className="space-y-1 muted text-[13px]">{a.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
              {a.model_1x2 && a.market_1x2 && (
                <div className="text-xs mono faint">
                  Modell: {a.model_1x2.map((x) => pct(x)).join(" / ")} · Piac: {a.market_1x2.map((x) => pct(x)).join(" / ")}
                </div>
              )}
              <div className="text-xs faint">Félidő 1X2: {pct(a.ht.p_home)} / {pct(a.ht.p_draw)} / {pct(a.ht.p_away)}</div>
              <div className="text-xs faint">Hiányzók: nincs adat (API-Football kulcs nélkül).</div>
              <div className="text-[11px] faint">Forrás: {a.source}; {a.sims.toLocaleString("hu-HU")} szimuláció; eredmények: ESPN.</div>
            </div>
          )}
          <Markets m={m} />
        </div>
      )}
    </article>
  );
}

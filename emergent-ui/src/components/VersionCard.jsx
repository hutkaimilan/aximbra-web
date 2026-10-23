import { Check, Layers, Ticket, TriangleAlert } from "lucide-react";
import { ft, kick, num, pct, signedPct } from "../lib/api";
import { useSlip } from "../lib/slip";

export const PickRow = ({ pick, showOdds, testid }) => (
  <div className="flex items-start gap-2.5 py-1.5" data-testid={testid}>
    <span className="check-y mt-0.5"><Check size={12} strokeWidth={3.5} /></span>
    <div className="min-w-0 flex-1">
      <div className="font-semibold text-sm leading-tight break-words">{pick.label}</div>
      <div className="text-xs faint leading-tight mt-0.5 break-words">{pick.market}</div>
    </div>
    {showOdds && <span className="mono text-sm font-bold">{num(pick.odds)}</span>}
  </div>
);

export const GroupBlock = ({ g, idx, prefix }) => (
  <div className="py-2.5 border-b border-[var(--line-soft)] last:border-0" data-testid={`${prefix}-group-${idx}`}>
    <div className="flex items-center justify-between gap-2 mb-1">
      <div className="min-w-0">
        <div className="text-sm font-semibold truncate">{g.match}</div>
        <div className="text-[11px] faint truncate">{g.competition} · {kick(g.kickoff)}</div>
      </div>
      <span className="text-[11px] mono muted shrink-0" title="A csoport becsült esélye">{pct(g.prob)}</span>
    </div>
    {g.builder ? (
      <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1">
        <div className="flex items-center justify-between py-1">
          <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--yellow)]">
            <Layers size={13} /> Fogadásépítő
          </span>
          <span className="mono text-sm font-bold" data-testid={`${prefix}-group-${idx}-odds`}>{num(g.odds)}</span>
        </div>
        {g.picks.map((p) => <PickRow key={p.id} pick={p} showOdds={false} />)}
      </div>
    ) : (
      g.picks.map((p) => <PickRow key={p.id} pick={p} showOdds />)
    )}
  </div>
);

export const Totals = ({ odds, stake, payout, prob, ev, lowProb, prefix }) => (
  <div className="space-y-1.5 text-sm" data-testid={`${prefix}-totals`}>
    <div className="flex justify-between items-baseline">
      <span className="muted">Odds összesen</span>
      <span className="mono text-xl font-bold text-[var(--yellow)]" data-testid={`${prefix}-total-odds`}>{num(odds)}</span>
    </div>
    <div className="flex justify-between"><span className="muted">Tét</span><span className="mono">{ft(stake)}</span></div>
    <div className="flex justify-between">
      <span className="muted">Lehetséges nyeremény</span>
      <span className="mono font-semibold" data-testid={`${prefix}-payout`}>{ft(payout)}</span>
    </div>
    <div className="flex justify-between items-center">
      <span className="muted">Becsült esély</span>
      <span className={`mono font-semibold px-2 py-0.5 rounded-md ${lowProb ? "bg-[var(--orange)] text-white" : ""}`}
        data-testid={`${prefix}-prob`}>
        {pct(prob, 1)}{lowProb ? " · 60% alatt" : ""}
      </span>
    </div>
    <div className="flex justify-between">
      <span className="muted">Várható érték</span>
      <span className={`mono font-semibold ${ev >= 0 ? "text-[var(--green)]" : "text-[var(--red)]"}`} data-testid={`${prefix}-ev`}>
        {signedPct(ev)}
      </span>
    </div>
  </div>
);

export default function VersionCard({ v, idx }) {
  const { replace } = useSlip();
  const prefix = `version-${idx}`;
  const toSlip = () =>
    replace(
      v.groups.flatMap((g) => g.picks.map((p) => ({ ...p, match: g.match, match_id: g.match_id }))),
      v.stake,
    );
  return (
    <div className="panel p-4 flex flex-col fade-up" style={{ animationDelay: `${idx * 60}ms` }} data-testid={prefix}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-bold leading-tight">{v.name}</h3>
          <p className="text-xs faint mt-1">{v.desc}</p>
        </div>
        {v.low_prob && (
          <span className="shrink-0 text-[11px] font-bold px-2 py-1 rounded-md bg-[var(--orange)] text-white" data-testid={`${prefix}-low-badge`}>
            60% alatt
          </span>
        )}
      </div>
      <div className="mt-2 flex-1">{v.groups.map((g, i) => <GroupBlock key={g.match_id} g={g} idx={i} prefix={prefix} />)}</div>
      {v.warnings?.map((w) => (
        <div key={w} className="text-xs text-[var(--orange)] flex gap-1.5 mt-2"><TriangleAlert size={14} />{w}</div>
      ))}
      <div className="mt-3 pt-3 border-t border-[var(--line)]">
        <Totals odds={v.odds} stake={v.stake} payout={v.payout} prob={v.prob} ev={v.ev} lowProb={v.low_prob} prefix={prefix} />
        <button className="btn-y w-full mt-3 inline-flex items-center justify-center gap-2" onClick={toSlip} data-testid={`${prefix}-to-slip`}>
          <Ticket size={16} /> Szelvényre
        </button>
      </div>
    </div>
  );
}

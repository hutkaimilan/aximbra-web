import { Ban, Loader2, Trash2, X } from "lucide-react";
import { ft, num } from "../lib/api";
import { useSlip } from "../lib/slip";
import { GroupBlock, Totals } from "./VersionCard";

const QUICK = [500, 1000, 2500, 5000, 10000];

function groupsFromCheck(legs, check) {
  const info = Object.fromEntries((check?.legs || []).map((l) => [l.id, l]));
  const bb = check?.bet_builder || [];
  const byMatch = {};
  legs.forEach((l) => {
    const i = info[l.id] || {};
    const mid = i.match_id || l.match_id;
    byMatch[mid] = byMatch[mid] || { match: i.match || l.match, match_id: mid, competition: i.competition || "", kickoff: i.kickoff, picks: [] };
    byMatch[mid].picks.push({ id: l.id, label: i.label || l.label, market: i.market || l.market, odds: i.odds ?? l.odds, prob: i.prob });
  });
  return Object.values(byMatch).map((g) => {
    const ids = new Set(g.picks.map((p) => p.id));
    const b = bb.find((x) => x.ids.length === ids.size && x.ids.every((i) => ids.has(i)));
    return { ...g, builder: g.picks.length > 1, odds: b ? b.odds : g.picks.length === 1 ? g.picks[0].odds : null, prob: g.picks.length === 1 ? g.picks[0].prob : null };
  });
}

export default function SlipPanel() {
  const { legs, stake, setStake, toggle, clear, check, checking, error } = useSlip();
  const forbidden = new Set((check?.forbidden || []).flat());
  const groups = groupsFromCheck(legs, check);
  return (
    <div className="panel p-4" data-testid="slip-panel">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold">Szelvény <span className="faint text-sm font-medium">({legs.length})</span></h2>
        {legs.length > 0 && (
          <button className="btn-ghost text-xs inline-flex items-center gap-1" onClick={clear} data-testid="slip-clear">
            <Trash2 size={13} /> Törlés
          </button>
        )}
      </div>
      {!legs.length && (
        <p className="text-sm faint py-6 text-center" data-testid="slip-empty">
          Válassz egy kész szelvényt („Szelvényre”), vagy kattints szorzókra a meccskártyákon.
        </p>
      )}
      {groups.map((g, i) => (
        <div key={g.match_id} className="relative">
          <GroupBlock g={{ ...g, odds: g.odds ?? 0, prob: g.prob }} idx={i} prefix="slip" />
          <div className="flex flex-wrap gap-1 -mt-1 mb-2">
            {g.picks.map((p) => (
              <button key={p.id} onClick={() => toggle(p)}
                className={`text-[11px] inline-flex items-center gap-1 px-2 py-0.5 rounded-md border ${forbidden.has(p.id) ? "border-[var(--red)] text-[var(--red)]" : "border-[var(--line)] faint"}`}
                data-testid={`slip-remove-${p.id}`}>
                {forbidden.has(p.id) && <Ban size={11} />} <X size={11} /> {p.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {check?.forbidden?.length > 0 && (
        <div className="rounded-lg border border-[var(--red)] bg-[color-mix(in_srgb,var(--red)_10%,transparent)] p-3 text-sm text-[var(--red)] mb-3"
          data-testid="slip-forbidden">
          <b>Kötéstiltás:</b> a TippmixPro szerint {check.forbidden.length} tippár nem köthető együtt (pirossal jelölve). Vedd ki az egyiket.
        </div>
      )}
      {legs.length > 0 && (
        <div className="pt-3 border-t border-[var(--line)] space-y-3">
          <div>
            <span className="text-[11px] uppercase tracking-wider font-semibold faint">Tét (Ft)</span>
            <input className="field mono mt-1" type="number" min={check?.min_stake || 100} value={stake}
              onChange={(e) => setStake(Number(e.target.value))} data-testid="slip-stake" />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {QUICK.map((q) => (
                <button key={q} className="chip text-xs" data-on={Number(stake) === q} onClick={() => setStake(q)} data-testid={`slip-quick-${q}`}>
                  {q.toLocaleString("hu-HU")}
                </button>
              ))}
            </div>
          </div>
          {checking && <div className="text-xs faint inline-flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> TippmixPro-ellenőrzés…</div>}
          {error && <div className="text-xs text-[var(--red)]" data-testid="slip-error">{error}</div>}
          {check && check.odds != null && (
            <Totals odds={check.odds} stake={check.stake} payout={check.payout} prob={check.prob} ev={check.ev}
              lowProb={check.prob != null && check.prob < 0.6} prefix="slip" />
          )}
          {check?.warnings?.map((w) => <div key={w} className="text-xs text-[var(--orange)]" data-testid="slip-warning">{w}</div>)}
          {check && (
            <div className={`text-xs font-semibold ${check.ok ? "text-[var(--green)]" : "text-[var(--orange)]"}`} data-testid="slip-status">
              {check.ok ? `A TippmixPro elfogadja (min. tét ${ft(check.min_stake)}).` : `Így nem köthető (min. tét ${ft(check.min_stake)}, max. 20 esemény).`}
            </div>
          )}
          <p className="text-[11px] faint">
            Szorzók: TippmixPro{check?.stale ? " (elavult!)" : ""}. Fogadásépítő-szorzó a TippmixPro saját ára. Össz-odds: {num(check?.odds)}.
          </p>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { api, errText, num, shortDate } from "../lib/api";

const RES = { GY: "bg-[var(--green)]", D: "bg-[var(--yellow)] text-[var(--on-yellow)]", V: "bg-[var(--red)]" };

const Badge = ({ r }) => (
  <span className={`inline-flex w-7 h-6 items-center justify-center rounded text-[11px] font-bold text-white ${RES[r]}`}>{r}</span>
);

const avg = (xs) => {
  const v = xs.filter((x) => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
};

export default function TeamSheet({ teamId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!teamId) return;
    setData(null);
    setError(null);
    api.team(teamId).then(setData).catch((e) => setError(errText(e)));
  }, [teamId]);
  const mine = (r, arr) => (arr?.[0] == null ? null : r.home_id === teamId ? arr[0] : arr[1]);
  return (
    <Sheet open={!!teamId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto bg-[var(--surface)] text-[var(--tx)] border-[var(--line)]" data-testid="team-sheet">
        <SheetHeader>
          <SheetTitle className="text-2xl font-display text-left" data-testid="team-name">{data?.name || "Csapat"}</SheetTitle>
          <SheetDescription className="text-left faint">Utolsó 15 meccs minden sorozatból (ESPN)</SheetDescription>
        </SheetHeader>
        {!data && !error && <div className="py-10 flex justify-center"><Loader2 className="animate-spin" /></div>}
        {error && <p className="text-sm text-[var(--red)] mt-4" data-testid="team-error">{error}</p>}
        {data && (
          <div className="mt-4 space-y-5">
            <div className="flex gap-1 flex-wrap" data-testid="team-form">{data.form.map((r, i) => <Badge key={i} r={r} />)}</div>
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                ["Gól / meccs", avg(data.results.map((r) => Number(r.score.split("–")[r.home_id === teamId ? 0 : 1])))],
                ["Szöglet / meccs", avg(data.results.map((r) => mine(r, r.corners)))],
                ["Lap / meccs", avg(data.results.map((r) => mine(r, r.cards)))],
              ].map(([l, v]) => (
                <div key={l} className="card py-2"><div className="text-[10px] uppercase faint">{l}</div><div className="mono font-bold">{num(v, 2)}</div></div>
              ))}
            </div>
            {data.strength && (
              <p className="text-xs faint">Modell-erő: támadás {num(data.strength.att)}, védekezés {num(data.strength.def)} (log-skála, liga: {data.strength.league}).</p>
            )}
            <div className="space-y-1.5" data-testid="team-results">
              {data.results.map((r) => (
                <div key={r.date + r.home} className="card px-3 py-2 flex items-center gap-2 text-sm">
                  <Badge r={r.result} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate"><span className={r.home_id === teamId ? "font-semibold" : ""}>{r.home}</span> – <span className={r.away_id === teamId ? "font-semibold" : ""}>{r.away}</span></div>
                    <div className="text-[11px] faint truncate">{shortDate(r.date)} · {r.competition} · szöglet {r.corners?.[0] ?? "–"}–{r.corners?.[1] ?? "–"} · lap {r.cards?.[0] ?? "–"}–{r.cards?.[1] ?? "–"}</div>
                  </div>
                  <span className="mono font-bold">{r.score}</span>
                </div>
              ))}
            </div>
            <div>
              <h4 className="font-semibold text-sm mb-2">Következő meccsek</h4>
              {data.upcoming.length ? data.upcoming.map((u) => (
                <div key={u.date + u.home} className="text-sm muted py-1">{shortDate(u.date)} · {u.home} – {u.away} <span className="faint text-xs">({u.competition})</span></div>
              )) : <p className="text-xs faint">Nincs adat.</p>}
            </div>
            <p className="text-xs faint" data-testid="team-injuries">{data.injuries_note}</p>
            {data.error && <p className="text-xs text-[var(--orange)]">{data.error}</p>}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

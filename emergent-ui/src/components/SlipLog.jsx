import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errText, ft, num, pct, shortDate, signedPct } from "../lib/api";
import { CalChart } from "./Accuracy";

const STATUS = { open: ["nyitott", "bg-[var(--accent-s)]"], won: ["nyert", "bg-[var(--green)] text-white"],
  lost: ["vesztett", "bg-[var(--red)] text-white"], void: ["érvénytelen", "bg-[var(--tx3)] text-white"] };

const Kpi = ({ l, v, s, testid }) => (
  <div className="panel p-4" data-testid={testid}>
    <div className="text-[11px] uppercase tracking-wider faint font-semibold">{l}</div>
    <div className="mono text-2xl font-bold mt-1 text-[var(--yellow)]">{v}</div>
    {s && <div className="text-xs faint mt-1">{s}</div>}
  </div>
);

export default function SlipLog() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.log().then(setD).catch((e) => setError(errText(e)));
  }, []);
  if (error) return <div className="panel p-4 text-[var(--red)]" data-testid="log-error">{error}</div>;
  if (!d) return <div className="panel p-8 muted">Betöltés…</div>;
  return (
    <section className="space-y-5" data-testid="log-view">
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold">Szelvény Napló</h1>
        <p className="text-sm muted mt-1 max-w-2xl">
          Minden ajánlott szelvény mentve (időpont, lábak bettingOfferId-val, szorzók, becsült esély, várható érték), a meccsek után automatikusan kiértékelve.
          Halmozott eredmény {d.unit} Ft-os egységtéttel.
        </p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi l="Mentett szelvény" v={d.total} s={`${d.open} nyitott, ${d.void} érvénytelen`} testid="log-kpi-total" />
        <Kpi l="Kiértékelt / nyert" v={`${d.settled} / ${d.won}`} s={`várt nyerés: ${num(d.expected_wins, 1)}`} testid="log-kpi-settled" />
        <Kpi l="Halmozott eredmény" v={ft(d.pl)} s={`tét összesen ${ft(d.staked)}`} testid="log-kpi-pl" />
        <Kpi l="Várt eredmény (EV)" v={ft(d.expected_pl)} s="a becsült esélyek szerint" testid="log-kpi-ev" />
      </div>
      {d.settled === 0 && (
        <div className="panel p-4 text-sm muted" data-testid="log-empty">Még nincs kiértékelt szelvény: a görbék a meccsek lejátszása után telnek meg.</div>
      )}
      {d.bins.length > 0 && (
        <div className="panel p-4" data-testid="log-bins">
          <h2 className="font-bold">Becsült vs. valódi találati arány esélysávonként</h2>
          <CalChart bins={d.bins} testid="log-cal-chart" />
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3 text-xs">
            {d.bins.map((b) => (
              <div key={b.lo} className="card px-2 py-1.5 mono">{Math.round(b.lo * 100)}–{Math.round(b.hi * 100)}%: becs. {pct(b.pred)} / valós {pct(b.obs)} <span className="faint">(n={b.n})</span></div>
            ))}
          </div>
        </div>
      )}
      {d.series.length > 0 && (
        <div className="panel p-4" data-testid="log-pl">
          <h2 className="font-bold">Halmozott eredmény ({d.unit} Ft / szelvény)</h2>
          <div className="h-64 mt-2">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 256 }}>
              <LineChart data={d.series.map((p, i) => ({ i: i + 1, pl: p.pl }))} margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
                <CartesianGrid stroke="var(--line-soft)" />
                <XAxis dataKey="i" stroke="var(--tx3)" fontSize={11} />
                <YAxis stroke="var(--tx3)" fontSize={11} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)" }} formatter={(v) => [ft(v), "eredmény"]} />
                <Line dataKey="pl" stroke="var(--yellow)" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      <div className="panel p-4" data-testid="log-recent">
        <h2 className="font-bold mb-3">Legutóbbi szelvények</h2>
        <div className="space-y-2">
          {d.recent.map((r) => (
            <div key={r.id} className="card px-3 py-2" data-testid={`log-row-${r.id}`}>
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-semibold truncate">{r.name}</span>
                <span className={`text-[11px] font-bold px-2 py-0.5 rounded ${STATUS[r.status][1]}`}>{STATUS[r.status][0]}</span>
              </div>
              <div className="text-xs faint mt-0.5 mono">
                {shortDate(r.created_at)} · odds {num(r.odds)} · esély {pct(r.prob, 1)} · EV {signedPct(r.ev)}
              </div>
              <div className="text-xs muted mt-1 break-words">
                {r.groups.map((g) => `${g.match}: ${g.picks.map((p) => p.label).join(" + ")}`).join(" · ")}
              </div>
            </div>
          ))}
          {!d.recent.length && <p className="text-sm faint">Még nincs mentett szelvény.</p>}
        </div>
      </div>
    </section>
  );
}

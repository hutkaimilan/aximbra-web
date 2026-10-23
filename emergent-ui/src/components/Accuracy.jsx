import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errText, num, pct } from "../lib/api";

export const CalChart = ({ bins, testid }) => {
  const data = bins.map((b) => ({ x: Math.round(b.pred * 100), modell: Math.round(b.obs * 100), ideal: Math.round(b.pred * 100) }));
  return (
    <div className="h-72" data-testid={testid}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 288 }}>
        <LineChart data={data} margin={{ left: -10, right: 10, top: 5, bottom: 5 }}>
          <CartesianGrid stroke="var(--line-soft)" />
          <XAxis dataKey="x" type="number" domain={[0, 100]} unit="%" stroke="var(--tx3)" fontSize={11} />
          <YAxis domain={[0, 100]} unit="%" stroke="var(--tx3)" fontSize={11} />
          <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)" }}
            formatter={(v, n) => [`${v}%`, n === "modell" ? "tényleges" : "ideális"]} labelFormatter={(l) => `becsült ${l}%`} />
          <Line dataKey="ideal" stroke="var(--tx3)" strokeDasharray="4 4" dot={false} isAnimationActive={false} />
          <Line dataKey="modell" stroke="var(--yellow)" strokeWidth={2.5} dot={{ r: 4, fill: "var(--yellow)" }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

function MarketTable({ mk, sel, onSel, prefix }) {
  return (
    <div className="overflow-x-auto -mx-4 px-4">
      <table className="w-full text-sm min-w-[640px] [&_td]:px-2 [&_th]:px-2" data-testid={`${prefix}-table`}>
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider faint">
            <th className="py-2">Piac</th><th>Tippek</th><th>Brier</th><th>Alap Brier</th><th>Log-loss</th><th>ECE</th><th>Max. eltérés</th><th>Leképezés</th><th>Állapot</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(mk).map(([k, v]) => (
            <tr key={k} className={`border-t border-[var(--line-soft)] cursor-pointer hover:bg-[var(--accent-s)] ${sel === k ? "bg-[var(--accent-s)]" : ""}`}
              onClick={() => onSel(k)} data-testid={`${prefix}-row-${k}`}>
              <td className="py-2 font-semibold">{v.name}</td>
              <td className="mono">{v.n.toLocaleString("hu-HU")}</td>
              <td className="mono">{num(v.brier, 4)}</td>
              <td className="mono faint">{num(v.base_brier, 4)}</td>
              <td className="mono">{num(v.logloss, 4)}</td>
              <td className="mono">{pct(v.ece, 1)}</td>
              <td className="mono">{pct(v.maxdev, 1)} <span className="faint">/ {pct(v.dev_max, 0)}</span></td>
              <td className="faint text-xs">{v.mapping}{v.mapping === "hőmérséklet" ? ` ${num(v.temperature, 2)}` : ""}</td>
              <td>
                <span className={`text-[11px] font-bold px-2 py-0.5 rounded ${v.calibrated ? "bg-[var(--green)] text-white" : "bg-[var(--orange)] text-white"}`}>
                  {v.calibrated ? "kalibrált" : "nem ajánljuk"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MarketSection({ title, desc, mk, prefix }) {
  const [sel, setSel] = useState("bb");
  const cur = mk[sel] || Object.values(mk)[0];
  return (
    <div className="panel p-4 space-y-4" data-testid={prefix}>
      <div>
        <h2 className="text-base md:text-lg font-bold">{title}</h2>
        <p className="text-xs faint mt-1">{desc}</p>
      </div>
      <MarketTable mk={mk} sel={sel} onSel={setSel} prefix={prefix} />
      <div>
        <h3 className="font-semibold text-sm">Kalibrációs görbe: {cur.name}</h3>
        <p className="text-xs faint mb-2">Vízszintesen a becsült esély (10%-os sávok átlaga), függőlegesen a tényleges találati arány; az átló a tökéletes.</p>
        <CalChart bins={cur.bins} testid={`${prefix}-chart`} />
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3 text-xs">
          {cur.bins.map((b) => (
            <div key={b.lo} className="card px-2 py-1.5 mono">{Math.round(b.lo * 100)}–{Math.round(b.hi * 100)}%: {pct(b.obs, 1)} <span className="faint">(n={b.n})</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BlendSection({ b }) {
  if (!b?.leagues || !Object.keys(b.leagues).length) return null;
  return (
    <div className="panel p-4" data-testid="blend-section">
      <h2 className="text-base md:text-lg font-bold">Piaci keverési súly</h2>
      <p className="text-xs faint mt-1">
        Forrás: {b.source}; évadok: {b.seasons.join(", ")}. A súly (w) ligánként a  w·piac + (1−w)·modell  keverék log-lossát
        minimalizálja (1X2 + gólszám 2,5). BL/EL-ben a két csapat hazai ligájának átlagos súlya.
      </p>
      <div className="overflow-x-auto -mx-4 px-4 mt-3">
        <table className="w-full text-sm min-w-[600px] [&_td]:px-2 [&_th]:px-2" data-testid="blend-table">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider faint">
              <th className="py-2">Liga</th><th>Párosított</th><th>Súly (w)</th><th>Csak 1X2</th><th>B365 záróval</th><th>Log-loss modell</th><th>piac</th><th>keverék</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(b.leagues).map(([lg, v]) => (
              <tr key={lg} className="border-t border-[var(--line-soft)]" data-testid={`blend-row-${lg}`}>
                <td className="py-2 font-semibold">{lg} <span className="faint text-xs">({v.code})</span></td>
                <td className="mono">{v.matched}/{v.rows}</td>
                <td className="mono font-bold text-[var(--yellow)]">{num(v.weight, 2)}</td>
                <td className="mono">{num(v.weight_1x2_only, 2)}</td>
                <td className="mono">{num(v.weight_b365, 2)}</td>
                <td className="mono">{num(v.logloss_model, 4)}</td>
                <td className="mono">{num(v.logloss_market, 4)}</td>
                <td className="mono">{num(v.logloss_blend, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {Object.values(b.leagues).every((v) => v.weight >= 0.99) && (
        <p className="text-xs text-[var(--orange)] mt-3">
          Eredmény: a záró piaci ár minden ligában jobb becslés, a modell hozzákeverése nem javít (w = 1). A szelvénykészítő ezért gólpiacokon a piaci árból
          levezetett, kalibrált eloszlást használja; a modell a meccsadatok nélküli piacokon (szöglet, lap) és a csak modellel becsülhető meccseken számít.
        </p>
      )}
      {b.errors?.length > 0 && <p className="text-xs text-[var(--orange)] mt-2">{b.errors.join("; ")}</p>}
    </div>
  );
}

export default function Accuracy() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.accuracy().then(setD).catch((e) => setError(errText(e)));
  }, []);
  if (error) return <div className="panel p-4 text-[var(--red)]">{error}</div>;
  if (!d) return <div className="panel p-8 muted">Betöltés…</div>;
  if (!d.ready) return <div className="panel p-8 muted" data-testid="accuracy-pending">A visszamérés fut: {d.status}</div>;
  const one = d.markets["1x2"];
  return (
    <section className="space-y-5" data-testid="accuracy-view">
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold">Mennyire pontos?</h1>
        <p className="text-sm muted mt-1 max-w-2xl">
          Visszamérés hetente újraillesztett modellel, mindig csak a meccs előtti adatokból. Kalibrált, ha ECE ≤ {pct(d.rules.ece_max, 0)}, a legalább {d.rules.bin_min} tippes
          sávokban az eltérés a piac határa alatt van (Fogadásépítő: 3%), és a Brier nem rosszabb az alapgyakoriságnál.
        </p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ["Brier (1X2, 3 kimenet)", num(one.brier_multi, 3), "0 = tökéletes; egyenletes tipp 0,667"],
          ["Log-loss (1X2)", num(one.logloss_multi, 3), "kisebb a jobb; egyenletes 1,099"],
          ["Legvalószínűbb 1X2 talált", pct(one.accuracy, 1), "a modell favoritja nyert"],
          ["Tesztelt meccs (modell)", d.n_matches.toLocaleString("hu-HU"), `${d.seconds} mp alatt`],
        ].map(([l, v, s]) => (
          <div key={l} className="panel p-4">
            <div className="text-[11px] uppercase tracking-wider faint font-semibold">{l}</div>
            <div className="mono text-2xl font-bold mt-1 text-[var(--yellow)]">{v}</div>
            <div className="text-xs faint mt-1">{s}</div>
          </div>
        ))}
      </div>
      <BlendSection b={d.blend} />
      {d.live && (
        <MarketSection prefix="live-markets" mk={d.live.markets}
          title={`Élő folyamat: piac + modell keverék (${d.live.seasons.join(", ")}, ${d.live.n_matches} meccs)`}
          desc={`${d.live.desc} Ez dönti el, mely piac kerülhet szelvényre.`} />
      )}
      <MarketSection prefix="model-markets" mk={d.markets}
        title={`Csak a modell (${Object.entries(d.per_season).map(([k, v]) => `${k}: ${v}`).join(", ")} meccs)`}
        desc="A Dixon–Coles/szöglet/lap modell önmagában, piaci ár nélkül." />
      <ul className="text-xs muted space-y-1">{d.notes.map((n) => <li key={n}>• {n}</li>)}</ul>
    </section>
  );
}

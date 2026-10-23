import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { api, COMPS, dayLabel, errText } from "../lib/api";
import { buildCombo, COMBO_NAME } from "../lib/combo";
import VersionCard from "./VersionCard";

// A szerver „Győztesek" és „Gólok" szelvénye helyett egy összevont „Győztes + gólok" (lib/combo.js).
const MERGED = new Set(["win", "goals"]);

const MODES = [
  { v: "auto", l: "Automatikus (60%)" },
  { v: "70", l: "legalább 70%" },
  { v: "80", l: "legalább 80%" },
  { v: "0", l: "60% alatti is" },
];

const Field = ({ label, children }) => (
  <label className="block min-w-0">
    <span className="text-[11px] uppercase tracking-wider font-semibold faint">{label}</span>
    <div className="mt-1">{children}</div>
  </label>
);

export default function Builder({ fixedComp, stateVersion }) {
  const [comps, setComps] = useState(fixedComp ? [fixedComp] : COMPS.map((c) => c.key));
  const [start, setStart] = useState("");
  const [days, setDays] = useState(1);
  const [stake, setStake] = useState(1000);
  const [target, setTarget] = useState("");
  const [mode, setMode] = useState("auto");
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [combo, setCombo] = useState(null);      // { version, notes } | null
  const [comboBusy, setComboBusy] = useState(false);
  const seq = useRef(0);   // egy régebbi, később beérkező számolás ne írja felül az újabbat
  const tid = fixedComp ? `builder-${fixedComp}` : "builder-main";

  const run = (over = {}) => {
    setLoading(true);
    setError(null);
    const p = { sorozat: comps.join(","), napok: days, tet: stake, esely: mode, ...over };
    if (target) p.cel = target;
    if (start && over.kezd === undefined) p.kezd = start;
    const req = { comps: [...comps], stake, target: target ? Number(String(target).replace(",", ".")) || null : null, mode };
    const my = ++seq.current;
    setCombo(null);
    setComboBusy(true);
    api.slips(p)
      .then(async (r) => {
        if (my !== seq.current) return;
        setRes(r);
        setLoading(false);
        let out;
        try {
          const state = await api.state(false);
          out = await buildCombo({ ...req, state, window: r.window });
        } catch (e) {
          out = { version: null, notes: [`A „${COMBO_NAME}” szelvény most nem készült el: ${errText(e)}`] };
        }
        if (my === seq.current) setCombo(out);
      })
      .catch((e) => my === seq.current && setError(errText(e)))
      .finally(() => { if (my === seq.current) { setLoading(false); setComboBusy(false); } });
  };

  // A szerver változatai, a „Győztesek" és „Gólok" helyén az összevont szelvénnyel.
  const versions = useMemo(() => {
    const out = [];
    let placed = false;
    for (const v of res?.versions || []) {
      if (MERGED.has(v.kind)) {
        if (!placed && combo?.version) out.push(combo.version);
        placed = true;
        continue;
      }
      out.push(v);
    }
    if (!placed && combo?.version) out.splice(Math.min(1, out.length), 0, combo.version);
    return out;
  }, [res, combo]);
  const notes = useMemo(() => [
    ...(res?.notes || []).filter((n) => !/Győztesek|Gólok/.test(n)),
    ...(combo?.notes || []),
  ], [res, combo]);

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateVersion]);

  const matchDays = useMemo(() => res?.window?.match_days || [], [res]);
  const toggleComp = (k) => setComps((cs) => (cs.includes(k) ? (cs.length > 1 ? cs.filter((c) => c !== k) : cs) : [...cs, k]));

  return (
    <section className="space-y-5" data-testid={tid}>
      <div className="panel p-4 sm:p-5">
        {!fixedComp && (
          <div className="flex flex-wrap gap-2 mb-4" data-testid={`${tid}-comps`}>
            {COMPS.map((c) => (
              <button key={c.key} className="chip" data-on={comps.includes(c.key)} onClick={() => toggleComp(c.key)}
                data-testid={`${tid}-comp-${c.key}`}>{c.short}</button>
            ))}
            <button className="chip" onClick={() => setComps(COMPS.map((c) => c.key))} data-testid={`${tid}-comp-all`}>Mind</button>
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <Field label="Kezdőnap">
            <select className="field" value={start || res?.window?.start || ""} onChange={(e) => setStart(e.target.value)} data-testid={`${tid}-start`}>
              {matchDays.map((d) => <option key={d.date} value={d.date}>{`${dayLabel(d.date)} · ${d.matches} meccs`}</option>)}
            </select>
          </Field>
          <Field label="Napok">
            <div className="flex gap-1.5">
              {[1, 2, 3].map((n) => (
                <button key={n} className="chip flex-1 justify-center" data-on={days === n} onClick={() => setDays(n)} data-testid={`${tid}-days-${n}`}>{n}</button>
              ))}
            </div>
          </Field>
          <Field label="Tét (Ft)">
            <input className="field mono" type="number" min={100} step={100} value={stake}
              onChange={(e) => setStake(Number(e.target.value))} data-testid={`${tid}-stake`} />
          </Field>
          <Field label="Célszorzó (opcionális)">
            <input className="field mono" inputMode="decimal" placeholder="pl. 3,5" value={target}
              onChange={(e) => setTarget(e.target.value.replace(/[^0-9.,]/g, ""))} data-testid={`${tid}-target`} />
          </Field>
          <Field label="Esély-mód">
            <select className="field" value={mode} onChange={(e) => setMode(e.target.value)} data-testid={`${tid}-mode`}>
              {MODES.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
            </select>
          </Field>
          <div className="flex items-end col-span-2 md:col-span-1">
            <button className="btn-y w-full inline-flex items-center justify-center gap-2" onClick={() => run()} disabled={loading}
              data-testid={`${tid}-run`}>
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} Szelvények
            </button>
          </div>
        </div>
        {res?.window && (
          <p className="text-xs faint mt-3" data-testid={`${tid}-window`}>
            {res.window.start ? `${dayLabel(res.window.start)} – ${res.window.days} nap, ${res.window.matches} meccs (budapesti idő)` : "Nincs meccsnap."}
          </p>
        )}
      </div>
      {error && <div className="panel p-4 text-sm text-[var(--red)]" data-testid={`${tid}-error`}>{error}</div>}
      {notes.length > 0 && (
        <ul className="text-xs muted space-y-1 px-1" data-testid={`${tid}-notes`}>
          {notes.map((n) => <li key={n}>• {n}</li>)}
        </ul>
      )}
      {loading && !res && <div className="panel p-8 text-center muted text-sm">Szelvények számolása és TippmixPro-ellenőrzése…</div>}
      <div className={`grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4 ${loading ? "opacity-60" : ""}`} data-testid={`${tid}-versions`}>
        {versions.map((v, i) => <VersionCard key={v.name} v={v} idx={i} />)}
        {comboBusy && !loading && !combo && (
          <div className="panel p-6 text-center muted text-sm" data-testid={`${tid}-combo-loading`}>
            „{COMBO_NAME}” szelvény beárazása a TippmixPro-nál…
          </div>
        )}
      </div>
      <p className="text-[11px] faint px-1">
        A becsült esély modellbecslés, nem garancia. A várható érték a TippmixPro árrése miatt jellemzően negatív. A fogadást a TippmixPro-n Te adod le; ez az oldal nem fogad.
      </p>
    </section>
  );
}

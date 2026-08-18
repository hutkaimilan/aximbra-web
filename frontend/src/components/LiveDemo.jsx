import { useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { EMAIL_SAMPLES, LEAD_SAMPLES } from "../data";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CONFIG = {
  email: {
    endpoint: "/demo/email",
    placeholder: "Illeszd be egy beérkező e-mail szövegét…",
    samples: EMAIL_SAMPLES,
    fields: [
      ["kategoria", "Kategória"], ["surgosseg", "Sürgősség"], ["felelos", "Felelős"],
      ["valaszhatarido", "Válaszhatáridő"], ["osszefoglalo", "Összefoglaló", true], ["javasolt_lepes", "Javasolt lépés", true],
    ],
  },
  lead: {
    endpoint: "/demo/lead",
    placeholder: "Írd le pár mondatban a beérkező érdeklődőt…",
    samples: LEAD_SAMPLES,
    fields: [
      ["minosites", "Minősítés"], ["igeny", "Igény"], ["koltsegvetes", "Költségvetés"],
      ["donteshozo", "Döntéshozó"], ["hatarido", "Határidő"], ["indoklas", "Indoklás", true], ["javasolt_lepes", "Javasolt lépés", true],
    ],
  },
};

const sessionId = Math.random().toString(36).slice(2);

export const LiveDemo = ({ type }) => {
  const cfg = CONFIG[type];
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const run = async () => {
    if (!input.trim()) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}${cfg.endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
        body: JSON.stringify({ text: input.slice(0, 4000) }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Valami hiba történt. Próbáld újra később."); }
      else { setResult(data); }
    } catch {
      setError("Nem sikerült elérni a szolgáltatást. Próbáld újra később.");
    } finally { setLoading(false); }
  };

  return (
    <div className="demo-panel" data-testid={`demo-panel-${type}`} onClick={(e) => e.stopPropagation()}>
      <textarea data-testid={`demo-input-${type}`} value={input} maxLength={4000}
        placeholder={cfg.placeholder} onChange={(e) => setInput(e.target.value)} />
      <div className="samples">
        {cfg.samples.map((s, i) => (
          <button key={i} className="sample-btn" data-testid={`demo-sample-${type}-${i}`}
            onClick={() => setInput(s)}>Példa {i + 1}</button>
        ))}
      </div>
      <LiquidButton data-testid={`demo-run-${type}`} onClick={run} disabled={loading || !input.trim()}>
        {loading ? <><span className="spin" /> Elemzés…</> : "Futtatás"}
      </LiquidButton>
      {error && <div className="demo-error" data-testid={`demo-error-${type}`}>{error}</div>}
      {result && (
        <div className="result-grid" data-testid={`demo-result-${type}`}>
          {cfg.fields.map(([key, label, full]) => (
            <div key={key} className={`result-field ${full ? "full" : ""}`}>
              <div className="k">{label}</div>
              <div className="v">{result[key]}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

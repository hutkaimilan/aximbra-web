import { useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ENDPOINT = { email: "/demo/email", lead: "/demo/lead" };
const sessionId = Math.random().toString(36).slice(2);

export const LiveDemo = ({ type }) => {
  const { t } = useLang();
  const d = t.demo;
  const cfg = d[type];
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const run = async () => {
    if (!input.trim()) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}${ENDPOINT[type]}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
        body: JSON.stringify({ text: input.slice(0, 4000) }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || d.error); }
      else { setResult(data); }
    } catch {
      setError(d.error);
    } finally { setLoading(false); }
  };

  return (
    <div className="demo-panel" data-testid={`demo-panel-${type}`} onClick={(e) => e.stopPropagation()}>
      <textarea data-testid={`demo-input-${type}`} value={input} maxLength={4000}
        placeholder={cfg.placeholder} onChange={(e) => setInput(e.target.value)} />
      <div className="samples">
        {cfg.samples.map((s, i) => (
          <button key={i} className="sample-btn" data-testid={`demo-sample-${type}-${i}`}
            onClick={() => setInput(s)}>{d.sample} {i + 1}</button>
        ))}
      </div>
      <LiquidButton data-testid={`demo-run-${type}`} onClick={run} disabled={loading || !input.trim()}>
        {loading ? <><span className="spin" /> {d.loading}</> : d.run}
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

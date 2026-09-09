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
  const [tone, setTone] = useState("hivatalos");
  const [draft, setDraft] = useState(null);
  const [drafting, setDrafting] = useState(false);
  const [copied, setCopied] = useState(false);

  const post = async (path, payload) => {
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || d.error);
    return data;
  };

  const run = async () => {
    if (!input.trim()) return;
    setLoading(true); setError(""); setResult(null); setDraft(null);
    try {
      setResult(await post(ENDPOINT[type], { text: input.slice(0, 4000) }));
    } catch (e) {
      setError(e.message || d.error);
    } finally { setLoading(false); }
  };

  const writeDraft = async (nextTone) => {
    const useTone = nextTone || tone;
    setTone(useTone);
    setDrafting(true); setError(""); setCopied(false);
    try {
      setDraft(await post("/demo/draft", { text: input.slice(0, 4000), tone: useTone }));
    } catch (e) {
      setError(e.message || d.error);
    } finally { setDrafting(false); }
  };

  const copyDraft = async () => {
    try {
      await navigator.clipboard.writeText(draft.valasz);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(d.draft.copyError);
    }
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

      {type === "email" && result && (
        <div className="draft-block" data-testid="demo-draft-block">
          <div className="draft-head">
            <span className="draft-title">{d.draft.title}</span>
            <div className="tone-toggle" role="group" aria-label={d.draft.toneLabel}>
              {["hivatalos", "kozvetlen"].map((tn) => (
                <button key={tn} type="button" data-testid={`demo-tone-${tn}`}
                  className={`tone-btn ${tone === tn ? "active" : ""}`}
                  onClick={() => (draft ? writeDraft(tn) : setTone(tn))}>
                  {d.draft.tones[tn]}
                </button>
              ))}
            </div>
          </div>

          {!draft ? (
            <LiquidButton data-testid="demo-draft-run" onClick={() => writeDraft()} disabled={drafting}>
              {drafting ? <><span className="spin" /> {d.draft.loading}</> : d.draft.run}
            </LiquidButton>
          ) : (
            <div data-testid="demo-draft-result">
              <div className="draft-subject">
                <span className="k">{d.draft.subject}</span>
                <span className="v">{draft.targy}</span>
              </div>
              <pre className="draft-body">{drafting ? d.draft.loading : draft.valasz}</pre>
              <div className="draft-actions">
                <button type="button" className="sample-btn" data-testid="demo-draft-copy" onClick={copyDraft}>
                  {copied ? d.draft.copied : d.draft.copy}
                </button>
                <span className="draft-note">{d.draft.note}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

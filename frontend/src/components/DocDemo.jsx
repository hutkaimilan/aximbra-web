import { useRef, useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";
import docdemo from "../i18n/docdemo";
import { CONTACT, mailto } from "../contact";

/** A dokumentum-elemző élő demója. Minta vagy feltöltött fájl → mezők a
 *  forrásmondattal; amit a dokumentum nem tartalmaz, az „nem található”. */
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const SAMPLES = ["contract_hu", "invoice_en", "quote_hu"];
const FIELDS = ["parties", "subject", "date", "duration", "amount", "payment_terms", "due_date_or_deadline", "termination"];
const ACCEPT = ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";
const MAX_BYTES = 5 * 1024 * 1024;
const sessionId = Math.random().toString(36).slice(2);

const toB64 = (file) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result).split(",")[1] || "");
  r.onerror = () => reject(new Error("read"));
  r.readAsDataURL(file);
});

export const DocDemo = () => {
  const { lang } = useLang();
  const d = { ...docdemo.en, ...(docdemo[lang] || {}) };
  const [sample, setSample] = useState("contract_hu");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const pickFile = (f) => {
    setError(""); setResult(null);
    if (!f) return;
    if (f.size > MAX_BYTES) { setError(d.errors.too_large); return; }
    setFile(f); setSample("");
  };

  const run = async () => {
    setLoading(true); setError(""); setResult(null); setCopied(false);
    try {
      const body = file
        ? { filename: file.name, mime: file.type, data_b64: await toB64(file), lang }
        : { sample, lang };
      const res = await fetch(`${API}/demo/document`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const key = data && typeof data.detail === "string" ? data.detail : "";
        throw new Error(d.errors[key] || (res.status === 429 && data.detail) || d.errors.generic);
      }
      setResult(data);
    } catch (e) {
      setError(e.message || d.errors.generic);
    } finally { setLoading(false); }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(result, null, 2)); setCopied(true); } catch { /* nincs vágólap */ }
  };

  const Field = ({ k, item }) => (
    <div className="result-field doc-field">
      <div className="k">{d.fields[k]}</div>
      {item && item.value
        ? <><div className="v">{item.value}</div><div className="doc-src">{d.source}: „{item.source}”</div></>
        : <div className="v doc-missing">{d.notFound}</div>}
    </div>
  );

  const Src = ({ it }) => <div className="doc-src">{d.source}: „{it.source}”</div>;

  const Obligations = () => (
    <div className="result-field full doc-field">
      <div className="k">{d.fields.key_obligations}</div>
      {result.key_obligations && result.key_obligations.length
        ? <ul className="doc-list">{result.key_obligations.map((it, i) => (
            <li key={i}>
              <div className="v">{it.party && <b className="doc-party">{it.party}: </b>}{it.value}</div>
              <Src it={it} />
            </li>))}</ul>
        : <div className="v doc-missing">{d.none}</div>}
    </div>
  );

  const Risks = () => (
    <div className="result-field full doc-field">
      <div className="k">{d.fields.risks_or_unusual_terms}</div>
      {result.risks_or_unusual_terms && result.risks_or_unusual_terms.length
        ? <ul className="doc-list doc-risks">{result.risks_or_unusual_terms.map((it, i) => (
            <li key={i} className={`doc-risk ${it.severity || ""}`}>
              <div className="v">
                {it.severity && <span className={`doc-sev ${it.severity}`}>{d.severity[it.severity]}</span>}
                {it.value}
              </div>
              {it.why && <div className="doc-why">{it.why}</div>}
              <Src it={it} />
            </li>))}</ul>
        : <div className="v doc-missing">{d.none}</div>}
    </div>
  );

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false);
    pickFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
  };

  return (
    <div className="demo-panel" data-testid="demo-panel-doc" onClick={(e) => e.stopPropagation()}>
      <p className="doc-intro">{d.intro}</p>
      <p className="doc-privacy">{d.privacy}</p>
      <button type="button" className={`doc-drop ${drag ? "drag" : ""} ${file ? "has" : ""}`} data-testid="doc-upload"
        onClick={() => inputRef.current && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}>
        <span className="doc-drop-icon">⬆</span>
        <span className="doc-drop-title">{file ? `${d.picked} ${file.name}` : d.upload}</span>
        <span className="doc-drop-hint">{file ? d.change : d.uploadHint}</span>
      </button>
      <input ref={inputRef} type="file" accept={ACCEPT} hidden
        onChange={(e) => { pickFile(e.target.files && e.target.files[0]); e.target.value = ""; }} />
      <p className="doc-or">{d.orSample}</p>
      <div className="samples">
        {SAMPLES.map((s) => (
          <button key={s} type="button" className={`sample-btn ${sample === s && !file ? "on" : ""}`}
            data-testid={`doc-sample-${s}`} onClick={() => { setSample(s); setFile(null); setResult(null); setError(""); }}>
            {d.samples[s]}
          </button>
        ))}
      </div>
      <LiquidButton data-testid="doc-run" onClick={run} disabled={loading || (!file && !sample)}>
        {loading ? <><span className="spin" /> {d.loading}</> : d.run}
      </LiquidButton>
      {error && <div className="demo-error" data-testid="doc-error">{error}</div>}
      {result && (
        <div className="result-grid" data-testid="doc-result">
          <div className="result-field full doc-field">
            <div className="k">{d.fields.document_type}</div>
            <div className="v">{d.types[result.document_type] || result.document_type}</div>
          </div>
          {result.summary && (
            <div className="result-field full doc-field doc-summary">
              <div className="k">{d.fields.summary}</div>
              <div className="v">{result.summary}</div>
            </div>
          )}
          {FIELDS.map((k) => <Field key={k} k={k} item={result[k]} />)}
          <Risks />
          <Obligations />
          {result.recommendations && result.recommendations.length > 0 && (
            <div className="result-field full doc-field doc-recs">
              <div className="k">{d.fields.recommendations}</div>
              <ul className="doc-list">{result.recommendations.map((r, i) => <li key={i}><div className="v">{r}</div></li>)}</ul>
              <div className="doc-src">{d.recsNote}</div>
            </div>
          )}
          {result.truncated && <div className="result-field full doc-missing">{d.truncated}</div>}
          <div className="doc-actions">
            <button type="button" className="sample-btn" onClick={copy} data-testid="doc-copy">{copied ? `✓ ${d.copied}` : d.copy}</button>
          </div>
        </div>
      )}
      <div className="doc-contact" data-testid="doc-contact">
        <a href={mailto("Dokumentum-elemző")}>✉ {CONTACT.email}</a>
      </div>
    </div>
  );
};

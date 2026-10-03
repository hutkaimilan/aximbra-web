import { useEffect, useRef, useState } from "react";
import "./demos.css";
import { useLang } from "../i18n";
import { useDocumentMeta } from "../seo";

/** Közös építőkockák a négy demóoldalhoz. */

export const reduceMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Egyszer kapcsol be, amikor az elem látszik (animációk indítása). */
export function useInView(threshold = 0.25) {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } },
      { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [threshold, seen]);
  return [ref, seen];
}

/** Beúszó blokk. */
export const Rise = ({ as: Tag = "div", className = "", delay = 0, children, ...rest }) => {
  const [ref, seen] = useInView(0.15);
  return (
    <Tag ref={ref} className={`d-rise ${seen ? "in" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }} {...rest}>
      {children}
    </Tag>
  );
};

/** A demó saját, nyelvenkénti tartalma (hu/en/de; a többi nyelv angolul kapja). */
/** Betűtípus betöltése <link>-kel: a CSS-be tett @import a közös csomag
 *  közepén érvénytelen lenne, a böngésző némán eldobná. */
export function useFonts(href) {
  useEffect(() => {
    if (!href || document.querySelector(`link[data-demo-font="${href}"]`)) return;
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = href; l.dataset.demoFont = href;
    document.head.appendChild(l);
  }, [href]);
}

export function useDemo(content, path) {
  const { t, lang } = useLang();
  const d = content[lang] || content.en;
  // noindex: kitalált vállalkozás ne jelenjen meg a keresőben.
  useDocumentMeta({ title: d.seo.title, description: d.seo.description, path, lang, noindex: true });
  useEffect(() => { window.scrollTo(0, 0); }, []);
  return { d, L: t.demos.labels, lang };
}

/** Bemutató űrlap: nem küld és nem tárol semmit, ezt ki is mondja. */
export const DemoForm = ({ L, cls, fields, submit }) => {
  const [sent, setSent] = useState(false);
  const [ok, setOk] = useState(false);
  if (sent) return <div className={`${cls}-sent`} role="status">{L.sentDemo}</div>;
  return (
    <form className={`${cls}-form`} onSubmit={(e) => { e.preventDefault(); if (ok) setSent(true); }}>
      {fields.map((f) => f.area
        ? <label key={f.name}><span>{f.label}</span><textarea name={f.name} rows={4} required /></label>
        : <label key={f.name}><span>{f.label}</span><input name={f.name} type={f.type || "text"} required /></label>)}
      <label className={`${cls}-consent`}>
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} required />
        <span>{L.consent}</span>
      </label>
      <button type="submit" className={`${cls}-btn solid`} disabled={!ok}>{submit || L.send}</button>
    </form>
  );
};

/** Gépelés-szerű, lépésenként megjelenő csevegés (az AI-agent bemutatója). */
export const ScriptedChat = ({ script, cls, start }) => {
  const [n, setN] = useState(0);
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    if (!start) return;
    if (reduceMotion()) { setN(script.length); return; }
    if (n >= script.length) return;
    const bot = script[n].from === "bot";
    setTyping(bot);
    const id = setTimeout(() => { setTyping(false); setN((x) => x + 1); }, bot ? 1500 : 900);
    return () => clearTimeout(id);
  }, [n, start, script]);
  return (
    <div className={`${cls}-chat`} aria-live="polite">
      {script.slice(0, n).map((m, i) => (
        <div key={i} className={`${cls}-msg ${m.from}`}>{m.text}</div>
      ))}
      {typing && <div className={`${cls}-msg bot typing`}><i /><i /><i /></div>}
    </div>
  );
};

export const money = (v, cur) =>
  cur === "HUF" ? `${String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, " ")} Ft`
    : `${v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;

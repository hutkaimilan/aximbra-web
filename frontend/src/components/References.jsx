import { useState } from "react";
import { Link } from "react-router-dom";
import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

const META = [
  { to: "/demo/etterem", accent: "#B87333" },
  { to: "/demo/szalon", accent: "#2C4A3B" },
  { to: "/demo/rendelo", accent: "#2B6CB0" },
  { to: "/demo/ugyvedi", accent: "#C9A227" },
];

export const References = () => {
  const { t } = useLang();
  const r = t.demos.refs;
  const [copied, setCopied] = useState(-1);

  const copyLink = async (i) => {
    const url = `${window.location.origin}${META[i].to}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = url;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(i);
    setTimeout(() => setCopied((c) => (c === i ? -1 : c)), 1800);
  };

  return (
    <section className="container" id="referenciak" data-testid="references-section">
      <Reveal>
        <span className="tag">{r.tag}</span>
        <h2 className="h-sec">{r.heading}</h2>
        <p className="sub">{r.sub}</p>
      </Reveal>
      <div className="ref-grid">
        {r.cards.map((c, i) => (
          <Reveal key={i} delay={i * 80}>
            <div className="ref-card-wrap" style={{ "--accent": META[i].accent }}>
              <Link to={META[i].to} className="ref-card" data-testid={`ref-card-${i}`}>
                <span className="ref-dot" aria-hidden="true" />
                <span className="ref-tag">{c.tag}</span>
                <div className="ref-title">{c.title}</div>
                <div className="ref-desc">{c.desc}</div>
                <span className="ref-cta">{r.view}</span>
              </Link>
              <button
                type="button"
                className={`ref-copy ${copied === i ? "done" : ""}`}
                data-testid={`ref-copy-${i}`}
                onClick={() => copyLink(i)}
                aria-label={r.copy}
              >
                {copied === i ? r.copied : r.copy}
              </button>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
};

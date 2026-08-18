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
            <Link to={META[i].to} className="ref-card" data-testid={`ref-card-${i}`} style={{ "--accent": META[i].accent }}>
              <span className="ref-dot" aria-hidden="true" />
              <span className="ref-tag">{c.tag}</span>
              <div className="ref-title">{c.title}</div>
              <div className="ref-desc">{c.desc}</div>
              <span className="ref-cta">{r.view}</span>
            </Link>
          </Reveal>
        ))}
      </div>
    </section>
  );
};

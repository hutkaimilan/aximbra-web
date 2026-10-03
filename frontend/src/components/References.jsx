import { Link } from "react-router-dom";
import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

const META = [
  { to: "/demo/fogaszat", accent: "#5FC4B0" },
  { to: "/demo/etterem", accent: "#FF6B2C" },
  { to: "/demo/ugyvedi", accent: "#C9A063" },
  { to: "/demo/webshop", accent: "#C8643B" },
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
            <Link to={META[i].to} className="ref-card" data-testid={`ref-card-${i}`}
              style={{ "--accent": META[i].accent }}
              onClick={() => sessionStorage.setItem("aximbra:return", String(window.scrollY))}>
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

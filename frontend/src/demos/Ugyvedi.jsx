import { useEffect, useState } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";

export default function Ugyvedi() {
  const { t } = useLang();
  const d = t.demos.ugyvedi;
  const L = t.demos.labels;
  const [sent, setSent] = useState(false);
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="law-page demo-page" data-testid="demo-ugyvedi">
      <DemoBar prefix="law" />
      <section className="law-hero">
        <div className="demo-container">
          <div className="law-eyebrow">{d.heroEyebrow}</div>
          <h1 className="law-title">{d.brand}</h1>
          <p className="law-sub">{d.heroSub}</p>
          <a className="law-btn" href="#contact">{d.cta}</a>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="law-h2">{d.timelineTitle}</h2>
          <div className="law-timeline">
            {d.timeline.map((tl, i) => (
              <div key={i} className="law-tl" data-testid={`law-tl-${i}`}>
                <div className="law-tl-y">{tl.year}</div>
                <div className="law-tl-t">{tl.text}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="law-h2">{d.areasTitle}</h2>
          <ul className="law-areas">
            {d.areas.map((a, i) => (
              <li key={i} className="law-area" data-testid={`law-area-${i}`}>
                <span className="n">{String(i + 1).padStart(2, "0")}</span>{a}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="demo-section law-contact" id="contact">
        <div className="demo-container">
          <h2 className="law-h2">{d.contactTitle}</h2>
          <p className="law-sub" style={{ fontSize: 18 }}>{d.contactText}</p>
          <form className="law-form" onSubmit={(e) => { e.preventDefault(); setSent(true); }} data-testid="law-form">
            <input type="text" placeholder={L.name} required data-testid="law-name" />
            <input type="email" placeholder={L.email} required data-testid="law-email" />
            <textarea placeholder={L.message} required data-testid="law-message" />
            <button type="submit" data-testid="law-submit">{L.send}</button>
          </form>
          {sent && <div className="law-sent" data-testid="law-sent">{L.sent}</div>}
          <div className="law-meta">
            <div><div className="law-ci-l">{L.address}</div><div className="law-ci-v">{d.address}</div></div>
            <div><div className="law-ci-l">{L.phone}</div><div className="law-ci-v">{d.phone}</div></div>
            <div><div className="law-ci-l">{L.email}</div><div className="law-ci-v">{d.email}</div></div>
            <div><div className="law-ci-l">{L.hours}</div><div className="law-ci-v">{d.hours}</div></div>
          </div>
        </div>
      </section>

      <footer className="law-footer">© {d.brand} · {d.address}</footer>
    </div>
  );
}

import { useEffect, useState } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";

const HERO_IMG = "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/eec847704c318a0f325a38b753c1380b45dece527d66c3e06926dc5ac70ff3d6.jpeg";

export default function Etterem() {
  const { t } = useLang();
  const d = t.demos.etterem;
  const L = t.demos.labels;
  const [open, setOpen] = useState(0);
  useEffect(() => { window.scrollTo(0, 0); }, []);
  const mailto = `mailto:${d.email}?subject=${encodeURIComponent(d.floating + " — " + d.brand)}`;

  return (
    <div className="rst-page demo-page" data-testid="demo-etterem">
      <DemoBar prefix="rst" />
      <section className="rst-hero">
        <img className="rst-hero-img" src={HERO_IMG} alt="" />
        <div className="rst-hero-in">
          <div className="rst-eyebrow">{d.heroEyebrow}</div>
          <h1 className="rst-title">{d.brand}</h1>
          <p className="rst-sub">{d.heroSub}</p>
          <div className="rst-cta-row">
            <a className="rst-btn solid" href={mailto}>{d.cta}</a>
            <a className="rst-btn ghost" href="#menu">{d.ctaGhost}</a>
          </div>
        </div>
      </section>

      <section className="demo-section" id="menu">
        <div className="demo-container">
          <h2 className="rst-h2">{d.menuTitle}</h2>
          <div className="rst-menu">
            {d.menu.map((m, i) => (
              <div key={i} className={`rst-mi ${open === i ? "open" : ""}`} data-testid={`rst-menu-${i}`}>
                <div className="rst-mi-head" onClick={() => setOpen(open === i ? -1 : i)}>
                  <span className="rst-mi-name">{m.name}</span>
                  <span className="rst-mi-price">{m.price}</span>
                </div>
                <div className="rst-mi-body">{m.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="demo-section rst-about">
        <div className="demo-container">
          <h2 className="rst-h2">{d.aboutTitle}</h2>
          <p className="rst-about-txt">{d.aboutText}</p>
        </div>
      </section>

      <section className="demo-section" id="contact">
        <div className="demo-container">
          <h2 className="rst-h2">{d.contactTitle}</h2>
          <div className="rst-contact-grid">
            <div><div className="rst-ci-l">{L.address}</div><div className="rst-ci-v">{d.address}</div></div>
            <div><div className="rst-ci-l">{L.phone}</div><div className="rst-ci-v">{d.phone}</div></div>
            <div><div className="rst-ci-l">{L.hours}</div><div className="rst-ci-v">{d.hours}</div></div>
          </div>
        </div>
      </section>

      <footer className="rst-footer">© {d.brand} · {d.address} · {L.demo || "demó"}</footer>
      <a className="rst-float" href={mailto} data-testid="rst-float">{d.floating}</a>
    </div>
  );
}

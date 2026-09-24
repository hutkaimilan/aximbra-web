import { useEffect, useState } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";
import { useDocumentMeta } from "../seo";

// Saját kiszolgálású kép. Korábban egy külső CDN-ről jött, ami azóta megszűnt:
// egy referencia-oldal, ami törött képpel nyílik meg, rosszabb, mint a semmi.
const HERO_IMG = "/media/demo/olajfa-hero.jpg";

export default function Etterem() {
  const { t, lang } = useLang();
  const d = t.demos.etterem;
  // noindex: an invented business must not surface in search results.
  useDocumentMeta({ title: d.seo.title, description: d.seo.description,
    path: "/demo/etterem", lang, noindex: true });
  const L = t.demos.labels;
  const [open, setOpen] = useState(0);
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="rst-page demo-page" data-testid="demo-etterem">
      <DemoBar prefix="rst" />
      <section className="rst-hero">
        <img className="rst-hero-img" src={HERO_IMG} alt={d.heroAlt} width="1800" height="1125" />
        <div className="rst-hero-in">
          <div className="rst-eyebrow">{d.heroEyebrow}</div>
          <h1 className="rst-title">{d.brand}</h1>
          <p className="rst-sub">{d.heroSub}</p>
          <div className="rst-cta-row">
            <a className="rst-btn solid" href="#contact">{d.cta}</a>
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

      <footer className="rst-footer">© {d.brand} · {d.address} · {L.demo}</footer>
      <a className="rst-float" href="#contact" data-testid="rst-float">{d.floating}</a>
    </div>
  );
}

import { useEffect, useState } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";

const GALLERY = [
  "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/3a7f67b4356732a7f3d819b1c595c63f72866c4612b69921b2b7edf92d9a421f.jpeg",
  "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/ed4387a941bbe7024415b5daa6a3291347e3d6caf4d6e1ddaf29c4afcfbee545.jpeg",
  "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/dbfeb936d5a7da5f6ad8025e2bc95e590ba7e7172376a6e80c2a87b49dda7cc1.jpeg",
];

export default function Szalon() {
  const { t } = useLang();
  const d = t.demos.szalon;
  const L = t.demos.labels;
  const [lb, setLb] = useState(null);
  useEffect(() => { window.scrollTo(0, 0); }, []);
  const mailto = `mailto:${d.email}?subject=${encodeURIComponent(d.cta + " — " + d.brand)}`;

  return (
    <div className="sln-page demo-page" data-testid="demo-szalon">
      <DemoBar prefix="sln" />
      <section className="sln-hero">
        <div className="demo-container">
          <div className="sln-eyebrow">{d.heroEyebrow}</div>
          <h1 className="sln-title">{d.heroTitle}</h1>
          <p className="sln-sub">{d.heroSub}</p>
          <a className="sln-btn" href={mailto}>{d.cta}</a>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="sln-h2">{d.servicesTitle}</h2>
          <div className="sln-serv">
            {d.services.map((s, i) => (
              <div key={i} className="sln-card" data-testid={`sln-serv-${i}`}>
                <div className="sln-card-t">{s.title}</div>
                <div className="sln-card-d">{s.desc}</div>
                <div className="sln-card-p">{s.price}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="sln-h2">{d.galleryTitle}</h2>
          <div className="sln-gallery">
            {GALLERY.map((g, i) => (
              <img key={i} src={g} alt="" data-testid={`sln-gallery-${i}`}
                style={{ cursor: "zoom-in" }} onClick={() => setLb(g)} />
            ))}
          </div>
        </div>
      </section>

      <section className="demo-section sln-about">
        <div className="demo-container">
          <h2 className="sln-h2">{d.aboutTitle}</h2>
          <p className="sln-about-txt">{d.aboutText}</p>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="sln-h2">{d.contactTitle}</h2>
          <div className="sln-contact-grid">
            <div><div className="sln-ci-l">{L.address}</div><div className="sln-ci-v">{d.address}</div></div>
            <div><div className="sln-ci-l">{L.phone}</div><div className="sln-ci-v">{d.phone}</div></div>
            <div><div className="sln-ci-l">{L.hours}</div><div className="sln-ci-v">{d.hours}</div></div>
          </div>
          <a className="sln-btn" href={mailto} style={{ marginTop: 34 }}>{d.cta}</a>
        </div>
      </section>

      <footer className="sln-footer">© {d.brand} · {d.address}</footer>

      {lb && (
        <div className="sln-lightbox" data-testid="sln-lightbox" onClick={() => setLb(null)}>
          <button className="sln-lb-close" aria-label="Close" data-testid="sln-lightbox-close">×</button>
          <img src={lb} alt="" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

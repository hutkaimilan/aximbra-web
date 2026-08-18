import { useEffect } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";

const GALLERY = [
  "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/ed646b4935ce300b88b3d5f19e8c1aa46aa63c331489d708be18b7a80cf0f06b.jpeg",
  "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/c05fe525304dff5b6f53b388540f52c169e70a75e65c5c93e69ac0b5453be4b3.jpeg",
  "https://static.prod-images.emergentagent.com/jobs/afbc24ab-458f-4a48-8241-485e9d12f0a0/images/e8d9296e507886d85103cf20a9e195792df1fd5481c7d0bf04b0c5a712906415.jpeg",
];

export default function Szalon() {
  const { t } = useLang();
  const d = t.demos.szalon;
  const L = t.demos.labels;
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
            {GALLERY.map((g, i) => <img key={i} src={g} alt="" data-testid={`sln-gallery-${i}`} />)}
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
    </div>
  );
}

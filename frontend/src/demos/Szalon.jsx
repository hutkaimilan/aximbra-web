import { useEffect, useState } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";
import { useDocumentMeta } from "../seo";

// Saját kiszolgálású illusztrációk. A korábbi képek egy külső CDN-en voltak,
// ami megszűnt; SVG, mert a világítódobozban nagyban is élesnek kell maradnia.
const GALLERY = [
  "/media/demo/flora-1.svg",
  "/media/demo/flora-2.svg",
  "/media/demo/flora-3.svg",
];

export default function Szalon() {
  const { t, lang } = useLang();
  const d = t.demos.szalon;
  // noindex: an invented business must not surface in search results.
  useDocumentMeta({ title: d.seo.title, description: d.seo.description,
    path: "/demo/szalon", lang, noindex: true });
  const L = t.demos.labels;
  const [lb, setLb] = useState(null);
  useEffect(() => { window.scrollTo(0, 0); }, []);

  // Escape zarja a nagykepet.
  //
  // Eddig csak a hatter es az X gomb zarta. Egy `aria-modal` panel, ami
  // figyelmen kivul hagyja az Escape-et, csapdanak erzodik: ez az elso,
  // amihez a latogato nyul, es billentyuzettel ez az EGYETLEN kiut.
  useEffect(() => {
    if (!lb) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setLb(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lb]);

  return (
    <div className="sln-page demo-page" data-testid="demo-szalon">
      <DemoBar prefix="sln" />
      <section className="sln-hero">
        <div className="demo-container">
          <div className="sln-eyebrow">{d.heroEyebrow}</div>
          <h1 className="sln-title">{d.heroTitle}</h1>
          <p className="sln-sub">{d.heroSub}</p>
          <a className="sln-btn" href="#contact">{d.cta}</a>
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
          {/* Kitalált márka: rajzolt kép mellett ezt ki is kell mondani, nem
              elég a lap tetején futó demó-sáv. */}
          <p className="sln-gallery-note">{d.galleryNote}</p>
          <div className="sln-gallery">
            {/* Gomb, nem kattintható kép: egy <img onClick> nem fókuszálható és
                billentyűzettel meg sem nyitható, tehát a galéria egy része
                elérhetetlen volt. */}
            {GALLERY.map((g, i) => (
              <button key={i} type="button" className="sln-gallery-item"
                data-testid={`sln-gallery-${i}`} onClick={() => setLb({ src: g, alt: d.galleryAlt[i] })}
                aria-label={`${d.galleryAlt[i]} — ${L.enlarge}`}>
                <img src={g} alt={d.galleryAlt[i]} width="900" height="760"
                  loading="lazy" decoding="async" />
              </button>
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

      <section className="demo-section" id="contact">
        <div className="demo-container">
          <h2 className="sln-h2">{d.contactTitle}</h2>
          <div className="sln-contact-grid">
            <div><div className="sln-ci-l">{L.address}</div><div className="sln-ci-v">{d.address}</div></div>
            <div><div className="sln-ci-l">{L.phone}</div><div className="sln-ci-v">{d.phone}</div></div>
            <div><div className="sln-ci-l">{L.hours}</div><div className="sln-ci-v">{d.hours}</div></div>
          </div>
        </div>
      </section>

      <footer className="sln-footer">© {d.brand} · {d.address}</footer>

      {lb && (
        <div className="sln-lightbox" data-testid="sln-lightbox" role="dialog" aria-modal="true"
          aria-label={`${d.brand} — ${L.enlarge}`} onClick={() => setLb(null)}>
          {/* Saját onClick: eddig csak azért működött, mert az esemény felbugyogott
              a szülőre — egy stopPropagation bárhol a láncban némán elrontotta volna. */}
          <button className="sln-lb-close" type="button" aria-label={L.close}
            data-testid="sln-lightbox-close" onClick={() => setLb(null)}>×</button>
          <img src={lb.src} alt={lb.alt} onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

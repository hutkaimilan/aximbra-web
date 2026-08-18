import { useEffect } from "react";
import "./demos.css";
import { DemoBar } from "./DemoBar";
import { useLang } from "../i18n";
import { Stethoscope, Activity, FlaskConical, HeartPulse, Syringe, ClipboardCheck, UserRound } from "lucide-react";

const ICONS = { stethoscope: Stethoscope, activity: Activity, "flask-conical": FlaskConical, "heart-pulse": HeartPulse, syringe: Syringe, "clipboard-check": ClipboardCheck };

export default function Rendelo() {
  const { t } = useLang();
  const d = t.demos.rendelo;
  const L = t.demos.labels;
  useEffect(() => { window.scrollTo(0, 0); }, []);
  const mailto = `mailto:${d.email}?subject=${encodeURIComponent(d.cta + " — " + d.brand)}`;

  return (
    <div className="med-page demo-page" data-testid="demo-rendelo">
      <DemoBar prefix="med" />
      <section className="med-hero">
        <div className="demo-container">
          <div className="med-eyebrow">{d.heroEyebrow}</div>
          <h1 className="med-title">{d.heroTitle}</h1>
          <p className="med-sub">{d.heroSub}</p>
          <div className="med-cta-row">
            <a className="med-btn" href={mailto}>{d.cta}</a>
            <div className="med-urgent">
              <span className="l">{d.urgentLabel}</span>
              <span className="p">{d.urgentPhone}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="med-h2">{d.servicesTitle}</h2>
          <div className="med-serv">
            {d.services.map((s, i) => {
              const Ic = ICONS[s.icon] || Stethoscope;
              return (
                <div key={i} className="med-si" data-testid={`med-serv-${i}`}>
                  <Ic size={30} strokeWidth={1.5} />
                  <div className="med-si-t">{s.title}</div>
                  <div className="med-si-d">{s.desc}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="demo-section med-about">
        <div className="demo-container">
          <h2 className="med-h2">{d.doctorsTitle}</h2>
          <div className="med-doc">
            {d.doctors.map((doc, i) => (
              <div key={i} className="med-doc-c" data-testid={`med-doc-${i}`}>
                <div className="med-doc-av"><UserRound size={26} strokeWidth={1.5} /></div>
                <div className="med-doc-r">{doc.role}</div>
                <div className="med-doc-f">{doc.focus}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="demo-section">
        <div className="demo-container">
          <h2 className="med-h2">{d.aboutTitle}</h2>
          <p className="med-about-txt">{d.aboutText}</p>
        </div>
      </section>

      <section className="demo-section med-about">
        <div className="demo-container">
          <h2 className="med-h2">{d.contactTitle}</h2>
          <div className="med-contact-grid">
            <div><div className="med-ci-l">{L.address}</div><div className="med-ci-v">{d.address}</div></div>
            <div><div className="med-ci-l">{L.phone}</div><div className="med-ci-v">{d.phone}</div></div>
            <div><div className="med-ci-l">{L.hours}</div><div className="med-ci-v">{d.hours}</div></div>
          </div>
        </div>
      </section>

      <footer className="med-footer">© {d.brand} · {d.address}</footer>
    </div>
  );
}

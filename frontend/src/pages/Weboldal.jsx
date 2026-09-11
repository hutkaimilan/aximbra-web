import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import "./weboldal.css";
import { PricingPackages } from "../components/Pricing";
import { useDocumentMeta } from "../seo";
import { useLang, pathFor } from "../i18n";

/** Weboldalkészítés — külön oldalon.
 *
 *  Két különböző dolgot árulunk: AI agenteket és weboldalakat. Egy lapon
 *  bemutatva az olvasónak kell eldöntenie, melyik cég vagyunk; külön oldalon
 *  mindkettő a saját ígéretével áll. */
export default function Weboldal() {
  const { t, lang } = useLang();
  const p = t.pricing;
  const w = t.webPage;
  useDocumentMeta({
    title: w.seo.title,
    description: w.seo.description,
    path: "/weboldal",
    lang,
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="legal-page web-page">
      <header className="legal-top">
        <Link to={pathFor(lang, "/")} className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main web-main">
        <span className="tag">{p.tag}</span>
        <h1>{p.heading}</h1>
        <p className="legal-lead">{w.lead}</p>

        <PricingPackages />

        <section className="web-block">
          <h2>{w.includedTitle}</h2>
          <ul>
            {w.included.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </section>

        <section className="web-block">
          <h2>{w.agentsTitle}</h2>
          <p>{w.agentsText}</p>
          <p>
            <Link className="legal-link" to={pathFor(lang, "/")}>{w.agentsLink}</Link>
          </p>
        </section>
      </main>
    </div>
  );
}

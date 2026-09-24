import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { useDocumentMeta } from "../seo";
import { useLang, pathFor } from "../i18n";

/**
 * Ami egy nem letezo cimen fogad.
 *
 * Eddig minden ismeretlen cim a fooldalt rajzolta ki, valtozatlan cimmel es
 * 200-as valasszal. Ez "soft 404": a Google ugy latja, hogy tetszoleges sok
 * cimen ugyanaz a lap all, es emiatt az egesz oldalt gyengebben ertekeli - a
 * latogato pedig nem erti, miert a fooldalon kotott ki.
 *
 * A valaszkod statikus kiszolgalonal nem allithato 404-re (egyoldalas
 * alkalmazas), ezert a `noindex` itt nem szepitesi kerdes: ez tartja tavol a
 * keresobol azokat a cimeket, amik nem leteznek.
 */
export default function NotFound() {
  const { t, lang } = useLang();
  const n = t.notFound;

  useDocumentMeta({
    title: `${n.title} | AXIMBRA`,
    description: n.lead,
    path: "/404",
    lang,
    noindex: true,
    translated: false,
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

  const home = pathFor(lang, "/");

  return (
    <div className="legal-page" data-testid="not-found">
      <header className="legal-top">
        <Link to={home} className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main">
        <h1>{n.title}</h1>
        <p>{n.lead}</p>
        <p style={{ marginTop: 28, display: "flex", gap: 18, flexWrap: "wrap" }}>
          <Link to={home}>{n.home}</Link>
          <Link to={`${home === "/" ? "" : home}/#agentek`}>{n.agents}</Link>
        </p>
      </main>
    </div>
  );
}

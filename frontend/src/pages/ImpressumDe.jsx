import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER, CONTROLLER_ADDRESS_DE, LEGAL_UPDATED_DE, PROCESSORS } from "../legal";
import { useDocumentMeta } from "../seo";
import { pathFor } from "../i18n";

/**
 * Az impresszum nemetul (/de/impresszum).
 *
 * Nemet latogatonak a "Impressum" kotelezo es jol lathato kell legyen
 * (DDG 5. §): egy magyar nyelvu lap ott nem teljesiti ezt. Az adatok ugyanabbol
 * a legal.js-bol jonnek, mint a magyar oldalon, igy nem csuszhatnak el.
 */
export default function ImpressumDe({ lang }) {
  useDocumentMeta({
    title: "Impressum | AXIMBRA",
    description: "Angaben zum Betreiber von AXIMBRA: Name, Anschrift, Kontakt und Hosting-Anbieter.",
    path: "/impresszum",
    lang,
    translated: false,
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

  const host = PROCESSORS[0];

  return (
    <div className="legal-page">
      <header className="legal-top">
        <Link to={pathFor(lang, "/")} className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main">
        <h1>Impressum</h1>
        <p className="legal-lead">
          Angaben gemäß § 5 Digitale-Dienste-Gesetz (DDG) für die unter der Marke{" "}
          <b>AXIMBRA</b> angebotene Website und Dienste.
        </p>

        <section>
          <h2>Anbieter</h2>
          <dl className="legal-dl">
            <div><dt>Name</dt><dd>{CONTROLLER.name}</dd></div>
            <div><dt>Anschrift</dt><dd>{CONTROLLER_ADDRESS_DE}</dd></div>
            <div><dt>E-Mail</dt><dd><a href={mailto()}>{CONTACT.email}</a></dd></div>
            <div><dt>Kontaktformular</dt><dd>
              <Link className="legal-link" to={pathFor(lang, "/")}>auf der Startseite, Abschnitt „Kontakt“</Link>
            </dd></div>
            <div><dt>Website</dt><dd>{CONTACT.domain}</dd></div>
            {CONTROLLER.taxNumber && (
              <div><dt>Steuernummer</dt><dd>{CONTROLLER.taxNumber}</dd></div>
            )}
          </dl>
          <p className="legal-note">
            AXIMBRA ist ein Markenname, kein eingetragenes Unternehmen. Website und
            Demo-Systeme werden von {CONTROLLER.name} als natürlicher Person betrieben.
          </p>
        </section>

        <section>
          <h2>Verantwortlich für den Inhalt</h2>
          <p>
            Nach § 18 Abs. 2 Medienstaatsvertrag: {CONTROLLER.name}, {CONTROLLER_ADDRESS_DE}.
          </p>
        </section>

        <section>
          <h2>Hosting</h2>
          <dl className="legal-dl">
            <div><dt>Anbieter</dt><dd>{host.name}</dd></div>
            <div><dt>Serverstandort</dt><dd>{host.whereDe}</dd></div>
            <div><dt>Website</dt><dd>
              <a href="https://railway.com" target="_blank" rel="noopener noreferrer">railway.com</a>
            </dd></div>
          </dl>
        </section>

        <section>
          <h2>Datenschutz</h2>
          <p>
            Die Demo-Systeme auf dieser Website — darunter der E-Mail-Agent und der
            Telefon-Agent — verarbeiten personenbezogene Daten. Was genau, wie lange und
            auf welcher Grundlage, steht in der Datenschutzerklärung:
          </p>
          <p>
            <Link className="legal-link" to={pathFor(lang, "/adatkezeles")}>Datenschutzerklärung →</Link>
          </p>
        </section>

        <section>
          <h2>Verbraucherstreitbeilegung</h2>
          <p>
            Wir richten uns an Unternehmen. Wir sind nicht bereit und nicht verpflichtet,
            an Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.
          </p>
        </section>

        <section>
          <h2>Urheberrecht</h2>
          <p>
            Texte, Grafiken und Quellcode dieser Website sind geistiges Eigentum des
            Betreibers. Die Demo-Seiten unter den Referenzen wurden für erfundene Marken
            erstellt; die dort genannten Namen, Adressen, Preise und Mitarbeitenden sind
            nicht real.
          </p>
        </section>

        <p className="legal-updated">Stand: {LEGAL_UPDATED_DE}</p>
      </main>
    </div>
  );
}

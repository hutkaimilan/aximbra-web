import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER, CONTROLLER_ADDRESS, LEGAL_UPDATED, PROCESSORS } from "../legal";
import { useDocumentMeta } from "../seo";

export default function Impresszum() {
  useDocumentMeta({
    title: "Impresszum | AXIMBRA",
    description:
      "Az AXIMBRA üzemeltetőjének adatai: név, székhely, elérhetőség és a tárhelyszolgáltató.",
    path: "/impresszum",
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

  const host = PROCESSORS[0];

  return (
    <div className="legal-page">
      <header className="legal-top">
        <Link to="/" className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main">
        <h1>Impresszum</h1>
        <p className="legal-lead">
          Az <b>AXIMBRA</b> márkanév alatt elérhető weboldal és szolgáltatások üzemeltetője.
        </p>

        <section>
          <h2>Üzemeltető</h2>
          <dl className="legal-dl">
            <div><dt>Név</dt><dd>{CONTROLLER.name}</dd></div>
            <div><dt>Cím</dt><dd>{CONTROLLER_ADDRESS}</dd></div>
            <div><dt>E-mail</dt><dd><a href={mailto()}>{CONTACT.email}</a></dd></div>
            <div><dt>Weboldal</dt><dd>{CONTACT.domain}</dd></div>
            {CONTROLLER.taxNumber && (
              <div><dt>Adószám</dt><dd>{CONTROLLER.taxNumber}</dd></div>
            )}
          </dl>
          {/* Egy nem létező társaság látszatát kelteni pontosan az a bizalmi
              hiba lenne, amit ez az oldal orvosolni hivatott. */}
          <p className="legal-note">
            Az AXIMBRA márkanév, nem bejegyzett gazdasági társaság. Az oldalt és a
            rajta elérhető bemutató rendszereket {CONTROLLER.name} természetes
            személy üzemelteti.
          </p>
        </section>

        <section>
          <h2>Tárhelyszolgáltató</h2>
          <dl className="legal-dl">
            <div><dt>Szolgáltató</dt><dd>{host.name}</dd></div>
            <div><dt>Kiszolgáló helye</dt><dd>{host.where}</dd></div>
            <div><dt>Weboldal</dt><dd>
              <a href="https://railway.com" target="_blank" rel="noopener noreferrer">railway.com</a>
            </dd></div>
          </dl>
        </section>

        <section>
          <h2>Adatkezelés</h2>
          <p>
            Az oldalon elérhető bemutató rendszerek — köztük az e-mail rendező és a
            telefonos agent — személyes adatokat kezelnek. Hogy pontosan mit, meddig
            és milyen alapon, azt külön oldal írja le:
          </p>
          <p>
            <Link className="legal-link" to="/adatkezeles">Adatkezelési tájékoztató →</Link>
          </p>
        </section>

        <section>
          <h2>Szerzői jog</h2>
          <p>
            Az oldal szövegei, ábrái és forráskódja az üzemeltető szellemi tulajdonát
            képezik. A <Link className="legal-link" to="/">Referenciák</Link> között
            szereplő bemutató oldalak kitalált márkákhoz készültek; az azokon szereplő
            nevek, címek, árak és munkatársak nem valósak.
          </p>
        </section>

        <p className="legal-updated">Utolsó frissítés: {LEGAL_UPDATED}</p>
      </main>
    </div>
  );
}

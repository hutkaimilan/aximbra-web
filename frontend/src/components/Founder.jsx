import { Link } from "react-router-dom";
import { Reveal } from "./Reveal";
import { CONTROLLER } from "../legal";
import { useLang, pathFor } from "../i18n";

/** Ki áll az AXIMBRA mögött.
 *
 *  Ez a szakasz szándékosan nem önéletrajz, és szándékosan nincs benne egyetlen
 *  olyan állítás sem, amit az oldalról ne lehetne ellenőrizni. Egy több milliós
 *  döntésnél az számít, hogy ki felel a munkáért és mi az, amit már el lehet
 *  érni — nem az, hogy hány év tapasztalatot írunk le magunkról. */
export const Founder = () => {
  const { t, lang } = useLang();
  const f = t.founder;
  return (
    <section className="container" id="rolunk" data-testid="founder-section">
      <Reveal>
        <div className="founder">
          <div className="founder-side">
            <span className="tag">{f.tag}</span>
            <h2 className="founder-name">{CONTROLLER.name}</h2>
            <p className="founder-role">{f.role}</p>
            <Link className="founder-link" to={pathFor(lang, "/impresszum")}>{f.imprint}</Link>
          </div>
          <div className="founder-body">
            {f.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
            <ul className="founder-proof">
              {f.proof.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </div>
        </div>
      </Reveal>
    </section>
  );
};

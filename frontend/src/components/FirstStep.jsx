import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

/** A legkisebb következő lépés.
 *
 *  Egy döntésnek ára van azon felül is, amit a számla mutat: ki kell találni,
 *  meg kell védeni mások előtt, és vissza kell csinálni, ha rossz volt. Aki
 *  elsőre ajánlatot kér, az ebből mindhármat megelőlegezi. Ez a szakasz azért
 *  áll közvetlenül a kapcsolatfelvétel előtt, hogy a következő lépés
 *  kicsi legyen és visszafordítható — nem azért, hogy elrejtse a nagyot. */
export const FirstStep = () => {
  const { t } = useLang();
  const f = t.firstStep;
  if (!f) return null;
  return (
    <section className="container" id="elso-lepes" data-testid="firststep-section">
      <Reveal>
        <div className="first-step">
          <div className="first-step-main">
            <span className="tag">{f.tag}</span>
            <h2 className="first-step-h">{f.heading}</h2>
            <p className="first-step-body">{f.body}</p>
          </div>
          <ul className="first-step-points">
            {f.points.map((p, i) => <li key={i} data-testid={`firststep-${i}`}>{p}</li>)}
          </ul>
        </div>
      </Reveal>
    </section>
  );
};

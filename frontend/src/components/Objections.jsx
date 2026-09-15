import { useState } from "react";
import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

/** A kifogások, mielőtt a látogató kimondaná őket.
 *
 *  A retorikában ez a legrégebbi ismert fogás — prolépszisznek hívták, ma
 *  beoltásnak szokás fordítani: az ellenérvet te hozod fel, mielőtt a másik
 *  megtenné. Két dolgot ad. Az egyik, hogy az érv a te megfogalmazásodban
 *  hangzik el, nem az övében. A másik, és ez a fontosabb: aki kimondja a saját
 *  gyenge pontját, arról a másik azt feltételezi, hogy a többit sem titkolja.
 *
 *  Ezért van itt a negyedik kérdés is („mi van, ha egy év múlva abbahagyod”).
 *  Egy húszéves, egyszemélyes műhelynél ez a legnagyobb ki nem mondott
 *  ellenvetés. Kihagyni nem azt jelenti, hogy nem merül fel — csak azt, hogy
 *  nem itt merül fel, hanem a döntés pillanatában, válasz nélkül.
 *
 *  Az első nyitva van. Egy csukott harmonika üres helynek látszik; egy nyitott
 *  megmutatja, milyen hosszúak a válaszok, és hogy tényleg válaszok. */
export const Objections = () => {
  const { t } = useLang();
  const o = t.objections;
  const [open, setOpen] = useState(0);
  if (!o) return null;
  return (
    <section className="container" id="ellenvetesek" data-testid="objections-section">
      <Reveal>
        <span className="tag">{o.tag}</span>
        <h2 className="h-sec">{o.heading}</h2>
        <p className="sub">{o.sub}</p>
      </Reveal>
      <Reveal delay={90}>
        <div className="obj-list">
          {o.items.map((it, i) => {
            const isOpen = open === i;
            return (
              <div key={i} className={`obj ${isOpen ? "obj-open" : ""}`} data-testid={`objection-${i}`}>
                <h3>
                  <button type="button" className="obj-q" aria-expanded={isOpen}
                    aria-controls={`obj-a-${i}`} data-testid={`objection-q-${i}`}
                    onClick={() => setOpen(isOpen ? -1 : i)}>
                    <span className="obj-mark" aria-hidden="true">{isOpen ? "–" : "+"}</span>
                    <span className="obj-text">{it.q}</span>
                  </button>
                </h3>
                <div className="obj-a" id={`obj-a-${i}`} hidden={!isOpen} data-testid={`objection-a-${i}`}>
                  <p>{it.a}</p>
                </div>
              </div>
            );
          })}
        </div>
      </Reveal>
    </section>
  );
};

import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

/** Amit a látogató ellenőrizni tud, mielőtt bármit elhinne.
 *
 *  A lap eddig a legaljára tette azt a négy állítást, amit tényleg meg lehet
 *  nézni — a készítőt bemutató szakaszba. Aki addig nem jutott el, az csak
 *  ígéreteket olvasott. Ez a sáv ezért közvetlenül a nyitány után áll: előbb a
 *  figyelem, rögtön utána az, amiért érdemes tovább olvasni.
 *
 *  Szándékosan nem újabb érv, hanem három feladat. Egy érvet el lehet hinni
 *  vagy nem; egy telefonszámot fel lehet hívni. */
export const Proof = ({ scrollTo }) => {
  const { t } = useLang();
  const p = t.proof;
  if (!p) return null;
  return (
    <section className="container" id="bizonyitek" data-testid="proof-section">
      <Reveal>
        <span className="tag">{p.tag}</span>
        <h2 className="h-sec">{p.heading}</h2>
        <p className="sub">{p.sub}</p>
      </Reveal>
      <div className="proof-grid">
        {p.items.map((it, i) => (
          <Reveal key={it.n} delay={i * 90}>
            <article className="proof-card" data-testid={`proof-${it.n}`}>
              <span className="proof-n">{it.n}</span>
              <h3 className="proof-title">{it.title}</h3>
              <p className="proof-desc">{it.desc}</p>
              <button type="button" className="proof-cta" data-testid={`proof-cta-${it.n}`}
                onClick={() => scrollTo(it.to)}>{it.cta}</button>
            </article>
          </Reveal>
        ))}
      </div>
    </section>
  );
};

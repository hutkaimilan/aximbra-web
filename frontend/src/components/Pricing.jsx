import { PRICING } from "../data";
import { Reveal } from "./Reveal";

export const Pricing = () => (
  <section className="container" id="arak" data-testid="pricing-section">
    <Reveal>
      <span className="tag">Árazás</span>
      <h2 className="h-sec">Nyilvános sávok, nem „kérjen ajánlatot”</h2>
      <p className="sub">
        A bevezetési díj egyszeri, a havidíj a felügyeletet és a modellköltséget fedezi.
        A sáv alja egyszerű eset, a teteje összetett integráció.
      </p>
    </Reveal>
    <Reveal>
      <div className="table">
        <div className="trow head">
          <div>Kategória</div><div>Bevezetés</div><div>Havidíj</div><div>Átfutás</div>
        </div>
        {PRICING.map((p) => (
          <div className="trow" key={p.cat} data-testid={`price-row-${p.cat}`}>
            <div className="c0">{p.cat}</div>
            <div className="cm"><span className="lbl-m">Bevezetés: </span>{p.intro}</div>
            <div className="cm"><span className="lbl-m">Havidíj: </span>{p.monthly}</div>
            <div className="cm"><span className="lbl-m">Átfutás: </span>{p.lead}</div>
          </div>
        ))}
      </div>
    </Reveal>
  </section>
);

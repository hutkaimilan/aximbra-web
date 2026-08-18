import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";

export const Hero = ({ scrollTo }) => {
  const { t } = useLang();
  const h = t.hero;
  return (
    <section className="hero container" id="top" data-testid="hero">
      <div className="eyebrow"><span className="dot" /> {h.eyebrow}</div>
      <h1 className="h1">
        {h.h1[0]}<br />{h.h1[1]}<br /><span className="grad">{h.h1[2]}</span>
      </h1>
      <p className="hero-sub">{h.sub}</p>
      <div className="hero-cta">
        <LiquidButton data-testid="hero-primary" onClick={() => scrollTo("agentek")}>{h.ctaPrimary}</LiquidButton>
        <LiquidButton ghost data-testid="hero-ghost" onClick={() => scrollTo("eset")}>{h.ctaGhost}</LiquidButton>
      </div>
      <div className="stats">
        {h.stats.map(([big, lbl], i) => (
          <div className="stat" key={i}><div className="big">{big}</div><div className="lbl">{lbl}</div></div>
        ))}
      </div>
    </section>
  );
};

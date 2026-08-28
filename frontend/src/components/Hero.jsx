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
      <a className="hero-phone" href="tel:+18024249852" data-testid="hero-phone">
        <span className="hero-phone-live" aria-hidden="true"><span className="dot" /> AI</span>
        <span className="hero-phone-main">
          <span className="hero-phone-num">+1 802 424 9852</span>
          <span className="hero-phone-note">{h.phoneCta.note}</span>
        </span>
      </a>
      <div className="stats">
        {h.stats.map(([big, lbl], i) => (
          <div className="stat" key={i}><div className="big">{big}</div><div className="lbl">{lbl}</div></div>
        ))}
      </div>
    </section>
  );
};

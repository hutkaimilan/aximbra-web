import { LiquidButton } from "./LiquidButton";

export const Hero = ({ scrollTo }) => (
  <section className="hero container" id="top" data-testid="hero">
    <div className="eyebrow"><span className="dot" /> Budapest · AI ügynökség</div>
    <h1 className="h1">
      Nem chatbotot<br />építünk. Hanem<br /><span className="grad">munkatársat.</span>
    </h1>
    <p className="hero-sub">
      Olyan AI agenteket építünk magyar cégeknek, amelyek elvégeznek egy konkrét munkát — leveleket rendeznek,
      érdeklődőt minősítenek, telefont vesznek fel. Nem demót adunk át, hanem működő rendszert, amit mi tartunk életben.
    </p>
    <div className="hero-cta">
      <LiquidButton data-testid="hero-primary" onClick={() => scrollTo("agentek")}>Nézd meg az agenteket</LiquidButton>
      <LiquidButton ghost data-testid="hero-ghost" onClick={() => scrollTo("eset")}>Működés közben</LiquidButton>
    </div>
    <div className="stats">
      <div className="stat"><div className="big">2–4 hét</div><div className="lbl">az első agent</div></div>
      <div className="stat"><div className="big">3 nyelv</div><div className="lbl">HU · EN · ES</div></div>
      <div className="stat"><div className="big">100%</div><div className="lbl">emberi jóváhagyás</div></div>
    </div>
  </section>
);

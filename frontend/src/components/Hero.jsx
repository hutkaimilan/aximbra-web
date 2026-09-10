import { useEffect, useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";
import { CONTACT } from "../contact";

const HeroStatus = ({ s }) => {
  const [status, setStatus] = useState(null); // null = loading

  useEffect(() => {
    let active = true;
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/voice/health`);
        const data = await res.json();
        if (active) setStatus(data);
      } catch {
        if (active) setStatus({ reachable: false, ok: false });
      }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30000);
    return () => { active = false; clearInterval(id); };
  }, []);

  const live = status && status.reachable && status.ok;
  const state = status === null ? "checking" : live ? "online" : "offline";
  const talking = live && typeof status.live === "number" && status.live > 0;

  let label = s.checking;
  let sub = null;
  if (state === "online") {
    label = s.online;
    const parts = [];
    if (typeof status.count === "number") parts.push(`${s.today} ${status.count} ${s.callsUnit}`);
    if (typeof status.live === "number" && status.live > 0) parts.push(`${status.live} ${s.liveUnit}`);
    sub = parts.join(" · ");
  } else if (state === "offline") {
    label = s.offline;
  }

  return (
    <div className={`hero-status ${state} ${talking ? "talking" : ""}`} data-testid="hero-status"
      data-state={state} data-talking={talking ? "true" : "false"} role="status" aria-live="polite">
      <span className="hero-status-dot" aria-hidden="true" />
      <span className="hero-status-label" data-testid="hero-status-label">{label}</span>
      {sub && <span className="hero-status-sub" data-testid="hero-status-sub">{sub}</span>}
    </div>
  );
};

export const Hero = ({ scrollTo }) => {
  const { t } = useLang();
  const h = t.hero;
  return (
    <section className="hero container" id="top" data-testid="hero">
      <div className="hero-top">
        <div className="eyebrow"><span className="dot" /> {h.eyebrow}</div>
        <HeroStatus s={h.status} />
      </div>
      <h1 className="h1">
        {h.h1[0]}<br />{h.h1[1]}<br /><span className="grad">{h.h1[2]}</span>
      </h1>
      <p className="hero-sub">{h.sub}</p>
      <div className="hero-cta">
        <LiquidButton data-testid="hero-primary" onClick={() => scrollTo("agentek")}>{h.ctaPrimary}</LiquidButton>
        <LiquidButton ghost data-testid="hero-ghost" onClick={() => scrollTo("eset")}>{h.ctaGhost}</LiquidButton>
      </div>
      <a className="hero-phone" href={CONTACT.phoneHref} data-testid="hero-phone">
        <span className="hero-phone-live" aria-hidden="true"><span className="dot" /> AI</span>
        <span className="hero-phone-main">
          <span className="hero-phone-num">{CONTACT.phone}</span>
          <span className="hero-phone-note">{h.phoneCta.note}</span>
          {/* A US number on a Budapest agency's site reads as a mismatch unless it
              says what it is: the voice agent's test line, not a support desk. */}
          <span className="hero-phone-origin">{h.phoneCta.origin}</span>
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

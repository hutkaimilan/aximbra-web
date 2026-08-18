import { useEffect, useRef, useState } from "react";
import { STEPS } from "../data";
import { Reveal } from "./Reveal";

export const Process = () => {
  const railRef = useRef(null);
  const [fill, setFill] = useState(0);
  const [active, setActive] = useState(-1);

  useEffect(() => {
    let raf;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = railRef.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        const vh = window.innerHeight;
        const total = r.height;
        const progress = Math.min(1, Math.max(0, (vh * 0.6 - r.top) / total));
        setFill(progress * 100);
        setActive(Math.floor(progress * STEPS.length + 0.15) - 1);
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  return (
    <section className="container" id="folyamat" data-testid="process-section">
      <Reveal>
        <span className="tag">Hogyan dolgozunk</span>
        <h2 className="h-sec">Hat lépés, egy emberi kapuval</h2>
        <p className="sub">
          Az agentek nagy részét agentek építik. Ami nem változik: jóváhagyni ember hagy jóvá —
          nem azért, mert a modell rossz, hanem mert a felelősség nem delegálható.
        </p>
      </Reveal>
      <div className="rail" ref={railRef}>
        <div className="rail-line" />
        <div className="rail-fill" style={{ height: `${fill}%` }} />
        {STEPS.map((s, i) => (
          <div key={s.n} className={`step ${active >= i ? "active" : ""}`} data-testid={`step-${s.n}`}>
            <div className="node">{s.n}</div>
            <h3>{s.title}</h3>
            <p>{s.desc}</p>
            {s.amber && <div className="amber-pill" data-testid="human-gate-pill">{s.amber}</div>}
          </div>
        ))}
      </div>
    </section>
  );
};

import { useState } from "react";
import { Reveal } from "./Reveal";
import { LiveDemo } from "./LiveDemo";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";

const TiltCard = ({ agent, open, onToggle, labels }) => {
  const onMove = (e) => {
    if (open) return;
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.transform = `rotateY(${(px - 0.5) * 14}deg) rotateX(${(0.5 - py) * 14}deg)`;
    el.style.setProperty("--mx", `${px * 100}%`);
    el.style.setProperty("--my", `${py * 100}%`);
  };
  const reset = (e) => { e.currentTarget.style.transform = "rotateY(0) rotateX(0)"; };

  return (
    <div className="card" data-testid={`agent-card-${agent.demo || agent.title}`} onMouseMove={onMove} onMouseLeave={reset}>
      <div className="card-head">
        <div className="card-title">{agent.title}</div>
        <span className={`badge ${agent.live ? "live" : "demo"}`}>
          {agent.live && <span className="dot" />}{agent.badge}
        </span>
      </div>
      <p className="card-desc">{agent.desc}</p>
      <div className="card-meta">
        <span className="price">{agent.price}</span>
        <span className="lead">{agent.lead}</span>
      </div>
      {agent.live && (
        <div className="card-try">
          <LiquidButton ghost data-testid={`agent-try-${agent.demo}`} onClick={onToggle}>
            {open ? labels.tryClose : labels.tryOpen}
          </LiquidButton>
          {open && <LiveDemo type={agent.demo} />}
        </div>
      )}
    </div>
  );
};

export const Agents = () => {
  const { t } = useLang();
  const [open, setOpen] = useState(null);
  const s = t.agentsSection;
  return (
    <section className="container" id="agentek" data-testid="agents-section">
      <Reveal>
        <span className="tag">{s.tag}</span>
        <h2 className="h-sec">{s.heading}</h2>
        <p className="sub">{s.sub}</p>
      </Reveal>
      <div className="grid">
        {t.agents.map((a, i) => (
          <Reveal key={a.demo || i} delay={(i % 3) * 90} className={open === a.demo ? "span-all" : ""}>
            <TiltCard agent={a} labels={s} open={open === a.demo}
              onToggle={() => setOpen(open === a.demo ? null : a.demo)} />
          </Reveal>
        ))}
      </div>
    </section>
  );
};

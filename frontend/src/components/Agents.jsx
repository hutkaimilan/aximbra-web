import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Reveal } from "./Reveal";
import { LiveDemo } from "./LiveDemo";
import EmailAgent from "@/demos/EmailAgent";
import { LiquidButton } from "./LiquidButton";
import { AgentViz } from "./AgentViz";
import { AgentSim } from "./AgentSim";
import sims from "./agentSims";
import { mailto } from "../contact";
import { useLang } from "../i18n";

export const SLUGS = ["email-rendezo", "erdeklodo-minosito", "belso-admin", "kutatasi-monitor", "ugyfelszolgalat", "tartalom", "webshop", "dokumentum-elemzo", "penzugyi", "toborzas", "it-uzemelteto", "multi-agent"];

const TiltCard = ({ agent, open, onToggle, labels, kind, simOn, onSim, quote }) => {
  const simData = sims[kind];
  const slug = SLUGS[kind];
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
    <div className="card" id={`agent-${slug}`} data-testid={`agent-card-${agent.demo || agent.title}`} onMouseMove={onMove} onMouseLeave={reset}>
      <AgentViz kind={kind} />
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
      <LiquidButton as="a" className="card-quote" data-testid={`agent-quote-${kind}`}
        href={mailto(`${quote.subject} – ${agent.title}`)}>
        {quote.label}
      </LiquidButton>
      {agent.live && (
        <div className="card-try">
          <LiquidButton ghost data-testid={`agent-try-${agent.demo}`} onClick={onToggle}>
            {open ? labels.tryClose : labels.tryOpen}
          </LiquidButton>
          {open && (agent.demo === "email" ? <EmailAgent embedded /> : <LiveDemo type={agent.demo} />)}
        </div>
      )}
      {simData && agent.demo !== "email" && (
        <div className="card-try">
          <LiquidButton ghost data-testid={`agent-sim-btn-${kind}`} onClick={onSim}>
            {simOn ? "Bezárás" : "Nézd meg működés közben"}
          </LiquidButton>
          {simOn && <AgentSim data={simData} slug={slug} />}
        </div>
      )}
    </div>
  );
};

/** Ennyi látszik elsőre. A tizenkét kártya telefonon több képernyőnyi görgetés
 *  azelőtt, hogy az olvasó bármi mást látott volna a lapból; a többi egy
 *  gombnyomásra ott van. Külön oldal helyett azért kinyitható, mert az
 *  /agent/:slug hivatkozásoknak akkor is működniük kell, ha olyan kártyára
 *  mutatnak, ami alapból rejtve van. */
const VISIBLE_AT_FIRST = 6;

export const Agents = () => {
  const { t } = useLang();
  const [open, setOpen] = useState(null);
  const [simOpen, setSimOpen] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const { slug } = useParams();
  useEffect(() => {
    if (!slug) return;
    const idx = SLUGS.indexOf(slug);
    if (idx < 0) return;
    if (idx >= VISIBLE_AT_FIRST) setShowAll(true);
    setOpen(null); setSimOpen(idx);
    const tid = setTimeout(() => {
      document.getElementById(`agent-${slug}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 500);
    return () => clearTimeout(tid);
  }, [slug]);
  const s = t.agentsSection;
  return (
    <section className="container" id="agentek" data-testid="agents-section">
      <Reveal>
        <span className="tag">{s.tag}</span>
        <h2 className="h-sec">{s.heading}</h2>
        <p className="sub">{s.sub}</p>
      </Reveal>
      <div className="grid">
        {t.agents.slice(0, showAll ? undefined : VISIBLE_AT_FIRST).map((a, i) => (
          <Reveal key={a.demo || i} delay={(i % 3) * 90} className={(open === a.demo || simOpen === i) ? "span-all" : ""}>
            <TiltCard agent={a} labels={s} kind={i}
              quote={{ label: t.pricing.cta, subject: t.pricing.subjectPrefix }}
              open={open === a.demo}
              onToggle={() => { setSimOpen(null); setOpen(open === a.demo ? null : a.demo); }}
              simOn={simOpen === i}
              onSim={() => { setOpen(null); setSimOpen(simOpen === i ? null : i); }} />
          </Reveal>
        ))}
      </div>
      {!showAll && t.agents.length > VISIBLE_AT_FIRST && (
        <div className="agents-more">
          <button type="button" className="agents-more-btn" data-testid="agents-show-all"
            onClick={() => setShowAll(true)}>
            {s.showAll.replace("{n}", String(t.agents.length - VISIBLE_AT_FIRST))}
          </button>
        </div>
      )}
    </section>
  );
};

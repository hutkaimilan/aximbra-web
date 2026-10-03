import { useState } from "react";
import { ArrowRight, RotateCcw, Scale as ScaleIc } from "lucide-react";
import "./ugyvedi.css";
import { DemoBar } from "./DemoBar";
import { DemoForm, Rise, useDemo, useFonts } from "./kit";
import C from "./content/ugyvedi";

/** A védjegy: az igazság mérlege. `tilt` fokban; a serpenyők mindig függőlegesen lógnak. */
const Scales = ({ tilt = 0, weights = [0, 0], idle = false, glow = false }) => {
  const a = (tilt * Math.PI) / 180;
  const L = 128;
  const end = (s) => [200 + s * L * Math.cos(a), 92 + s * L * Math.sin(a)];
  const pan = (s, w) => {
    const [x, y] = end(s);
    return (
      <g className={`vrt-pan ${s < 0 ? "l" : "r"}`} style={{ transform: `translate(${x}px, ${y}px)` }}>
        <path d="M0 0L-46 96M0 0L46 96" className="vrt-cord" />
        <path d="M-56 96Q0 132 56 96Z" className="vrt-dish" />
        {Array.from({ length: w }, (_, i) => (
          <ellipse key={i} cx={(i % 3 - 1) * 20} cy={92 - Math.floor(i / 3) * 9} rx="11" ry="5" className="vrt-weight" />
        ))}
        <circle r="5" className="vrt-ring" />
      </g>
    );
  };
  return (
    <svg viewBox="0 0 400 330" className={`vrt-scales ${idle ? "idle" : ""} ${glow ? "glow" : ""}`} aria-hidden="true">
      <defs>
        <linearGradient id="vrtGold" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#F3DCA5" /><stop offset=".5" stopColor="#C9A063" /><stop offset="1" stopColor="#8E6A35" />
        </linearGradient>
      </defs>
      <circle cx="200" cy="92" r="70" className="vrt-halo" />
      <path d="M200 92V300M150 300h100M170 300q30-30 60 0" className="vrt-post" />
      <g className="vrt-beam" style={{ transform: `rotate(${tilt}deg)` }}>
        <rect x={200 - L} y="88" width={L * 2} height="8" rx="4" fill="url(#vrtGold)" />
      </g>
      <circle cx="200" cy="80" r="14" fill="url(#vrtGold)" />
      <path d="M200 50l9 20h-18z" fill="url(#vrtGold)" />
      {pan(-1, weights[0])}
      {pan(1, weights[1])}
    </svg>
  );
};

const Triage = ({ d }) => {
  const [ans, setAns] = useState([]);
  const done = ans.length === d.qs.length;
  const i = ans.length;
  // Minden válasz súlyt tesz valamelyik serpenyőbe; a végén a mérleg kiegyenlít.
  const left = ans.filter((_, k) => k % 2 === 0).length;
  const right = ans.length - left;
  const tilt = done ? 0 : (right - left) * 9 + (i === 0 ? 0 : 0);
  return (
    <div className="vrt-tri">
      <div className="vrt-tri-vis"><Scales tilt={tilt} weights={done ? [3, 3] : [left * 2, right * 2]} glow={done} /></div>
      <div className="vrt-tri-card" aria-live="polite">
        {!done ? (
          <div key={i} className="vrt-q">
            <div className="vrt-step">{d.step.replace("{i}", i + 1).replace("{n}", d.qs.length)}</div>
            <div className="vrt-prog"><span style={{ width: `${(i / d.qs.length) * 100}%` }} /></div>
            <h3>{d.qs[i].q}</h3>
            <div className="vrt-opts">
              {d.qs[i].opts.map((o, k) => (
                <button key={o} type="button" onClick={() => setAns([...ans, k])}>
                  <span>{o}</span><ArrowRight size={18} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="vrt-res">
            <div className="vrt-step">{d.resTitle}</div>
            <h3>{d.resTeam.replace("{team}", d.teams[ans[0]])}</h3>
            <p className={`vrt-urg u${ans[1]}`}>{d.urg[ans[1]]}</p>
            <div className="vrt-res-row">
              <a href="#contact" className="vrt-btn solid">{d.resCta}</a>
              <button type="button" className="vrt-btn" onClick={() => setAns([])}><RotateCcw size={16} />{d.restart}</button>
            </div>
            <p className="vrt-note">{d.resNote}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default function Ugyvedi() {
  const { d, L } = useDemo(C, "/demo/ugyvedi");
  useFonts("https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,500&family=Inter:wght@300;400;500;600&display=swap");
  return (
    <div className="vrt-page demo-page" data-testid="demo-ugyvedi">
      <DemoBar prefix="vrt" />
      <header className="vrt-hero">
        <div className="vrt-wrap vrt-hero-in">
          <div>
            <div className="vrt-logo"><ScaleIc size={18} />{d.brand}<span>{d.brandSub}</span></div>
            <div className="vrt-eyebrow">{d.eyebrow}</div>
            <h1 className="vrt-title">{d.title}</h1>
            <p className="vrt-sub">{d.sub}</p>
            <div className="vrt-cta">
              <a href="#felmeres" className="vrt-btn solid">{d.cta}</a>
              <a href="#teruletek" className="vrt-btn">{d.ghost}</a>
            </div>
          </div>
          <div className="vrt-hero-vis"><Scales idle tilt={0} weights={[2, 1]} /></div>
        </div>
      </header>

      <section className="vrt-sec vrt-light" id="felmeres">
        <div className="vrt-wrap">
          <Rise className="vrt-center">
            <span className="vrt-tag">{d.triTag}</span>
            <h2 className="vrt-h2">{d.triTitle}</h2>
            <p className="vrt-lead">{d.triSub}</p>
          </Rise>
          <Triage d={d} />
        </div>
      </section>

      <section className="vrt-sec" id="teruletek">
        <div className="vrt-wrap">
          <Rise><h2 className="vrt-h2">{d.areasTitle}</h2></Rise>
          <div className="vrt-areas">
            {d.areas.map((a, i) => (
              <Rise key={a.t} delay={i * 80} className="vrt-area">
                <span className="vrt-num">0{i + 1}</span>
                <h3>{a.t}</h3>
                <p>{a.d}</p>
              </Rise>
            ))}
          </div>
        </div>
      </section>

      <section className="vrt-sec vrt-light">
        <div className="vrt-wrap">
          <Rise><h2 className="vrt-h2">{d.feeTitle}</h2></Rise>
          <div className="vrt-fees">
            {d.fees.map((f, i) => (
              <Rise key={f.t} delay={i * 100} className={`vrt-fee ${i === 1 ? "hl" : ""}`}>
                <h3>{f.t}</h3><div className="vrt-fee-p">{f.p}</div><p>{f.d}</p>
              </Rise>
            ))}
          </div>
        </div>
      </section>

      <section className="vrt-sec">
        <div className="vrt-wrap">
          <Rise><h2 className="vrt-h2">{d.procTitle}</h2></Rise>
          <ol className="vrt-proc">
            {d.proc.map((p, i) => (
              <Rise as="li" key={p.t} delay={i * 120}>
                <span className="vrt-proc-n">{i + 1}</span><h3>{p.t}</h3><p>{p.d}</p>
              </Rise>
            ))}
          </ol>
        </div>
      </section>

      <section className="vrt-sec vrt-light" id="contact">
        <div className="vrt-wrap vrt-contact">
          <Rise>
            <h2 className="vrt-h2">{d.contactTitle}</h2>
            <p className="vrt-lead">{d.contactSub}</p>
            <dl className="vrt-dl">
              <div><dt>{L.address}</dt><dd>{d.address}</dd></div>
              <div><dt>{L.phone}</dt><dd>{d.phone}</dd></div>
              <div><dt>{L.email}</dt><dd>{d.email}</dd></div>
              <div><dt>{L.hours}</dt><dd>{d.hours}</dd></div>
            </dl>
          </Rise>
          <DemoForm L={L} cls="vrt" submit={d.formSend} fields={[
            { name: "name", label: d.formName }, { name: "contact", label: d.formContact },
            { name: "msg", label: d.formMsg, area: true }]} />
        </div>
      </section>
      <footer className="vrt-footer">© {d.brand} {d.brandSub} · {d.address}</footer>
    </div>
  );
}

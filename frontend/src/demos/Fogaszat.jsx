import { useEffect, useMemo, useState } from "react";
import { Sparkles, ShieldCheck, Smile, Gem, Droplets, Baby, Plus, Check } from "lucide-react";
import "./fogaszat.css";
import { DemoBar } from "./DemoBar";
import { DemoForm, Rise, ScriptedChat, money, reduceMotion, useDemo, useFonts, useInView } from "./kit";
import C from "./content/fogaszat";

const ICONS = { spark: Sparkles, implant: ShieldCheck, aligner: Smile, veneer: Gem, clean: Droplets, kid: Baby };
const TOOTH = "M100 18C140 14 176 30 180 72C184 110 168 130 160 160C152 196 146 226 130 228C116 230 114 196 108 176C104 166 96 166 92 176C86 196 84 230 70 228C54 226 48 196 40 160C32 130 16 110 20 72C24 30 60 22 100 18Z";

/** A védjegy: a fog kirajzolódik, gyöngyházfényt kap, és végigfut rajta a csillogás. */
const HeroTooth = () => (
  <div className="dnt-tooth" aria-hidden="true">
    <svg viewBox="0 0 200 250">
      <defs>
        <radialGradient id="dntPearl" cx="38%" cy="28%" r="80%">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset=".55" stopColor="#eef6f4" />
          <stop offset="1" stopColor="#c9e4de" />
        </radialGradient>
        <linearGradient id="dntShine" x1="0" x2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset=".5" stopColor="#fff" stopOpacity=".95" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <clipPath id="dntClip"><path d={TOOTH} /></clipPath>
      </defs>
      <circle className="dnt-orbit" cx="100" cy="125" r="104" />
      <path className="dnt-fill" d={TOOTH} fill="url(#dntPearl)" />
      <g clipPath="url(#dntClip)">
        <rect className="dnt-shine" x="-60" y="-20" width="46" height="300" fill="url(#dntShine)" transform="rotate(18)" />
      </g>
      <path className="dnt-draw" d={TOOTH} pathLength="1" />
      <path className="dnt-gloss" d="M62 52C74 40 92 36 108 38" pathLength="1" />
      {[[30, 40, 0], [176, 34, .8], [186, 150, 1.6], [16, 168, 2.3]].map(([x, y, dl], i) => (
        <path key={i} className="dnt-spark" style={{ animationDelay: `${2.2 + dl}s`, transformOrigin: `${x}px ${y}px` }}
          d={`M${x} ${y - 9}L${x + 2.2} ${y - 2.2}L${x + 9} ${y}L${x + 2.2} ${y + 2.2}L${x} ${y + 9}L${x - 2.2} ${y + 2.2}L${x - 9} ${y}L${x - 2.2} ${y - 2.2}Z`} />
      ))}
    </svg>
  </div>
);

/** Légzőgyakorlat: 4 mp be, 4 tart, 4 ki — a szorongó páciensnek ez az első élménye. */
const Breath = ({ labels, note }) => {
  const [ref, seen] = useInView(0.4);
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!seen || reduceMotion()) return;
    const id = setInterval(() => setI((x) => (x + 1) % 3), 4000);
    return () => clearInterval(id);
  }, [seen]);
  return (
    <div ref={ref} className={`dnt-breath ${seen ? "on" : ""}`}>
      <div className={`dnt-breath-c ph${i}`}><span>{labels[i]}</span></div>
      <p>{note}</p>
    </div>
  );
};

const Smile2 = ({ after }) => {
  const teeth = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4];
  return (
    <svg viewBox="0 0 400 200" className="dnt-smile" aria-hidden="true">
      <path d="M20 70Q200 -10 380 70Q330 190 200 190Q70 190 20 70Z" fill={after ? "#7a2638" : "#6b2a33"} />
      <path d="M44 78Q200 28 356 78Q320 168 200 170Q80 168 44 78Z" fill="#3a0f18" />
      {teeth.map((k, j) => {
        const x = 200 + k * 30 + 2;
        const w = 26;
        const dy = after ? 0 : [3, -2, 4, 0, 2, -3, 3, 1, -2, 4][j];
        const rot = after ? 0 : [-4, 3, -2, 5, -3, 4, -5, 2, 3, -4][j];
        const h = 48 - Math.abs(k + .5) * 3;
        return <rect key={j} x={x} y={62 + Math.abs(k + .5) * 2.4 + dy} width={w} height={h} rx="7"
          transform={`rotate(${rot} ${x + w / 2} ${80})`}
          fill={after ? "#fbfcfa" : ["#e2cf9c", "#d9c48c", "#e6d4a4", "#dcc690"][j % 4]} stroke={after ? "#e6efec" : "#bfa96f"} />;
      })}
      <path d="M20 70Q200 -10 380 70Q200 30 20 70Z" fill={after ? "#8e2f44" : "#7b333d"} />
    </svg>
  );
};

const BeforeAfter = ({ d }) => {
  const [v, setV] = useState(50);
  return (
    <div className="dnt-ba">
      <div className="dnt-ba-stage">
        <Smile2 after={false} />
        <div className="dnt-ba-after" style={{ clipPath: `inset(0 0 0 ${v}%)` }}><Smile2 after /></div>
        <div className="dnt-ba-handle" style={{ left: `${v}%` }}><span /></div>
        <span className="dnt-ba-l">{d.baBefore}</span><span className="dnt-ba-r">{d.baAfter}</span>
        <input type="range" min="0" max="100" value={v} onChange={(e) => setV(+e.target.value)}
          aria-label={`${d.baBefore} / ${d.baAfter}`} />
      </div>
      <p className="dnt-note">{d.baNote}</p>
    </div>
  );
};

/** Számláló, ami az új értékre fut fel — az árkalkulátor visszajelzése. */
const useTween = (target) => {
  const [v, setV] = useState(target);
  useEffect(() => {
    if (reduceMotion()) { setV(target); return; }
    let raf; const from = v; const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 450);
      setV(from + (target - from) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return v;
};

const Estimator = ({ d }) => {
  const [on, setOn] = useState(() => new Set([0]));
  const sum = useMemo(() => [...on].reduce((a, i) => [a[0] + d.est[i].min, a[1] + d.est[i].max], [0, 0]), [on, d.est]);
  const lo = useTween(sum[0]); const hi = useTween(sum[1]);
  const flip = (i) => setOn((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; });
  return (
    <div className="dnt-est">
      <div className="dnt-est-list">
        {d.est.map((e, i) => (
          <button key={i} type="button" className={`dnt-est-i ${on.has(i) ? "on" : ""}`} aria-pressed={on.has(i)} onClick={() => flip(i)}>
            <span className="dnt-est-box">{on.has(i) ? <Check size={16} /> : <Plus size={16} />}</span>
            <span className="dnt-est-t">{e.t}</span>
            <span className="dnt-est-p">{money(e.min, d.cur)}</span>
          </button>
        ))}
      </div>
      <div className="dnt-est-total">
        <div className="dnt-est-lbl">{d.estTotal}</div>
        <div className="dnt-est-sum">{on.size ? `${money(lo, d.cur)} – ${money(hi, d.cur)}` : d.estEmpty}</div>
        <a href="#contact" className="dnt-btn solid">{d.estCta}</a>
        <p className="dnt-note">{d.estNote}</p>
      </div>
    </div>
  );
};

export default function Fogaszat() {
  const { d, L } = useDemo(C, "/demo/fogaszat");
  useFonts("https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Manrope:wght@400;500;600;700&display=swap");
  const [chatRef, chatSeen] = useInView(0.35);

  return (
    <div className="dnt-page demo-page" data-testid="demo-fogaszat">
      <DemoBar prefix="dnt" />

      <header className="dnt-hero">
        <div className="dnt-wrap dnt-hero-in">
          <div>
            <div className="dnt-logo">{d.brand}<span>{d.brandSub}</span></div>
            <div className="dnt-eyebrow">{d.eyebrow}</div>
            <h1 className="dnt-title">{d.title}</h1>
            <p className="dnt-sub">{d.sub}</p>
            <div className="dnt-cta">
              <a href="#contact" className="dnt-btn solid">{d.cta}</a>
              <a href="#arak" className="dnt-btn">{d.ghost}</a>
            </div>
            <ul className="dnt-chips">{d.chips.map((c) => <li key={c}><Check size={14} />{c}</li>)}</ul>
          </div>
          <HeroTooth />
        </div>
      </header>

      <section className="dnt-sec dnt-fear">
        <div className="dnt-wrap dnt-fear-in">
          <Rise>
            <span className="dnt-tag">{d.fearTag}</span>
            <h2 className="dnt-h2">{d.fearTitle}</h2>
            <p className="dnt-lead">{d.fearText}</p>
            <ul className="dnt-points">{d.fearPoints.map((p) => <li key={p}>{p}</li>)}</ul>
          </Rise>
          <Breath labels={d.breath} note={d.breathNote} />
        </div>
      </section>

      <section className="dnt-sec">
        <div className="dnt-wrap">
          <Rise><h2 className="dnt-h2">{d.treatTitle}</h2><p className="dnt-lead">{d.treatSub}</p></Rise>
          <div className="dnt-treat">
            {d.treatments.map((x, i) => {
              const Ic = ICONS[x.icon] || Sparkles;
              return (
                <Rise key={x.t} delay={(i % 3) * 90} className="dnt-card">
                  <div className="dnt-ic"><Ic size={26} strokeWidth={1.6} /></div>
                  <h3>{x.t}</h3><p>{x.d}</p><div className="dnt-price">{x.p}</div>
                </Rise>
              );
            })}
          </div>
        </div>
      </section>

      <section className="dnt-sec dnt-soft">
        <div className="dnt-wrap">
          <Rise><h2 className="dnt-h2 center">{d.baTitle}</h2></Rise>
          <BeforeAfter d={d} />
        </div>
      </section>

      <section className="dnt-sec" id="arak">
        <div className="dnt-wrap">
          <Rise><h2 className="dnt-h2">{d.estTitle}</h2><p className="dnt-lead">{d.estSub}</p></Rise>
          <Estimator d={d} />
        </div>
      </section>

      <section className="dnt-sec dnt-dark">
        <div className="dnt-wrap dnt-rec">
          <Rise>
            <h2 className="dnt-h2">{d.recTitle}</h2>
            <p className="dnt-lead">{d.recSub}</p>
            <span className="dnt-badge">{d.recBadge}</span>
          </Rise>
          <div ref={chatRef} className="dnt-phone">
            <div className="dnt-phone-top"><b>{d.brand}</b> · {L.demo}</div>
            <ScriptedChat script={d.script} cls="dnt" start={chatSeen} />
          </div>
        </div>
      </section>

      <section className="dnt-sec">
        <div className="dnt-wrap dnt-narrow">
          <Rise><h2 className="dnt-h2">{d.faqTitle}</h2></Rise>
          {d.faq.map((f) => (
            <details key={f.q} className="dnt-faq"><summary>{f.q}</summary><p>{f.a}</p></details>
          ))}
        </div>
      </section>

      <section className="dnt-sec dnt-soft" id="contact">
        <div className="dnt-wrap dnt-contact">
          <Rise>
            <h2 className="dnt-h2">{d.contactTitle}</h2>
            <p className="dnt-lead">{d.contactSub}</p>
            <dl className="dnt-dl">
              <div><dt>{L.address}</dt><dd>{d.address}</dd></div>
              <div><dt>{L.phone}</dt><dd>{d.phone}</dd></div>
              <div><dt>{L.email}</dt><dd>{d.email}</dd></div>
              <div><dt>{L.hours}</dt><dd>{d.hours}</dd></div>
            </dl>
          </Rise>
          <DemoForm L={L} cls="dnt" submit={d.formSend} fields={[
            { name: "name", label: d.formName }, { name: "contact", label: d.formContact },
            { name: "msg", label: d.formMsg, area: true }]} />
        </div>
      </section>

      <footer className="dnt-footer">© {d.brand} {d.brandSub} · {d.address}</footer>
    </div>
  );
}

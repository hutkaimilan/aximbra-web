import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

/**
 * "Hogyan dolgozunk": egy fenycsomag vegigmegy a lepeseken, es az emberi
 * kapunal (amber lepes) megall, mielott tovabbengedik.
 *
 * Miert igy (marketingkutatas):
 *  - mutatni, nem allitani: a "semmi nem megy ki jovahagyas nelkul" igeretet a
 *    megallas maga bizonyitja, nem egy ujabb mondat;
 *  - peak-end szabaly: a csucs az emberi kapu (hosszabb megallas, amber), a vege
 *    a visszameres, utana a csomag visszafut az elejere — zart kor;
 *  - chunking: 7 lepes harom szakaszba csoportositva, igy fejben tarthato;
 *  - magatol fut, ha latszik, de raallva megall, kattintva barmelyik lepes elohozhato:
 *    az olvaso iranyit, nem a gorgetes.
 */
const STEP_MS = 1500;
const GATE_MS = 2900;
const END_MS = 2600;

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export const Process = () => {
  const { t } = useLang();
  const p = t.process;
  const steps = p.steps;
  const phases = p.phases || [];
  const flowRef = useRef(null);
  const nodeRefs = useRef([]);
  const [cur, setCur] = useState(-1);
  const [pos, setPos] = useState(0);
  const [inView, setInView] = useState(false);
  const [paused, setPaused] = useState(false);
  const [still] = useState(reducedMotion);

  // Csak akkor fut, ha a szakasz latszik: nem pazarol, es nem "lemaradt" allapotot lat az olvaso.
  useEffect(() => {
    const el = flowRef.current;
    if (!el || still) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.2 });
    io.observe(el);
    return () => io.disconnect();
  }, [still]);

  useEffect(() => {
    if (still || !inView || paused) return;
    const last = steps.length - 1;
    let delay;
    if (cur < 0) delay = 500;
    else if (cur >= last) delay = END_MS;
    else delay = steps[cur].amber ? GATE_MS : STEP_MS;
    const id = setTimeout(() => setCur((c) => (c >= last ? -1 : c + 1)), delay);
    return () => clearTimeout(id);
  }, [cur, inView, paused, still, steps]);

  const measure = useCallback(() => {
    const flow = flowRef.current;
    const i = still ? steps.length - 1 : cur;
    const node = nodeRefs.current[i];
    if (!flow || !node || i < 0) { setPos(0); return; }
    const f = flow.getBoundingClientRect();
    const n = node.getBoundingClientRect();
    setPos(n.top - f.top + n.height / 2);
  }, [cur, still, steps.length]);

  useLayoutEffect(() => { measure(); }, [measure]);
  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const shown = still ? steps.length - 1 : cur;
  const atGate = shown >= 0 && !!steps[shown]?.amber && !still;
  const phaseAt = (i) => phases.find((ph) => ph.from === i);

  return (
    <section className="container" id="folyamat" data-testid="process-section">
      <Reveal>
        <span className="tag">{p.tag}</span>
        <h2 className="h-sec">{p.heading}</h2>
        <p className="sub">{p.sub}</p>
      </Reveal>
      <div
        className={`flow${cur < 0 && !still ? " rewind" : ""}${still ? " still" : ""}`}
        ref={flowRef}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        <div className="flow-line" aria-hidden="true" />
        <div className={`flow-fill${atGate ? " gate" : ""}`} style={{ height: pos }} aria-hidden="true" />
        {!still && (
          <div className={`flow-packet${atGate ? " gate" : ""}${cur < 0 ? " idle" : ""}`}
            style={{ transform: `translateY(${pos}px)` }} aria-hidden="true" />
        )}
        {steps.map((s, i) => {
          const ph = phaseAt(i);
          const state = i < shown ? "done" : i === shown ? "active" : "";
          return (
            <Fragment key={s.n}>
              {ph && (
                <div className={`flow-phase${shown >= i ? " lit" : ""}`}><span>{ph.label}</span></div>
              )}
              <div
                className={`fstep ${i % 2 ? "right" : "left"} ${state}${s.amber ? " gate" : ""}`}
                data-testid={`step-${s.n}`}
                onClick={() => setCur(i)}
              >
                <div className="fnode" ref={(el) => { nodeRefs.current[i] = el; }}>{s.n}</div>
                <div className="fcard">
                  <h3>{s.title}</h3>
                  <p>{s.desc}</p>
                  {s.amber && <div className="amber-pill" data-testid="human-gate-pill">{s.amber}</div>}
                </div>
              </div>
            </Fragment>
          );
        })}
      </div>
    </section>
  );
};

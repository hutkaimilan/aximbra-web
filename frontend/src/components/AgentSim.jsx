import { useEffect, useRef, useState } from "react";
import "./agentsim.css";

const CAT = { m: "sim-m", c: "sim-c", a: "sim-a", dim: "sim-dim" };

export const AgentSim = ({ data }) => {
  const [phase, setPhase] = useState("idle"); // idle | running | done
  const [prog, setProg] = useState(0);        // revealed item count
  const [count, setCount] = useState(0);       // ticking counter
  const [vis, setVis] = useState(true);
  const timers = useRef([]);
  const rootRef = useRef(null);
  const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVis(e.isIntersecting), { threshold: 0.1 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  useEffect(() => () => clear(), []);

  const finish = () => { clear(); setProg(data.items.length); setCount(data.total); setPhase("done"); };

  const run = () => {
    clear();
    if (reduce) { finish(); return; }
    setPhase("running"); setProg(0); setCount(0);
    const n = data.items.length;
    const stepMs = Math.max(280, Math.floor(6500 / n));
    for (let i = 1; i <= n; i++) {
      timers.current.push(setTimeout(() => {
        setProg(i);
        setCount(Math.round((i / n) * data.total));
      }, i * stepMs));
    }
    timers.current.push(setTimeout(finish, n * stepMs + 500));
  };

  const reset = () => { clear(); setPhase("idle"); setProg(0); setCount(0); };

  return (
    <div ref={rootRef} className={`agent-sim ${vis ? "sim-vis" : ""}`} data-testid="agent-sim">
      {phase === "idle" && (
        <div className="sim-before">
          <div className="sim-head"><span className="sim-big">{data.total}</span> {data.beforeLabel}</div>
          <div className="sim-grid">
            {data.items.map((it, i) => (
              <div key={i} className="sim-chip sim-dim" data-testid={`sim-chip-${i}`}>
                <span className="sim-chip-t">{it.t}</span>{it.s && <span className="sim-chip-s">{it.s}</span>}
              </div>
            ))}
          </div>
          <button className="sim-btn go" data-testid="sim-start" onClick={run}>▶ {data.start}</button>
        </div>
      )}

      {phase === "running" && (
        <div className="sim-before">
          <div className="sim-head"><span className="sim-big">{count}</span> / {data.total} feldolgozva…</div>
          <div className="sim-grid">
            {data.items.map((it, i) => (
              <div key={i} className={`sim-chip ${i < prog ? CAT[it.cat] : "sim-dim sim-pending"}`}>
                <span className="sim-chip-t">{it.t}</span>{it.s && <span className="sim-chip-s">{it.s}</span>}
              </div>
            ))}
          </div>
          <button className="sim-btn skip" data-testid="sim-skip" onClick={finish}>Ugrás a végére →</button>
        </div>
      )}

      {phase === "done" && (
        <div className="sim-after" data-testid="sim-after">
          <div className="sim-after-head">{data.afterHead}</div>
          {data.afterBar && <div className="sim-bar sim-a" data-testid="sim-bar">{data.afterBar}</div>}
          <div className="sim-picks">
            {data.picks.map((p, i) => (
              <div key={i} className={`sim-pick ${CAT[p.cat]}`}>
                <span className="sim-pick-t">{p.t}</span>
                <span className="sim-pick-r">{p.reason}</span>
              </div>
            ))}
          </div>
          <div className="sim-closing" data-testid="sim-closing">{data.closing}</div>
          <button className="sim-btn again" data-testid="sim-again" onClick={reset}>↻ Újra</button>
        </div>
      )}
    </div>
  );
};

import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

// Statikus kartyaracs: nincs gorgetesre toltodo vonal, minden lepes azonnal olvashato.
export const Process = () => {
  const { t } = useLang();
  const p = t.process;

  return (
    <section className="container" id="folyamat" data-testid="process-section">
      <Reveal>
        <span className="tag">{p.tag}</span>
        <h2 className="h-sec">{p.heading}</h2>
        <p className="sub">{p.sub}</p>
      </Reveal>
      <div className="steps">
        {p.steps.map((s, i) => (
          <Reveal key={s.n} delay={(i % 2) * 90}
            className={`step${s.amber ? " step-gate" : ""}${i === p.steps.length - 1 ? " step-last" : ""}`}
            testid={`step-${s.n}`}>
            <div>
              <div className="step-head">
                <span className="step-n">{s.n}</span>
                <h3>{s.title}</h3>
              </div>
              <p>{s.desc}</p>
              {s.amber && <div className="amber-pill" data-testid="human-gate-pill">{s.amber}</div>}
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
};

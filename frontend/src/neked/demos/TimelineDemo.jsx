import { useState } from "react";

const Toggle = ({ mode, setMode, ui }) => (
  <div className="mb-5 inline-flex rounded-full border border-[var(--ax-line)] p-1" data-testid="timeline-toggle">
    {["before", "after"].map((m) => (
      <button
        key={m}
        type="button"
        onClick={() => setMode(m)}
        className={`rounded-full px-5 py-2 text-sm font-semibold transition-colors ${
          mode === m ? (m === "after" ? "bg-[var(--ax-cyan)] text-[#03040a]" : "bg-[var(--ax-magenta)]/80 text-white") : "text-[var(--ax-muted)]"
        }`}
        data-testid={`timeline-toggle-${m}`}
      >
        {ui[`label_${m}`]}
      </button>
    ))}
  </div>
);

export const TimelineDemo = ({ demo, ui }) => {
  const [mode, setMode] = useState("before");
  const after = mode === "after";
  return (
    <div>
      <Toggle mode={mode} setMode={setMode} ui={ui} />
      <ol className="relative border-l border-[var(--ax-line)] pl-6" data-testid="timeline-list">
        {demo.items.map((t, i) => (
          <li key={`${mode}-${i}`} className="ax-rise relative mb-5 last:mb-0" style={{ animationDelay: `${i * 0.06}s` }}>
            <span className={`absolute -left-[31px] top-1.5 h-3 w-3 rounded-full ${after ? "bg-[var(--ax-cyan)]" : "bg-[var(--ax-magenta)]"}`} />
            <div className="flex flex-wrap items-baseline gap-x-3">
              <span className="font-mono text-sm font-bold text-[var(--ax-cyan)]">{t.title}</span>
              <span className="text-sm font-semibold">{t.subtitle}</span>
            </div>
            <p className={`mt-1 text-sm leading-relaxed ${after ? "text-slate-200" : "text-[var(--ax-muted)]"}`} data-testid={`timeline-text-${i}`}>
              {after ? t.output : t.body}
            </p>
          </li>
        ))}
      </ol>
      {demo.summary && <p className="mt-5 text-sm text-[var(--ax-muted)]">{demo.summary}</p>}
    </div>
  );
};

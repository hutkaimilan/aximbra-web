import { useState } from "react";
import { FieldLabel, Level } from "./parts";

export const ReportDemo = ({ demo, ui }) => {
  const [sel, setSel] = useState(0);
  const it = demo.items[sel];
  return (
    <div>
      <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="report-kpis">
        {demo.items.map((k, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setSel(i)}
            className={`rounded-xl border p-4 text-left transition-colors ${i === sel ? "border-[var(--ax-cyan)]/60 bg-[var(--ax-cyan)]/5" : "border-[var(--ax-line)] hover:bg-white/[0.03]"}`}
            data-testid={`report-kpi-${i}`}
          >
            <p className="text-xs text-[var(--ax-muted)] leading-snug">{k.title}</p>
            <p className="mt-2 font-mono text-xl font-bold text-[var(--ax-cyan)] break-words">{k.tag}</p>
            <div className="mt-2"><Level level={k.level} ui={ui} /></div>
          </button>
        ))}
      </div>
      <div className="mt-4 [display:grid] gap-4 rounded-xl border border-[var(--ax-line)] bg-[#06070f] p-5 md:grid-cols-2" data-testid="report-detail">
        <div>
          <FieldLabel color="text-[var(--ax-cyan)]">{it.title}</FieldLabel>
          <p className="text-sm leading-relaxed text-slate-300">{it.body}</p>
        </div>
        <div className="rounded-lg border border-[var(--ax-purple)]/30 bg-[var(--ax-purple)]/5 p-4">
          <FieldLabel>{ui.label_next_step}</FieldLabel>
          <p className="text-sm leading-relaxed">{it.output}</p>
        </div>
      </div>
      {demo.summary && <p className="mt-4 text-sm text-[var(--ax-muted)]">{demo.summary}</p>}
    </div>
  );
};

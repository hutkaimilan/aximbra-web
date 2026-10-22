import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { FieldLabel, Tag } from "./parts";

const scoreColor = (s) => (s >= 75 ? "var(--ax-cyan)" : s >= 50 ? "var(--ax-purple)" : "var(--ax-magenta)");

export const LeadsDemo = ({ demo, ui }) => {
  const items = [...demo.items].map((it, i) => ({ ...it, i })).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const [open, setOpen] = useState(items[0]?.i);
  return (
    <div className="flex flex-col gap-3" data-testid="leads-list">
      {items.map((l) => {
        const isOpen = open === l.i;
        const score = l.score ?? 0;
        return (
          <div key={l.i} className={`rounded-xl border transition-colors ${isOpen ? "border-[var(--ax-cyan)]/50 bg-[var(--ax-cyan)]/[0.03]" : "border-[var(--ax-line)]"}`}>
            <button type="button" onClick={() => setOpen(isOpen ? null : l.i)} className="flex w-full items-center gap-4 p-4 text-left" data-testid={`lead-item-${l.i}`}>
              <div className="w-14 shrink-0 text-center">
                <span className="font-mono text-2xl font-bold" style={{ color: scoreColor(score) }}>{score}</span>
                <div className="mt-1 h-1 rounded-full bg-white/10">
                  <div className="h-1 rounded-full" style={{ width: `${score}%`, background: scoreColor(score) }} />
                </div>
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold leading-snug">{l.title}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <Tag>{l.tag}</Tag>
                  <span className="font-mono text-[11px] text-[var(--ax-muted)]">{l.subtitle}</span>
                </div>
              </div>
              <ChevronDown size={18} className={`shrink-0 text-[var(--ax-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`} />
            </button>
            {isOpen && (
              <div className="[display:grid] gap-4 border-t border-[var(--ax-line)] p-4 md:grid-cols-2" data-testid={`lead-detail-${l.i}`}>
                <p className="text-sm leading-relaxed text-slate-300">{l.body}</p>
                <div className="rounded-lg border border-[var(--ax-purple)]/30 bg-[var(--ax-purple)]/5 p-4">
                  <FieldLabel>{ui.label_next_step}</FieldLabel>
                  <p className="text-sm leading-relaxed">{l.output}</p>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {demo.summary && <p className="mt-2 text-sm text-[var(--ax-muted)]">{demo.summary}</p>}
    </div>
  );
};

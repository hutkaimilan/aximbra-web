import { useState } from "react";
import { FileText } from "lucide-react";
import { FieldLabel, Level } from "./parts";

const MARK = {
  high: "bg-[#ff5c7a]/15 border-[#ff5c7a]",
  medium: "bg-[#ffb547]/10 border-[#ffb547]",
  low: "bg-transparent border-transparent",
};

export const DocumentDemo = ({ demo, ui }) => {
  const [sel, setSel] = useState(demo.items.findIndex((c) => c.level === "high"));
  const it = demo.items[sel];
  return (
    <div className="[display:grid] gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="rounded-xl border border-[var(--ax-line)] bg-[#f4f5f8] p-5 text-[#141622] sm:p-8" data-testid="document-paper">
        <div className="mb-5 flex items-center gap-2 border-b border-black/10 pb-3">
          <FileText size={16} /> <span className="font-mono text-xs">{demo.title}</span>
        </div>
        {demo.items.map((c, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setSel(i)}
            className={`mb-2 block w-full rounded-md border-l-4 px-3 py-2 text-left transition-colors hover:bg-black/5 ${MARK[c.level] || MARK.low} ${i === sel ? "ring-2 ring-[#8b5cff]" : ""}`}
            data-testid={`document-clause-${i}`}
          >
            <span className="block text-xs font-bold uppercase tracking-wide">{c.title}</span>
            <span className="mt-1 block text-sm leading-relaxed">{c.body}</span>
          </button>
        ))}
      </div>
      <div className="rounded-xl border border-[var(--ax-line)] bg-[#06070f] p-5 lg:sticky lg:top-24 lg:self-start" data-testid="document-comment">
        {it ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <FieldLabel>{ui.label_risk}</FieldLabel>
              <Level level={it.level} ui={ui} />
            </div>
            <p className="font-semibold">{it.title}</p>
            <div className="mt-4 rounded-lg border border-[var(--ax-purple)]/30 bg-[var(--ax-purple)]/5 p-4">
              <FieldLabel>{ui.label_comment}</FieldLabel>
              <p className="text-sm leading-relaxed">{it.output}</p>
            </div>
          </>
        ) : (
          <p className="text-sm text-[var(--ax-muted)]">{ui.label_select}</p>
        )}
      </div>
    </div>
  );
};

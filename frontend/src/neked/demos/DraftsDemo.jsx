import { useState } from "react";
import { ApproveButton, FieldLabel, Tag } from "./parts";

export const DraftsDemo = ({ demo, ui }) => {
  const [sel, setSel] = useState(0);
  const [approved, setApproved] = useState({});
  const it = demo.items[sel];
  return (
    <div>
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1" data-testid="drafts-tabs">
        {demo.items.map((d, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setSel(i)}
            className={`shrink-0 rounded-full border px-4 py-2 text-sm transition-colors ${i === sel ? "border-[var(--ax-cyan)] bg-[var(--ax-cyan)]/10 text-[var(--ax-cyan)]" : "border-[var(--ax-line)] text-[var(--ax-muted)] hover:text-white"}`}
            data-testid={`drafts-tab-${i}`}
          >
            {d.subtitle || d.title}
          </button>
        ))}
      </div>
      <div className="[display:grid] gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="rounded-xl border border-[var(--ax-line)] p-5">
          <FieldLabel color="text-[var(--ax-muted)]">{ui.label_brief}</FieldLabel>
          <p className="text-sm leading-relaxed text-slate-300">{it.body}</p>
          <div className="mt-3"><Tag>{it.tag}</Tag></div>
        </div>
        <div className="rounded-xl border border-[var(--ax-purple)]/30 bg-[var(--ax-purple)]/5 p-5" data-testid="drafts-output">
          <h3 className="text-lg font-semibold">{it.title}</h3>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed">{it.output}</p>
          <ApproveButton approved={approved[sel]} onClick={() => setApproved({ ...approved, [sel]: !approved[sel] })} ui={ui} testId="drafts-approve-button" />
        </div>
      </div>
    </div>
  );
};

import { useState } from "react";
import { Mail } from "lucide-react";
import { ApproveButton, FieldLabel, Level, Tag } from "./parts";

export const InboxDemo = ({ demo, ui }) => {
  const [sel, setSel] = useState(0);
  const [approved, setApproved] = useState({});
  const it = demo.items[sel];
  return (
    <div className="[display:grid] gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <ul className="flex flex-col gap-2" data-testid="inbox-list">
        {demo.items.map((m, i) => (
          <li key={i}>
            <button
              type="button"
              onClick={() => setSel(i)}
              className={`w-full rounded-xl border p-4 text-left transition-colors ${
                i === sel ? "border-[var(--ax-cyan)]/60 bg-[var(--ax-cyan)]/5" : "border-[var(--ax-line)] hover:bg-white/[0.03]"
              }`}
              data-testid={`inbox-item-${i}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[11px] text-[var(--ax-muted)]">{m.subtitle}</span>
                <Level level={m.level} ui={ui} />
              </div>
              <p className="mt-1.5 font-semibold leading-snug">{m.title}</p>
              <div className="mt-2"><Tag>{m.tag}</Tag></div>
            </button>
          </li>
        ))}
      </ul>
      <div className="rounded-xl border border-[var(--ax-line)] bg-[#06070f] p-5 sm:p-6" data-testid="inbox-detail">
        <div className="flex flex-wrap items-center gap-2 text-[var(--ax-muted)]">
          <Mail size={15} /> <span className="font-mono text-xs">{it.subtitle}</span>
          <span className="ml-auto flex gap-2"><Tag>{ui.label_category}: {it.tag}</Tag></span>
        </div>
        <h3 className="mt-3 text-lg font-semibold">{it.title}</h3>
        <p className="mt-3 text-sm leading-relaxed text-slate-300">{it.body}</p>
        <div className="mt-6 rounded-lg border border-[var(--ax-purple)]/30 bg-[var(--ax-purple)]/5 p-4">
          <FieldLabel>{ui.label_draft}</FieldLabel>
          <p className="text-sm leading-relaxed" data-testid="inbox-draft">{it.output}</p>
          <ApproveButton approved={approved[sel]} onClick={() => setApproved({ ...approved, [sel]: !approved[sel] })} ui={ui} testId="inbox-approve-button" />
        </div>
      </div>
    </div>
  );
};

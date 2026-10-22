import { useEffect, useState } from "react";
import { Tag } from "./parts";

const Bubble = ({ who, children, agent }) => (
  <div className={`ax-rise max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${agent ? "self-end bg-[var(--ax-cyan)]/10 border border-[var(--ax-cyan)]/30" : "self-start bg-white/5 border border-[var(--ax-line)]"}`}>
    <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-[var(--ax-muted)]">{who}</span>
    {children}
  </div>
);

export const ChatDemo = ({ demo, ui }) => {
  const [sel, setSel] = useState(0);
  const [typing, setTyping] = useState(true);
  const it = demo.items[sel];

  useEffect(() => {
    const t = setTimeout(() => setTyping(false), 1200);
    return () => clearTimeout(t);
  }, [sel]);

  const pick = (i) => {
    if (i === sel) return;
    setTyping(true);
    setSel(i);
  };

  return (
    <div className="[display:grid] gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible" data-testid="chat-topics">
        {demo.items.map((c, i) => (
          <button
            key={i}
            type="button"
            onClick={() => pick(i)}
            className={`shrink-0 rounded-xl border px-4 py-3 text-left text-sm transition-colors lg:w-full ${i === sel ? "border-[var(--ax-cyan)]/60 bg-[var(--ax-cyan)]/5" : "border-[var(--ax-line)] hover:bg-white/[0.03]"}`}
            data-testid={`chat-topic-${i}`}
          >
            <span className="font-semibold">{c.title}</span>
          </button>
        ))}
      </div>
      <div className="flex min-h-[260px] flex-col gap-3 rounded-xl border border-[var(--ax-line)] bg-[#06070f] p-4 sm:p-6" data-testid="chat-window">
        <Bubble key={`q-${sel}`} who={ui.label_customer}>{it.body}</Bubble>
        {typing ? (
          <div className="flex gap-1.5 self-end rounded-2xl border border-[var(--ax-cyan)]/30 bg-[var(--ax-cyan)]/10 px-4 py-3" data-testid="chat-typing">
            {[0, 1, 2].map((d) => <span key={d} className="ax-dot h-2 w-2 rounded-full bg-[var(--ax-cyan)]" style={{ animationDelay: `${d * 0.15}s` }} />)}
          </div>
        ) : (
          <Bubble key={`a-${sel}`} who={ui.label_agent} agent>{it.output}</Bubble>
        )}
        {!typing && it.tag && <div className="self-end"><Tag>{it.tag}</Tag></div>}
      </div>
    </div>
  );
};

import { useEffect, useRef, useState } from "react";
import { Phone, Play, RotateCcw } from "lucide-react";
import { FieldLabel } from "./parts";

const isAgent = (s) => /agent|ai|recep/i.test(s || "");

export const CallDemo = ({ demo, ui }) => {
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef(null);
  const total = demo.items.length;

  useEffect(() => {
    if (!playing) return;
    if (shown >= total) return setPlaying(false);
    timer.current = setTimeout(() => setShown((n) => n + 1), shown === 0 ? 300 : 1100);
    return () => clearTimeout(timer.current);
  }, [playing, shown, total]);

  const start = () => { setShown(0); setPlaying(true); };
  const done = shown >= total;

  return (
    <div className="rounded-xl border border-[var(--ax-line)] bg-[#06070f] p-4 sm:p-6" data-testid="call-demo">
      <div className="mb-5 flex items-center gap-3">
        <span className={`flex h-10 w-10 items-center justify-center rounded-full bg-[var(--ax-cyan)]/15 text-[var(--ax-cyan)] ${playing ? "ax-live" : ""}`}>
          <Phone size={18} />
        </span>
        <div className="flex h-6 flex-1 items-end gap-[3px] overflow-hidden" aria-hidden>
          {Array.from({ length: 40 }).map((_, i) => (
            <span key={i} className="w-[3px] rounded-full bg-[var(--ax-cyan)]/60 transition-all duration-300"
              style={{ height: playing ? `${20 + ((i * 37) % 80)}%` : "15%" }} />
          ))}
        </div>
        <button type="button" onClick={start} className="ax-btn-primary inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold" data-testid="call-play-button">
          {done && shown > 0 ? <RotateCcw size={14} /> : <Play size={14} />} {done && shown > 0 ? ui.label_replay : ui.label_play}
        </button>
      </div>
      <div className="flex flex-col gap-3" data-testid="call-transcript">
        {demo.items.slice(0, shown).map((l, i) => {
          const agent = isAgent(l.subtitle);
          return (
            <div key={i} className={`ax-rise max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${agent ? "self-end bg-[var(--ax-cyan)]/10 border border-[var(--ax-cyan)]/30" : "self-start bg-white/5 border border-[var(--ax-line)]"}`}>
              <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-[var(--ax-muted)]">{agent ? ui.label_agent : ui.label_caller}</span>
              {l.body}
            </div>
          );
        })}
        {shown === 0 && <p className="text-sm text-[var(--ax-muted)]">▶ {ui.label_play}</p>}
      </div>
      {done && shown > 0 && demo.summary && (
        <div className="ax-rise mt-6 rounded-lg border border-[var(--ax-purple)]/30 bg-[var(--ax-purple)]/5 p-4" data-testid="call-summary">
          <FieldLabel>{ui.label_summary}</FieldLabel>
          <p className="text-sm leading-relaxed">{demo.summary}</p>
        </div>
      )}
    </div>
  );
};

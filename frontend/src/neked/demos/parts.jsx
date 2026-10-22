const COLORS = {
  high: "text-[#ff5c7a] border-[#ff5c7a]/40 bg-[#ff5c7a]/10",
  medium: "text-[#ffb547] border-[#ffb547]/40 bg-[#ffb547]/10",
  low: "text-[#3ee6a8] border-[#3ee6a8]/40 bg-[#3ee6a8]/10",
};

export const levelColor = (level) => COLORS[level] || "text-[var(--ax-muted)] border-[var(--ax-line)]";

export const Level = ({ level, ui }) =>
  level ? (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] ${levelColor(level)}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {ui[`level_${level}`]}
    </span>
  ) : null;

export const Tag = ({ children }) =>
  children ? (
    <span className="inline-flex rounded-md border border-[var(--ax-cyan)]/30 bg-[var(--ax-cyan)]/5 px-2 py-0.5 font-mono text-[11px] text-[var(--ax-cyan)]">
      {children}
    </span>
  ) : null;

export const FieldLabel = ({ children, color = "text-[var(--ax-purple)]" }) => (
  <p className={`font-mono text-[11px] uppercase tracking-[0.2em] ${color} mb-2`}>{children}</p>
);

export const ApproveButton = ({ approved, onClick, ui, testId }) => (
  <button
    type="button"
    onClick={onClick}
    className={`mt-4 rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
      approved ? "bg-[#3ee6a8]/15 text-[#3ee6a8] border border-[#3ee6a8]/40" : "ax-btn-primary"
    }`}
    data-testid={testId}
  >
    {approved ? `✓ ${ui.label_approved}` : ui.label_approve}
  </button>
);

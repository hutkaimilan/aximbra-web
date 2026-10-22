import { Bot, Plus } from "lucide-react";
import { SectionLabel } from "./QuoteCard";

const Steps = ({ steps, label }) => (
  <div className="mt-8">
    <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--ax-cyan)] mb-4">{label}</p>
    <ol className="[display:grid] gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="agent-steps">
      {steps.map((s, i) => (
        <li key={i} className="rounded-xl border border-[var(--ax-line)] bg-[var(--ax-card-2)]/60 p-4">
          <span className="font-mono text-xs text-[var(--ax-magenta)]">0{i + 1}</span>
          <p className="mt-2 text-sm leading-relaxed">{s}</p>
        </li>
      ))}
    </ol>
  </div>
);

const MainAgent = ({ agent, ui }) => (
  <div className="ax-glow-border p-6 sm:p-10" data-testid="main-agent-card">
    <div className="flex items-center gap-3">
      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--ax-cyan)]/10 text-[var(--ax-cyan)]">
        <Bot size={22} />
      </span>
      <h2 className="text-2xl font-bold sm:text-3xl" data-testid="main-agent-name">{agent.name}</h2>
    </div>
    <p className="mt-6 max-w-3xl text-base leading-relaxed sm:text-lg" data-testid="main-agent-what">{agent.what_it_does}</p>
    {agent.custom_idea && (
      <div className="mt-6 rounded-xl border border-[var(--ax-magenta)]/30 bg-[var(--ax-magenta)]/5 p-5" data-testid="custom-agent-idea">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--ax-magenta)] mb-2">{ui.custom_label}</p>
        <p className="text-sm sm:text-base">{agent.custom_idea}</p>
      </div>
    )}
    {agent.reason && (
      <div className="mt-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--ax-purple)] mb-2">{ui.why_label}</p>
        <p className="max-w-3xl text-sm text-[var(--ax-muted)] sm:text-base" data-testid="main-agent-reason">{agent.reason}</p>
      </div>
    )}
    {agent.steps?.length > 0 && <Steps steps={agent.steps} label={ui.steps_label} />}
  </div>
);

const Secondary = ({ items, ui }) => (
  <div className="mt-6" data-testid="secondary-agents">
    <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--ax-muted)] mb-3">{ui.secondary_label}</p>
    <div className="[display:grid] gap-3 md:grid-cols-2">
      {items.map((s) => (
        <div key={s.id} className="ax-card flex gap-3 p-5" data-testid={`secondary-agent-${s.id}`}>
          <Plus size={18} className="mt-0.5 shrink-0 text-[var(--ax-purple)]" />
          <div>
            <p className="font-semibold">{s.name}</p>
            {s.reason && <p className="mt-1 text-sm text-[var(--ax-muted)]">{s.reason}</p>}
          </div>
        </div>
      ))}
    </div>
  </div>
);

export const AgentSection = ({ page }) => (
  <section className="pb-16 sm:pb-24" data-testid="agent-section">
    <SectionLabel>{page.ui.agent_label}</SectionLabel>
    <MainAgent agent={page.agent} ui={page.ui} />
    {page.secondary?.length > 0 && <Secondary items={page.secondary} ui={page.ui} />}
  </section>
);

import { Database, ExternalLink, Phone } from "lucide-react";
import { SectionLabel } from "./QuoteCard";
import { InboxDemo } from "./demos/InboxDemo";
import { LeadsDemo } from "./demos/LeadsDemo";
import { DocumentDemo } from "./demos/DocumentDemo";
import { CallDemo } from "./demos/CallDemo";
import { ReportDemo } from "./demos/ReportDemo";
import { TimelineDemo } from "./demos/TimelineDemo";
import { ChatDemo } from "./demos/ChatDemo";
import { DraftsDemo } from "./demos/DraftsDemo";
import { track } from "./lib";

const KINDS = {
  inbox: InboxDemo, leads: LeadsDemo, document: DocumentDemo, call: CallDemo,
  report: ReportDemo, timeline: TimelineDemo, chat: ChatDemo, drafts: DraftsDemo,
};

export const SampleBadge = ({ label }) => (
  <span
    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--ax-magenta)]/50 bg-[var(--ax-magenta)]/10 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-[var(--ax-magenta)]"
    data-testid="sample-data-badge"
  >
    <Database size={12} /> {label}
  </span>
);

const LiveDemoButton = ({ agent, ui }) => {
  if (!agent.demo_url) return null;
  const isPhone = agent.demo_url.startsWith("tel:");
  return (
    <a
      href={agent.demo_url}
      target={isPhone ? undefined : "_blank"}
      rel="noreferrer"
      onClick={() => track("live_demo_click")}
      className="ax-btn-ghost inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium"
      data-testid="live-demo-button"
    >
      {isPhone ? <Phone size={15} /> : <ExternalLink size={15} />}
      {isPhone ? `${ui.live_demo_phone}: ${agent.demo_label}` : ui.live_demo}
    </a>
  );
};

export const DemoSection = ({ page }) => {
  const Comp = KINDS[page.demo.kind] || InboxDemo;
  return (
    <section id="demo" className="scroll-mt-24 pb-16 sm:pb-24" data-testid="interactive-demo-section">
      <SectionLabel>{page.ui.demo_label}</SectionLabel>
      <div className="ax-card p-5 sm:p-8">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <SampleBadge label={page.ui.sample_badge} />
            <h2 className="mt-4 text-2xl font-bold sm:text-3xl" data-testid="demo-title">{page.demo.title}</h2>
            <p className="mt-2 text-sm text-[var(--ax-muted)] sm:text-base">{page.demo.intro}</p>
          </div>
          <div className="shrink-0"><LiveDemoButton agent={page.agent} ui={page.ui} /></div>
        </div>
        <div onClickCapture={() => track("demo_click")} data-testid={`demo-kind-${page.demo.kind}`}>
          <Comp demo={page.demo} ui={page.ui} />
        </div>
      </div>
    </section>
  );
};

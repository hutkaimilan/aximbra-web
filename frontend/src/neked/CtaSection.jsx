import { ArrowUpRight } from "lucide-react";
import { mailtoHref, offerFor, track } from "./lib";

export const CtaSection = ({ page }) => (
  <section className="pb-20 sm:pb-28" data-testid="cta-section">
    <div className="ax-glow-border relative overflow-hidden px-6 py-12 sm:px-12 sm:py-16">
      <div className="pointer-events-none absolute -right-20 -bottom-24 h-72 w-72 rounded-full bg-[var(--ax-magenta)] opacity-20 blur-[110px]" />
      <div className="relative mb-8 max-w-2xl rounded-2xl border border-[var(--ax-line)] bg-[var(--ax-card)] p-5" data-testid="cta-offer">
        <p className="font-mono text-xs uppercase tracking-wider text-[var(--ax-cyan)]">{offerFor(page.lang)[0]}</p>
        <p className="mt-2 text-base leading-relaxed sm:text-lg">{offerFor(page.lang)[1]}</p>
      </div>
      <h2 className="relative max-w-2xl text-3xl font-bold leading-tight sm:text-4xl">{page.ui.cta}</h2>
      <p className="relative mt-4 max-w-xl text-sm text-[var(--ax-muted)] sm:text-base">{page.ui.cta_sub}</p>
      <a
        href={mailtoHref(page.contact_email, page.company)}
        onClick={() => track("cta_click")}
        className="ax-btn-primary relative mt-8 inline-flex items-center gap-2 rounded-full px-7 py-4 text-base font-semibold"
        data-testid="cta-talk-button"
      >
        {page.ui.cta} <ArrowUpRight size={18} />
      </a>
      <p className="relative mt-4 font-mono text-xs text-[var(--ax-muted)]">{page.contact_email}</p>
    </div>
  </section>
);

import { mailtoHref } from "./lib";
import { track } from "./lib";

export const TopBar = ({ page }) => (
  <header className="sticky top-0 z-30 border-b border-[var(--ax-line)] bg-[#03040a]/85 backdrop-blur-xl" data-testid="top-bar">
    <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
      <a href="https://aximbra.hu" target="_blank" rel="noreferrer" className="flex items-center gap-2.5" data-testid="top-bar-logo">
        <span className="ax-live h-2.5 w-2.5 rounded-full bg-[var(--ax-cyan)]" />
        <span className="font-mono text-sm font-bold tracking-[0.35em]">AXIMBRA</span>
      </a>
      <a
        href={mailtoHref(page.contact_email, page.company)}
        onClick={() => track("cta_click")}
        className="ax-btn-primary rounded-full px-4 py-2 text-sm font-semibold sm:px-5"
        data-testid="top-bar-cta-button"
      >
        {page.ui.cta}
      </a>
    </div>
  </header>
);

export const PageFooter = ({ page }) => (
  <footer className="relative z-[2] border-t border-[var(--ax-line)]" data-testid="page-footer">
    <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8">
      <p className="text-xs text-[var(--ax-muted)] sm:text-sm" data-testid="footer-disclaimer">{page.footer}</p>
      <div className="flex flex-wrap items-center gap-4 font-mono text-xs">
        <a href="https://aximbra.hu/impresszum" className="text-[var(--ax-muted)] hover:text-white">Impresszum</a>
        <a href="https://aximbra.hu/adatkezeles" className="text-[var(--ax-muted)] hover:text-white">Adatkezelés</a>
        <a href="https://aximbra.hu" target="_blank" rel="noreferrer" className="tracking-[0.3em] text-[var(--ax-cyan)]" data-testid="footer-aximbra-link">
          AXIMBRA
        </a>
      </div>
    </div>
  </footer>
);

import { useEffect, useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { useLang, LANGS } from "../i18n";

export const Nav = ({ scrollTo }) => {
  const { t, lang, setLang } = useLang();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let raf;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setScrolled(window.scrollY > 40));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  const go = (id) => { setOpen(false); scrollTo(id); };

  return (
    <nav className={`nav ${scrolled ? "scrolled" : ""}`} data-testid="main-nav">
      <div className="logo" data-testid="logo" onClick={() => go("top")}>
        <span className="dot" /> AXIMBRA
      </div>

      <div className="nav-right">
        <div className="nav-links">
          {t.nav.links.map(([label, id]) => (
            <a key={id} className="link" data-testid={`nav-${id}`} onClick={() => go(id)} tabIndex={0}
               onKeyDown={(e) => e.key === "Enter" && go(id)} role="button">{label}</a>
          ))}
          <a className="btn-callbar" data-testid="nav-callbar" href={t.nav.callbarHref}>{t.nav.callbar}</a>
        </div>

        <select className="lang-select" data-testid="lang-select" value={lang}
          onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {LANGS.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>

        <LiquidButton className="btn-nav nav-contact-desktop" data-testid="nav-contact" onClick={() => go("kapcsolat")}>
          {t.nav.contact}
        </LiquidButton>

        <button className={`nav-burger ${open ? "open" : ""}`} data-testid="nav-burger"
          aria-label="Menü" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span /><span /><span />
        </button>
      </div>

      <div className={`nav-drawer ${open ? "open" : ""}`} data-testid="nav-drawer" aria-hidden={!open}>
        {t.nav.links.map(([label, id]) => (
          <a key={id} className="drawer-link" data-testid={`drawer-${id}`} role="button" tabIndex={open ? 0 : -1}
             onClick={() => go(id)} onKeyDown={(e) => e.key === "Enter" && go(id)}>{label}</a>
        ))}
        <a className="drawer-link" data-testid="drawer-callbar" href={t.nav.callbarHref} onClick={() => setOpen(false)}>
          {t.nav.callbar}
        </a>
        <LiquidButton className="btn-nav drawer-contact" data-testid="drawer-contact" onClick={() => go("kapcsolat")}>
          {t.nav.contact}
        </LiquidButton>
      </div>
    </nav>
  );
};

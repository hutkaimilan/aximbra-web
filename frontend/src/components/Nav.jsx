import { useEffect, useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { useLang, LANGS } from "../i18n";

export const Nav = ({ scrollTo }) => {
  const { t, lang, setLang } = useLang();
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    let raf;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setScrolled(window.scrollY > 40));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  return (
    <nav className={`nav ${scrolled ? "scrolled" : ""}`} data-testid="main-nav">
      <div className="logo" data-testid="logo" onClick={() => scrollTo("top")}>
        <span className="dot" /> AXIMBRA
      </div>
      <div className="nav-links">
        {t.nav.links.map(([label, id]) => (
          <a key={id} className="link" data-testid={`nav-${id}`} onClick={() => scrollTo(id)} tabIndex={0}
             onKeyDown={(e) => e.key === "Enter" && scrollTo(id)} role="button">{label}</a>
        ))}
        <a className="btn-callbar" data-testid="nav-callbar" href={t.nav.callbarHref}>{t.nav.callbar}</a>
        <select className="lang-select" data-testid="lang-select" value={lang}
          onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {LANGS.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>
        <LiquidButton className="btn-nav" data-testid="nav-contact" onClick={() => scrollTo("kapcsolat")}>
          {t.nav.contact}
        </LiquidButton>
      </div>
    </nav>
  );
};

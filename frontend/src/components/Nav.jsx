import { useEffect, useRef, useState } from "react";
import { LiquidButton } from "./LiquidButton";
import { Link } from "react-router-dom";
import { useLang, LANGS, pathFor } from "../i18n";

export const Nav = ({ scrollTo }) => {
  const { t, lang, setLang } = useLang();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const navRef = useRef(null);

  useEffect(() => {
    let raf;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setScrolled(window.scrollY > 40));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, []);

  // Close mobile drawer on outside tap or on scroll
  useEffect(() => {
    if (!open) return;
    const onPointer = (e) => { if (navRef.current && !navRef.current.contains(e.target)) setOpen(false); };
    const onScroll = () => setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("wheel", onScroll, { passive: true });
    window.addEventListener("touchmove", onScroll, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("wheel", onScroll);
      window.removeEventListener("touchmove", onScroll);
    };
  }, [open]);

  const go = (id) => { setOpen(false); scrollTo(id); };

  return (
    <nav ref={navRef} className={`nav ${scrolled ? "scrolled" : ""}`} data-testid="main-nav">
      <a className="logo" data-testid="logo" href="#top"
         onClick={(e) => { e.preventDefault(); go("top"); }} aria-label="AXIMBRA">
        <span className="dot" /> AXIMBRA
      </a>

      <div className="nav-right">
        <div className="nav-links">
          {/* A harmadik elem egy útvonal: az a menüpont nem a lapon belülre
              ugrik, hanem másik oldalra visz — a nyelvi előtagot megtartva. */}
          {t.nav.links.map(([label, id, route]) => (route ? (
            <Link key={id} className="link" data-testid={`nav-${id}`}
                  to={pathFor(lang, route)} onClick={() => setOpen(false)}>{label}</Link>
          ) : (
            <a key={id} className="link" data-testid={`nav-${id}`} href={`#${id}`}
               onClick={(e) => { e.preventDefault(); go(id); }}>{label}</a>
          )))}
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
        {t.nav.links.map(([label, id, route]) => (route ? (
          <Link key={id} className="drawer-link" data-testid={`drawer-${id}`}
                to={pathFor(lang, route)} tabIndex={open ? 0 : -1}
                onClick={() => setOpen(false)}>{label}</Link>
        ) : (
          <a key={id} className="drawer-link" data-testid={`drawer-${id}`} href={`#${id}`}
             tabIndex={open ? 0 : -1} onClick={(e) => { e.preventDefault(); go(id); }}>{label}</a>
        )))}
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

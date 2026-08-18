import { useEffect, useState } from "react";
import { LiquidButton } from "./LiquidButton";

export const Nav = ({ scrollTo }) => {
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

  const links = [
    ["Agentek", "agentek"], ["Folyamat", "folyamat"], ["Árak", "arak"], ["Esettanulmány", "eset"],
  ];

  return (
    <nav className={`nav ${scrolled ? "scrolled" : ""}`} data-testid="main-nav">
      <div className="logo" data-testid="logo" onClick={() => scrollTo("top")}>
        <span className="dot" /> AXIMBRA
      </div>
      <div className="nav-links">
        {links.map(([label, id]) => (
          <a key={id} className="link" data-testid={`nav-${id}`} onClick={() => scrollTo(id)} tabIndex={0}
             onKeyDown={(e) => e.key === "Enter" && scrollTo(id)} role="button">{label}</a>
        ))}
        <LiquidButton className="btn-nav" data-testid="nav-contact" onClick={() => scrollTo("kapcsolat")}>
          KAPCSOLAT
        </LiquidButton>
      </div>
    </nav>
  );
};

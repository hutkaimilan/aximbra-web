import { useEffect, useState } from "react";
import { useLang } from "../i18n";

const LETTERS = "AXIMBRA".split("");

// The wordmark plays on every load of the page, by choice: it is the first
// thing the brand says, and a visitor arriving from a search result should get
// it whether or not they have been here before. An earlier version remembered
// each visitor in localStorage and showed it once, ever - that is the line to
// change if it should go back to being once per visitor.
//
// `skip` is a different matter and stays: it covers coming back from a demo
// page inside the same visit, where replaying the intro would feel like the
// site had reloaded under the visitor.
export const Intro = ({ skip }) => {
  const { t } = useLang();
  // Read once, on mount: re-reading during the run would hide it mid-animation.
  const [suppressed] = useState(() => skip);
  const [hide, setHide] = useState(false);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (suppressed) return undefined;
    document.body.classList.add("lock");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const delay = reduce ? 200 : 2600;
    const t1 = setTimeout(() => setHide(true), delay);
    const t2 = setTimeout(() => { setGone(true); document.body.classList.remove("lock"); }, delay + 850);

    // Aki dolgozni jott, ne varjon ra.
    //
    // Az animacio 2,6 masodpercig takarja a fejlecet, es addig a lap sem
    // gorgetheto. Aki a talalati listarol erkezik es rogton a KAPCSOLAT
    // gombra menne, halott kattintast kap - meresen pontosan ennyi ideig.
    // A marka-pillanat marad mindenki masnak; ez csak kiutat ad belole.
    const skipNow = () => { setHide(true); setTimeout(() => { setGone(true); document.body.classList.remove("lock"); }, 300); };
    window.addEventListener("pointerdown", skipNow, { once: true });
    window.addEventListener("keydown", skipNow, { once: true });
    window.addEventListener("wheel", skipNow, { once: true, passive: true });

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      window.removeEventListener("pointerdown", skipNow);
      window.removeEventListener("keydown", skipNow);
      window.removeEventListener("wheel", skipNow);
      document.body.classList.remove("lock");
    };
  }, [suppressed]);

  if (suppressed || gone) return null;

  return (
    <div className={`intro ${hide ? "hide" : ""}`} data-testid="intro-overlay" aria-hidden="true">
      <div className="intro-word">
        {LETTERS.map((l, i) => (
          <span key={i} style={{ animationDelay: `${i * 85}ms` }}>{l}</span>
        ))}
      </div>
      <div className="intro-line" />
      <div className="intro-cap">{t.nav.intro}</div>
    </div>
  );
};

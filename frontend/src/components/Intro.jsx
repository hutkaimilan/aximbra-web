import { useEffect, useState } from "react";
import { useLang } from "../i18n";

const LETTERS = "AXIMBRA".split("");

// The 2.6s wordmark is worth it once. On every later visit it is a toll on
// someone who already knows the brand, so it plays once per visitor rather than
// once per tab. localStorage can throw (private mode, blocked site data), and a
// visitor who cannot be remembered simply sees the animation again.
const SEEN_KEY = "aximbra:intro-seen";
const hasSeenIntro = () => {
  try { return localStorage.getItem(SEEN_KEY) !== null; } catch { return false; }
};
const markIntroSeen = () => {
  try { localStorage.setItem(SEEN_KEY, "1"); } catch { /* not remembered, no harm */ }
};

export const Intro = ({ skip }) => {
  const { t } = useLang();
  // Read once, on mount: re-reading during the run would hide it mid-animation.
  const [suppressed] = useState(() => skip || hasSeenIntro());
  const [hide, setHide] = useState(false);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (suppressed) return;
    markIntroSeen();
    document.body.classList.add("lock");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const delay = reduce ? 200 : 2600;
    const t1 = setTimeout(() => setHide(true), delay);
    const t2 = setTimeout(() => { setGone(true); document.body.classList.remove("lock"); }, delay + 850);
    return () => { clearTimeout(t1); clearTimeout(t2); document.body.classList.remove("lock"); };
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

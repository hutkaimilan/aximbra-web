import { useEffect, useState } from "react";

const LETTERS = "AXIMBRA".split("");

export const Intro = ({ skip }) => {
  const [hide, setHide] = useState(false);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (skip) return;
    document.body.classList.add("lock");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const delay = reduce ? 200 : 2600;
    const t1 = setTimeout(() => setHide(true), delay);
    const t2 = setTimeout(() => { setGone(true); document.body.classList.remove("lock"); }, delay + 850);
    return () => { clearTimeout(t1); clearTimeout(t2); document.body.classList.remove("lock"); };
  }, [skip]);

  if (skip || gone) return null;

  return (
    <div className={`intro ${hide ? "hide" : ""}`} data-testid="intro-overlay" aria-hidden="true">
      <div className="intro-word">
        {LETTERS.map((l, i) => (
          <span key={i} style={{ animationDelay: `${i * 85}ms` }}>{l}</span>
        ))}
      </div>
      <div className="intro-line" />
      <div className="intro-cap">AI AGENTEK · BUDAPEST</div>
    </div>
  );
};

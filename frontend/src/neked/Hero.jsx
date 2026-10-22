import { ArrowDown } from "lucide-react";

const Highlight = ({ text, word }) => {
  const i = word ? text.indexOf(word) : -1;
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <span className="ax-gradient-text">{word}</span>
      {text.slice(i + word.length)}
    </>
  );
};

const hostOf = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

export const Hero = ({ page }) => (
  <section className="relative pt-16 pb-14 sm:pt-24 sm:pb-20" data-testid="hero-section">
    <div className="pointer-events-none absolute -top-20 -left-32 h-80 w-80 rounded-full bg-[var(--ax-purple)] opacity-20 blur-[120px]" />
    <div className="pointer-events-none absolute top-10 right-0 h-64 w-64 rounded-full bg-[var(--ax-cyan)] opacity-10 blur-[110px]" />
    <p className="ax-rise font-mono text-xs tracking-[0.25em] text-[var(--ax-cyan)] mb-6" data-testid="hero-domain">
      // {hostOf(page.url)}
    </p>
    <h1
      className="ax-rise max-w-4xl text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl break-words"
      style={{ animationDelay: "0.08s" }}
      data-testid="hero-title"
    >
      <Highlight text={page.title} word={page.company} />
    </h1>
    {page.hero_subtitle && (
      <p className="ax-rise mt-6 max-w-2xl text-base text-[var(--ax-muted)] md:text-lg" style={{ animationDelay: "0.16s" }} data-testid="hero-subtitle">
        {page.hero_subtitle}
      </p>
    )}
    <div className="ax-rise mt-10 flex flex-wrap gap-3" style={{ animationDelay: "0.24s" }}>
      <a href="#demo" className="ax-btn-ghost inline-flex items-center gap-2 rounded-full px-6 py-3 font-medium" data-testid="hero-demo-link">
        {page.ui.demo_label} <ArrowDown size={16} />
      </a>
    </div>
  </section>
);

import { ExternalLink, Quote } from "lucide-react";

const shortUrl = (url) => {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "") + (u.pathname === "/" ? "" : decodeURI(u.pathname));
  } catch {
    return url;
  }
};

export const SectionLabel = ({ children, testId }) => (
  <p className="font-mono text-xs uppercase tracking-[0.25em] text-[var(--ax-muted)] mb-5" data-testid={testId}>
    {children}
  </p>
);

const MARKS = { hu: ["„", "”"], de: ["„", "“"], pl: ["„", "”"], cs: ["„", "“"], fr: ["« ", " »"], es: ["«", "»"], it: ["«", "»"], ru: ["«", "»"], ja: ["「", "」"], zh: ["“", "”"] };

const marksFor = (lang) => MARKS[(lang || "").slice(0, 2).toLowerCase()] || ["“", "”"];

export const QuoteCard = ({ obs, ui, lang }) => (
  <section className="pb-16 sm:pb-24" data-testid="verified-quote-card">
    <SectionLabel>{ui.observation_label}</SectionLabel>
    <div className="ax-card relative overflow-hidden p-6 sm:p-10">
      <div className="absolute left-0 top-0 h-full w-1 bg-gradient-to-b from-[var(--ax-cyan)] via-[var(--ax-purple)] to-[var(--ax-magenta)]" />
      <Quote className="mb-4 text-[var(--ax-purple)]" size={28} />
      <blockquote className="text-xl font-medium leading-snug sm:text-2xl break-words" data-testid="quote-text">
        {marksFor(lang)[0]}{obs.quote}{marksFor(lang)[1]}
      </blockquote>
      {obs.insight && (
        <p className="mt-5 max-w-3xl text-sm text-[var(--ax-muted)] sm:text-base" data-testid="quote-insight">
          {obs.insight}
        </p>
      )}
      <a
        href={obs.page_url}
        target="_blank"
        rel="noreferrer nofollow"
        className="mt-6 inline-flex max-w-full items-center gap-2 font-mono text-xs text-[var(--ax-cyan)] hover:underline"
        data-testid="quote-source-link"
      >
        <span className="shrink-0">{ui.observation_source}:</span>
        <span className="truncate">{shortUrl(obs.page_url)}</span>
        <ExternalLink size={12} className="shrink-0" />
      </a>
    </div>
  </section>
);

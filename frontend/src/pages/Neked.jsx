import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import "./neked.css";
import { useDocumentMeta } from "../seo";
import { stateText } from "./nekedText";
import { SALES, setTrackSlug, track } from "../neked/lib";
import { TopBar } from "../neked/TopBar";
import { Hero } from "../neked/Hero";
import { QuoteCard } from "../neked/QuoteCard";
import { AgentSection } from "../neked/AgentSection";
import { DemoSection } from "../neked/DemoSection";
import { RoiCalculator } from "../neked/RoiCalculator";
import { CtaSection } from "../neked/CtaSection";
import { PageFooter } from "../neked/PageFooter";

/**
 * aximbra.hu/neked/:slug — egy megkeresett cégnek készült demóoldal.
 *
 * A megjelenés és a szakaszok az Emergent-féle demóoldalból jönnek
 * (src/neked/), a tartalmat a sales agent állítja össze
 * (sales-agent/demopage.py). Itt a betöltés, a mérés és az állapotok vannak.
 *
 * ?preview=1: a saját ellenőrzésünk, nem számít megnyitásnak.
 */

/** Betöltés: a sales agent alszik, ha nincs forgalom, az első kérés lassú lehet. */
function usePage(slug) {
  const [state, setState] = useState({ status: "loading", slow: false, data: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    const slowTimer = setTimeout(() => alive && setState((s) => ({ ...s, slow: true })), 4000);
    (async () => {
      for (let i = 0; i < 3 && alive; i++) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 30000);
        try {
          const r = await fetch(`${SALES}/public/neked/${encodeURIComponent(slug)}`, { signal: ctrl.signal });
          clearTimeout(timer);
          if (r.status === 404) {
            if (alive) setState({ status: "gone", data: null });
            return;
          }
          if (!r.ok) throw new Error(String(r.status));
          const data = await r.json();
          if (alive) setState({ status: "ready", data });
          return;
        } catch {
          clearTimeout(timer);
          await new Promise((res) => setTimeout(res, 1500 * (i + 1)));
        }
      }
      if (alive) setState({ status: "error", data: null });
    })();
    return () => {
      alive = false;
      clearTimeout(slowTimer);
    };
  }, [slug, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading", slow: false, data: null });
    setAttempt((a) => a + 1);
  }, []);
  return [state, retry];
}

export default function Neked() {
  const { slug = "" } = useParams();
  const [{ status, slow, data }, retry] = usePage(slug);

  useDocumentMeta({
    title: data ? `${data.title} · AXIMBRA` : "AXIMBRA",
    description: data ? data.hero_subtitle || data.title : "AXIMBRA",
    path: `/neked/${slug}`,
    lang: data?.lang,
    noindex: true,
    translated: false,
  });

  useEffect(() => {
    if (!data) return;
    document.documentElement.lang = data.lang;
    setTrackSlug(slug);
    track("open");
  }, [data, slug]);

  if (status !== "ready") {
    const t = stateText(navigator.language);
    return (
      <div className="nk-ax ax-grid min-h-screen flex flex-col items-center justify-center gap-4 px-5 text-center" data-testid="demo-page-state">
        {status === "loading" && (
          <>
            <div className="flex gap-2" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <span key={i} className="ax-dot h-2.5 w-2.5 rounded-full bg-[var(--ax-cyan)]" style={{ animationDelay: `${i * 0.18}s` }} />
              ))}
            </div>
            <p className="text-sm text-[var(--ax-muted)]">{t.loading}</p>
            {slow && <p className="text-xs text-[var(--ax-muted)]">{t.slow}</p>}
          </>
        )}
        {status === "gone" && (
          <>
            <h1 className="text-2xl font-bold">{t.goneTitle}</h1>
            <p className="max-w-md text-[var(--ax-muted)]">{t.goneText}</p>
            <a href="mailto:aximbra@gmail.com" className="ax-btn-primary rounded-full px-6 py-3 font-semibold">aximbra@gmail.com</a>
          </>
        )}
        {status === "error" && (
          <>
            <p className="text-[var(--ax-muted)]">{t.errorText}</p>
            <button type="button" onClick={retry} className="ax-btn-primary rounded-full px-6 py-3 font-semibold">{t.retry}</button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="nk-ax ax-noise ax-grid min-h-screen overflow-x-hidden" data-testid="demo-page">
      <TopBar page={data} />
      <main className="relative z-[2] mx-auto max-w-6xl px-5 sm:px-8">
        <Hero page={data} />
        {data.observation && <QuoteCard obs={data.observation} ui={data.ui} lang={data.lang} />}
        <AgentSection page={data} />
        <DemoSection page={data} />
        <RoiCalculator key={slug} page={data} />
        <CtaSection page={data} />
      </main>
      <PageFooter page={data} />
    </div>
  );
}

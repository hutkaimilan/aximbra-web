import { useEffect, useRef } from "react";
import Lenis from "lenis";
import "@/index.css";
import { Intro } from "@/components/Intro";
import { PlasmaHero } from "@/components/PlasmaHero";
import { Nav } from "@/components/Nav";
import { Hero } from "@/components/Hero";
import { Agents } from "@/components/Agents";
import { Process } from "@/components/Process";
import { Pricing } from "@/components/Pricing";
import { CaseStudy } from "@/components/CaseStudy";
import { Contact, Footer } from "@/components/Contact";
import { References } from "@/components/References";
import { Founder } from "@/components/Founder";
import { LanguageProvider, useLang, PREFIXED_LANGS } from "@/i18n";
import { useDocumentMeta, organizationJsonLd } from "@/seo";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Etterem from "@/demos/Etterem";
import Szalon from "@/demos/Szalon";
import Rendelo from "@/demos/Rendelo";
import Ugyvedi from "@/demos/Ugyvedi";
import EmailAgent from "@/demos/EmailAgent";
import Impresszum from "@/pages/Impresszum";
import Adatkezeles from "@/pages/Adatkezeles";
import Weboldal from "@/pages/Weboldal";

function Site() {
  const { t, lang } = useLang();
  useDocumentMeta({
    title: t.seo.title,
    description: t.seo.description,
    path: "/",
    lang,
    jsonLd: organizationJsonLd(t.seo.description),
  });
  const lenisRef = useRef(null);
  const returningRef = useRef(sessionStorage.getItem("aximbra:return") !== null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const lenis = new Lenis({ duration: 1.1, smoothWheel: true });
    lenisRef.current = lenis;
    let raf;
    const loop = (t) => { lenis.raf(t); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); lenis.destroy(); };
  }, []);

  // Restore exact scroll position when returning from a demo page
  useEffect(() => {
    const saved = sessionStorage.getItem("aximbra:return");
    if (saved === null) return;
    sessionStorage.removeItem("aximbra:return");
    const y = parseInt(saved, 10) || 0;
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (lenisRef.current) lenisRef.current.scrollTo(y, { immediate: true, force: true });
        else window.scrollTo(0, y);
      });
    });
  }, []);

  const scrollTo = (id) => {
    if (id === "top") {
      lenisRef.current ? lenisRef.current.scrollTo(0) : window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const el = document.getElementById(id);
    if (!el) return;
    if (lenisRef.current) lenisRef.current.scrollTo(el, { offset: -80 });
    else el.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className={`App${returningRef.current ? " restore" : ""}`}>
      <Intro skip={returningRef.current} />
      <PlasmaHero />
      <div className="plasma-veil" />
      <div className="grain" />
      <Nav scrollTo={scrollTo} />
      <main className="wrap">
        <Hero scrollTo={scrollTo} />
        <div className="marquee" aria-hidden="true">
          <div className="marquee-track">
            {[...t.marquee, ...t.marquee].map((m, i) => <span key={i}>{m}</span>)}
          </div>
        </div>
        <Agents />
        <Process />
        <Pricing />
        <CaseStudy />
        <References />
        <Founder />
        <Contact />
      </main>
      <Footer />
    </div>
  );
}

/** Every page, once — then mounted at the root and under each language prefix.
 *  Listing them twice by hand is how one language quietly ends up missing a page. */
const PAGES = [
  { path: "", element: <Site /> },
  { path: "agent/:slug", element: <Site /> },
  { path: "demo/etterem", element: <Etterem /> },
  { path: "demo/szalon", element: <Szalon /> },
  { path: "demo/rendelo", element: <Rendelo /> },
  { path: "demo/ugyvedi", element: <Ugyvedi /> },
  { path: "demo/email-agent", element: <EmailAgent /> },
  { path: "weboldal", element: <Weboldal /> },
  { path: "impresszum", element: <Impresszum /> },
  { path: "adatkezeles", element: <Adatkezeles /> },
];

export default function App() {
  return (
    // The router wraps the provider, not the other way round: the language now
    // comes from the URL, so the provider has to be able to read it.
    <BrowserRouter>
      <LanguageProvider>
        <Routes>
          {PAGES.map((p) => (
            <Route key={p.path} path={`/${p.path}`} element={p.element} />
          ))}
          {PREFIXED_LANGS.map((code) =>
            PAGES.map((p) => (
              <Route key={`${code}/${p.path}`} path={`/${code}/${p.path}`} element={p.element} />
            ))
          )}
          {/* Unknown path: hand it to the homepage rather than a blank screen. */}
          <Route path="*" element={<Site />} />
        </Routes>
      </LanguageProvider>
    </BrowserRouter>
  );
}

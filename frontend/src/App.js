import { useEffect, useLayoutEffect, useRef } from "react";
import Lenis from "lenis";
import "@/index.css";
import { Intro } from "@/components/Intro";
import { PlasmaHero } from "@/components/PlasmaHero";
import { Nav } from "@/components/Nav";
import { Hero } from "@/components/Hero";
import { Agents } from "@/components/Agents";
import { Process } from "@/components/Process";
import { Proof } from "@/components/Proof";
import { NoTricks } from "@/components/NoTricks";
import { Objections } from "@/components/Objections";
import { FirstStep } from "@/components/FirstStep";
import { CaseStudy } from "@/components/CaseStudy";
import { Contact, Footer } from "@/components/Contact";
import { WebShowcase } from "@/components/WebShowcase";
import { Founder } from "@/components/Founder";
import { Payback } from "@/components/Payback";
import { OfferBand } from "@/components/OfferBand";
import { LanguageProvider, useLang, PREFIXED_LANGS } from "@/i18n";
import { useDocumentMeta, organizationJsonLd } from "@/seo";
import { BrowserRouter, Routes, Route, Navigate, useLocation, matchPath } from "react-router-dom";
import NotFound from "./pages/NotFound";
import { useVisitBeacon } from "./visits";
import Etterem from "@/demos/Etterem";
import Fogaszat from "@/demos/Fogaszat";
import Webshop from "@/demos/Webshop";
import Ugyvedi from "@/demos/Ugyvedi";
import EmailAgent from "@/demos/EmailAgent";
import Impresszum from "@/pages/Impresszum";
import Adatkezeles from "@/pages/Adatkezeles";
import Weboldal from "@/pages/Weboldal";
import Neked from "@/pages/Neked";

let reloadChecked = false;

function Site({ visible = true }) {
  const { t, lang } = useLang();
  useDocumentMeta({
    // Ures cim = "most nem en vagyok a lap": rejtve ne irja felul az impresszum
    // cimet, visszaterve pedig (a cim valtozasa miatt) ujra beallitja a sajatjat.
    title: visible ? t.seo.title : "",
    description: t.seo.description,
    path: "/",
    lang,
    jsonLd: organizationJsonLd(t.seo.description),
  });
  const lenisRef = useRef(null);
  const visibleRef = useRef(visible);
  const returningRef = useRef((() => {
    try {
      // F5-nel a teljes nyitas jar (animacioval, a lap tetejen): egy kattintas
      // utan bennmaradt ertek ne ugrassa a latogatot egy regi pozicioba.
      // Csak a dokumentum elso betoltesekor: a navigation-bejegyzes az egesz
      // munkamenetben "reload" marad, a kesobbi SPA-visszatereseket nem torolheti.
      if (!reloadChecked) {
        reloadChecked = true;
        const nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
        if (nav && nav.type === "reload") sessionStorage.removeItem("aximbra:return");
      }
      return sessionStorage.getItem("aximbra:return") !== null;
    } catch {
      return false;
    }
  })());

  // Barmilyen belso lapra lepve (impresszum, adatkezeles, weboldal-csomagok,
  // demo) megjegyezzuk, hol tartott. Visszafele igy nem fut le ujra a nyito-
  // animacio, es ugyanoda kerul - kulonben ugy hat, mintha ujratoltott volna a
  // lap. A kattintas pillanataban mentunk: az unmount utan a bongeszo mar a
  // rovidebb uj laphoz igazitotta a gorgetest, az a szam rossz lenne.
  useEffect(() => {
    const onClick = (e) => {
      // Rejtve (az impresszumon vagyunk) az ottani kattintas nem a mi helyunk.
      if (!visibleRef.current) return;
      const a = e.target.closest && e.target.closest("a[href]");
      if (!a || a.target === "_blank") return;
      const href = a.getAttribute("href") || "";
      if (!href.startsWith("/") || href.startsWith("//")) return;
      try { sessionStorage.setItem("aximbra:return", String(window.scrollY)); } catch { /* privat mod */ }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

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
    const go = () => {
      if (lenisRef.current) lenisRef.current.scrollTo(y, { immediate: true, force: true });
      else window.scrollTo(0, y);
    };
    requestAnimationFrame(() => requestAnimationFrame(go));
    // A lap alja (kepek, demo-elonezetek) kesobb nyeri el a vegleges magassagat;
    // addig a cel tul lehet a gorgetheto hosszon. Par ujraprobalas, amig a
    // latogato maga nem gorget.
    let touched = false;
    const stop = () => { touched = true; };
    window.addEventListener("wheel", stop, { passive: true, once: true });
    window.addEventListener("touchstart", stop, { passive: true, once: true });
    const timers = [250, 600, 1200].map((ms) => setTimeout(() => {
      if (!touched && Math.abs(window.scrollY - y) > 40) go();
    }, ms));
    return () => {
      timers.forEach(clearTimeout);
      window.removeEventListener("wheel", stop);
      window.removeEventListener("touchstart", stop);
    };
  }, []);

  // A fooldal belso lapra lepve nem szunik meg, csak elrejtodik (lasd Shell).
  // Elrejteskor a masik lap a tetejen kezdodik; visszaterve egyetlen ugrassal
  // ott vagyunk, ahol a latogato kattintott - a lap mar teljes magassagu, nincs
  // ujrarajzolas, animacio vagy tobbszori igazitas.
  const firstVisibility = useRef(true);
  // Layout effect: a gorgetes a festes elott a helyere kerul, egy kocka
  // erejeig sem latszik a rossz pozicio.
  useLayoutEffect(() => {
    visibleRef.current = visible;
    if (firstVisibility.current) { firstVisibility.current = false; return; }
    const lenis = lenisRef.current;
    if (!visible) {
      document.body.classList.add("site-hidden");
      if (lenis) lenis.scrollTo(0, { immediate: true, force: true });
      else window.scrollTo(0, 0);
      return;
    }
    document.body.classList.remove("site-hidden");
    let y = 0;
    try {
      y = parseInt(sessionStorage.getItem("aximbra:return"), 10) || 0;
      sessionStorage.removeItem("aximbra:return");
    } catch { /* privat mod */ }
    if (lenis) { lenis.resize(); lenis.scrollTo(y, { immediate: true, force: true }); }
    else window.scrollTo(0, y);
  }, [visible]);
  useEffect(() => () => document.body.classList.remove("site-hidden"), []);

  const scrollTo = (id) => {
    if (id === "top") {
      lenisRef.current ? lenisRef.current.scrollTo(0) : window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const el = document.getElementById(id);
    // A visszahivo urlap csak akkor letezik, ha a telefon-agent el; ha nincs
    // ott, a lap teteje (a telefonszam) a legkozelebbi ertelmes cel.
    if (!el) {
      if (id === "visszahivas") scrollTo("top");
      return;
    }
    if (lenisRef.current) lenisRef.current.scrollTo(el, { offset: -80 });
    else el.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className={`App${returningRef.current ? " restore" : ""}`} style={visible ? undefined : { display: "none" }}>
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
        {/* A sorrend nem ízlés kérdése. Előbb az, amit a látogató ELLENŐRIZNI
            tud, aztán amit kap, aztán a bizonyíték, hogy működik, és csak ezek
            után az ár. Eddig fordítva volt: az árazás a két bizonyító szakasz
            ELŐTT állt, tehát a költséget azelőtt kellett mérlegelni, hogy
            bármit látott volna belőle. Az ellenvetések közvetlenül a bizonyíték
            után jönnek, mert ott fogalmazódnak meg; a folyamat és a készítő
            utánuk válaszol rájuk, az ár pedig a legvégén áll, amikor már van
            mihez viszonyítani. */}
        <OfferBand />
        <Proof scrollTo={scrollTo} />
        <Agents />
        <div className="container"><WebShowcase /></div>
        <CaseStudy />
        <Objections />
        <Payback />
        <Process />
        <Founder />
        <NoTricks />
        <FirstStep />
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
  { path: "demo/fogaszat", element: <Fogaszat /> },
  { path: "demo/webshop", element: <Webshop /> },
  // A régi demók címei: a már kiküldött linkek ne vezessenek 404-re.
  { path: "demo/rendelo", element: <Navigate to="../fogaszat" relative="path" replace /> },
  { path: "demo/szalon", element: <Navigate to="../webshop" relative="path" replace /> },
  { path: "demo/ugyvedi", element: <Ugyvedi /> },
  { path: "demo/email-agent", element: <EmailAgent /> },
  { path: "weboldal", element: <Weboldal /> },
  { path: "impresszum", element: <Impresszum /> },
  { path: "adatkezeles", element: <Adatkezeles /> },
];

/**
 * Semmit nem rajzol - csak jelzi a szervernek, hogy valaki megnyitott egy
 * lapot. Kulon komponens, mert a useLocation csak a routeren BELUL mukodik.
 */
function VisitBeacon() {
  const { lang } = useLang();
  useVisitBeacon(lang);
  return null;
}

// A gorgetest mi allitjuk vissza (Site, aximbra:return). A bongeszo sajat
// visszaallitasa ugyanarra a pillanatra egy masik, korabbi erteket tenne, es
// a lap visszalepeskor egyet ugrana.
if (typeof window !== "undefined" && "scrollRestoration" in window.history) {
  window.history.scrollRestoration = "manual";
}

const HOME_PATTERNS = ["/", "/agent/:slug",
  ...PREFIXED_LANGS.flatMap((c) => [`/${c}`, `/${c}/agent/:slug`])];
const isHomePath = (pathname) => HOME_PATTERNS.some((p) => matchPath({ path: p, end: true }, pathname));
const HOME_PAGES = PAGES.filter((p) => p.path === "" || p.path === "agent/:slug");
const OTHER_PAGES = PAGES.filter((p) => !HOME_PAGES.includes(p));

/**
 * A fooldal egyszer felepul, es belso lapra (impresszum, adatkezeles, demo,
 * weboldal) lepve csak elrejtodik. Korabban minden visszalepesnel ujraepult:
 * ujra lefutott a nyitoanimacio, a lap nulla magassagrol nott vissza, es a
 * gorgetes ugralt, amig utolerte. A rejtett fooldal az utolso sajat cimen
 * marad (Routes location), igy az /agent/:slug parameter sem vesz el.
 */
function Shell() {
  const location = useLocation();
  const home = isHomePath(location.pathname);
  const lastHome = useRef(home ? location : null);
  if (home) lastHome.current = location;

  const homeRoutes = (visible) => (
    <>
      {HOME_PAGES.map((p) => (
        <Route key={p.path} path={`/${p.path}`} element={<Site visible={visible} />} />
      ))}
      {PREFIXED_LANGS.map((code) =>
        HOME_PAGES.map((p) => (
          <Route key={`${code}/${p.path}`} path={`/${code}/${p.path}`} element={<Site visible={visible} />} />
        ))
      )}
    </>
  );

  return (
    <>
      {lastHome.current && <Routes location={lastHome.current}>{homeRoutes(home)}</Routes>}
      {!home && (
        <Routes>
          {OTHER_PAGES.map((p) => (
            <Route key={p.path} path={`/${p.path}`} element={p.element} />
          ))}
          {PREFIXED_LANGS.map((code) =>
            OTHER_PAGES.map((p) => (
              <Route key={`${code}/${p.path}`} path={`/${code}/${p.path}`} element={p.element} />
            ))
          )}
          {/* Egy cégnek készült demóoldal. Nyelvi előtag nélkül: a nyelvét a cég
              oldala dönti el, nem az URL. */}
          <Route path="/neked/:slug" element={<Neked />} />
          {/* Ismeretlen cim: sajat lap, `noindex`-szel. */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      )}
    </>
  );
}

export default function App() {
  return (
    // The router wraps the provider, not the other way round: the language now
    // comes from the URL, so the provider has to be able to read it.
    <BrowserRouter>
      <LanguageProvider>
        <VisitBeacon />
        <Shell />
      </LanguageProvider>
    </BrowserRouter>
  );
}

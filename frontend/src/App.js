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
import { LanguageProvider, useLang } from "@/i18n";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Etterem from "@/demos/Etterem";
import Szalon from "@/demos/Szalon";
import Rendelo from "@/demos/Rendelo";
import Ugyvedi from "@/demos/Ugyvedi";

function Site() {
  const { t } = useLang();
  const lenisRef = useRef(null);

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
    <div className="App">
      <Intro />
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
        <Contact />
      </main>
      <Footer />
    </div>
  );
}

export default function App() {
  return (
    <LanguageProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Site />} />
          <Route path="/agent/:slug" element={<Site />} />
          <Route path="/demo/etterem" element={<Etterem />} />
          <Route path="/demo/szalon" element={<Szalon />} />
          <Route path="/demo/rendelo" element={<Rendelo />} />
          <Route path="/demo/ugyvedi" element={<Ugyvedi />} />
        </Routes>
      </BrowserRouter>
    </LanguageProvider>
  );
}

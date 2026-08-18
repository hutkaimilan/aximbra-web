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

function App() {
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
            <span>AGENTEK, NEM CHATBOTOK</span><span>EMBERI JÓVÁHAGYÁS</span><span>BUDAPEST</span>
            <span>HU · EN · ES</span><span>MŰKÖDŐ RENDSZER</span>
            <span>AGENTEK, NEM CHATBOTOK</span><span>EMBERI JÓVÁHAGYÁS</span><span>BUDAPEST</span>
            <span>HU · EN · ES</span><span>MŰKÖDŐ RENDSZER</span>
          </div>
        </div>
        <Agents />
        <Process />
        <Pricing />
        <CaseStudy />
        <Contact />
      </main>
      <Footer />
    </div>
  );
}

export default App;

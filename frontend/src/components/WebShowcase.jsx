import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useLang, pathFor } from "../i18n";
import "./webshowcase.css";

const SITES = [
  { to: "/demo/fogaszat", accent: "#5FC4B0" },
  { to: "/demo/etterem", accent: "#FF6B2C" },
  { to: "/demo/ugyvedi", accent: "#C9A063" },
  { to: "/demo/webshop", accent: "#C8643B" },
];
const W = 1280, H = 800;

/** Élő, kicsinyített előnézet: a valódi demóoldal fut benne, nem egy képernyőkép.
 *  Csak akkor töltődik be, amikor a kártya a képernyő közelébe ér. */
const Preview = ({ src, title }) => {
  const box = useRef(null);
  const [scale, setScale] = useState(0.25);
  const [load, setLoad] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => setScale(el.clientWidth / W);
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setLoad(true); io.disconnect(); } }, { rootMargin: "300px" });
    io.observe(el);
    return () => { ro.disconnect(); io.disconnect(); };
  }, []);
  return (
    <div ref={box} className="wsc-prev" style={{ height: H * scale }}>
      {load && <iframe src={src} title={title} tabIndex={-1} aria-hidden="true" loading="lazy"
        style={{ width: W, height: H, transform: `scale(${scale})` }} />}
    </div>
  );
};

export const WebShowcase = () => {
  const { t, lang } = useLang();
  const r = t.demos.refs;
  return (
    <section className="wsc" id="referenciak" data-testid="web-showcase">
      <span className="tag">{r.tag}</span>
      <h2 className="h-sec">{r.heading}</h2>
      <p className="sub wsc-sub">{r.sub}</p>
      <div className="wsc-grid">
        {r.cards.map((c, i) => {
          const to = pathFor(lang, SITES[i].to);
          return (
            <Link key={SITES[i].to} to={to} className="wsc-card" style={{ "--accent": SITES[i].accent }}
              onClick={() => sessionStorage.setItem("aximbra:return", String(window.scrollY))}>
              <div className="wsc-frame">
                <div className="wsc-chrome"><i /><i /><i /><span>aximbra.hu{to}</span></div>
                <Preview src={to} title={c.title} />
              </div>
              <div className="wsc-body">
                <span className="wsc-tag">{c.tag}</span>
                <div className="wsc-title">{c.title}</div>
                <p>{c.desc}</p>
                <span className="wsc-cta">{r.view}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
};

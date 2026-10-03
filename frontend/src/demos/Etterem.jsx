import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, Flame, ChevronLeft, ChevronRight } from "lucide-react";
import "./etterem.css";
import { DemoBar } from "./DemoBar";
import { Rise, reduceMotion, useDemo, useFonts } from "./kit";
import C from "./content/etterem";

/** A védjegy: felszálló parázs a hős mögött (canvas, a látogató gépét kímélve). */
const Embers = () => {
  const ref = useRef(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv || reduceMotion()) return;
    const ctx = cv.getContext("2d");
    let w, h, raf, running = true;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => { w = cv.clientWidth; h = cv.clientHeight; cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
    resize();
    const N = w < 600 ? 45 : 90;
    const mk = (fresh) => ({ x: Math.random() * w, y: fresh ? h + Math.random() * 40 : Math.random() * h,
      r: .6 + Math.random() * 2.2, vy: .25 + Math.random() * .9, vx: (Math.random() - .5) * .3,
      life: Math.random() * Math.PI * 2, hue: 18 + Math.random() * 22 });
    const ps = Array.from({ length: N }, () => mk(false));
    const tick = () => {
      if (!running) return;
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
      for (const p of ps) {
        p.life += .03; p.y -= p.vy; p.x += p.vx + Math.sin(p.life) * .35;
        if (p.y < -10) Object.assign(p, mk(true));
        const fade = Math.min(1, p.y / h * 1.4);
        const a = (.35 + .45 * Math.abs(Math.sin(p.life * 1.7))) * fade;
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 5);
        g.addColorStop(0, `hsla(${p.hue},100%,70%,${a})`);
        g.addColorStop(1, `hsla(${p.hue},100%,50%,0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 5, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(tick);
    };
    // Ha nem látszik a hős, nem rajzolunk: üres CPU, üres akku.
    const io = new IntersectionObserver(([e]) => {
      const was = running; running = e.isIntersecting;
      if (running && !was) raf = requestAnimationFrame(tick);
    });
    io.observe(cv);
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(tick);
    return () => { running = false; cancelAnimationFrame(raf); io.disconnect(); window.removeEventListener("resize", resize); };
  }, []);
  return <canvas ref={ref} className="fire-embers" aria-hidden="true" />;
};

const Plate = ({ i }) => (
  <svg viewBox="0 0 120 120" className="fire-plate" aria-hidden="true">
    <circle cx="60" cy="60" r="56" fill="#1d1916" stroke="#3a312a" />
    <circle cx="60" cy="60" r="40" fill="none" stroke="#2c2520" />
    {i % 3 === 0 && <><circle cx="50" cy="56" r="13" fill="#7b1e2b" /><circle cx="70" cy="64" r="8" fill="#e9e1cf" /><path d="M42 74q18 8 36-4" stroke="#6f8d3a" strokeWidth="3" fill="none" strokeLinecap="round" /></>}
    {i % 3 === 1 && <><path d="M34 62q26-22 52 0q-26 14-52 0z" fill="#e7a07a" /><path d="M40 62h40" stroke="#f6d7c3" strokeWidth="2" /><circle cx="78" cy="48" r="3" fill="#6f8d3a" /><circle cx="44" cy="74" r="2.5" fill="#6f8d3a" /></>}
    {i % 3 === 2 && <><rect x="36" y="46" width="48" height="26" rx="8" fill="#5a2f1d" /><path d="M38 50l44 18M38 60l40 12" stroke="#2a150c" strokeWidth="2.5" /><circle cx="60" cy="80" r="5" fill="#d9a55b" /></>}
  </svg>
);

/** Kitalált, de stabil foglaltság: ugyanarra a napra mindig ugyanazt mutatja. */
const seatsLeft = (dayKey, slot) => {
  let h = 0;
  for (const c of `${dayKey}|${slot}`) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return [0, 2, 2, 4, 6, 3, 8, 5][h % 8];
};
const SLOTS = ["18:00", "18:30", "19:30", "20:00", "21:00"];

const Booking = ({ d }) => {
  const days = useMemo(() => {
    const out = []; const now = new Date();
    for (let k = 1; out.length < 6 && k < 21; k++) {
      const x = new Date(now.getFullYear(), now.getMonth(), now.getDate() + k);
      if ([3, 4, 5, 6].includes(x.getDay())) out.push(x);
    }
    return out;
  }, []);
  const [di, setDi] = useState(0);
  const [slot, setSlot] = useState("");
  const [n, setN] = useState(2);
  const [done, setDone] = useState(false);
  const fmt = (x, o) => x.toLocaleDateString(d.locale, o);
  const dayKey = days[di].toISOString().slice(0, 10);
  if (done) {
    const dayTxt = fmt(days[di], { weekday: "long", month: "long", day: "numeric" });
    return (
      <div className="fire-done" role="status">
        <Flame size={34} />
        <p className="fire-done-t">{d.confirm.replace("{day}", dayTxt).replace("{time}", slot).replace("{n}", n)}</p>
        <p className="fire-done-n">{d.confirmNote}</p>
        <button type="button" className="fire-btn" onClick={() => { setDone(false); setSlot(""); }}>{d.again}</button>
      </div>
    );
  }
  return (
    <div className="fire-book">
      <div className="fire-book-row">
        <span className="fire-lbl">{d.party}</span>
        <div className="fire-step">
          <button type="button" aria-label="-" onClick={() => setN((x) => Math.max(1, x - 1))}><Minus size={16} /></button>
          <b aria-live="polite">{n}</b>
          <button type="button" aria-label="+" onClick={() => setN((x) => Math.min(8, x + 1))}><Plus size={16} /></button>
        </div>
      </div>
      <span className="fire-lbl">{d.day}</span>
      <div className="fire-days">
        {days.map((x, i) => (
          <button key={i} type="button" className={i === di ? "on" : ""} aria-pressed={i === di} onClick={() => { setDi(i); setSlot(""); }}>
            <small>{fmt(x, { weekday: "short" })}</small><b>{x.getDate()}</b><small>{fmt(x, { month: "short" })}</small>
          </button>
        ))}
      </div>
      <span className="fire-lbl">{d.time}</span>
      <div className="fire-slots">
        {SLOTS.map((s) => {
          const left = seatsLeft(dayKey, s);
          const ok = left >= n;
          return (
            <button key={s} type="button" disabled={!ok} className={slot === s ? "on" : ""} aria-pressed={slot === s} onClick={() => setSlot(s)}>
              <b>{s}</b><small>{left ? d.left.replace("{n}", left) : d.full}</small>
            </button>
          );
        })}
      </div>
      <button type="button" className="fire-btn solid wide" disabled={!slot} onClick={() => setDone(true)}>{d.bookBtn}</button>
    </div>
  );
};

export default function Etterem() {
  const { d, L } = useDemo(C, "/demo/etterem");
  useFonts("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=Inter:wght@300;400;500;600&display=swap");
  const rail = useRef(null);
  const [act, setAct] = useState(0);
  const step = () => (rail.current?.firstElementChild?.getBoundingClientRect().width || 300) + 18;
  const onRail = () => {
    const el = rail.current; if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    // A sor végén az utolsó fogás az aktív, akkor is, ha nem ér a bal szélre.
    const i = el.scrollLeft >= max - 4 ? d.courses.length - 1 : Math.round(el.scrollLeft / step());
    setAct(Math.min(d.courses.length - 1, i));
  };
  const go = (i) => {
    const k = Math.max(0, Math.min(d.courses.length - 1, i));
    rail.current?.scrollTo({ left: k * step(), behavior: "smooth" });
    setAct(k);
  };
  // Egérrel húzható (asztali gépen nincs érintéses lapozás), görgővel is lapoz.
  const drag = useRef(null);
  const onDown = (e) => {
    if (e.pointerType !== "mouse") return;
    drag.current = { x: e.clientX, left: rail.current.scrollLeft, moved: false };
    rail.current.classList.add("drag");
  };
  const onMove = (e) => {
    const g = drag.current; if (!g) return;
    const dx = e.clientX - g.x;
    if (Math.abs(dx) > 3) g.moved = true;
    rail.current.scrollLeft = g.left - dx;
  };
  const onUp = () => {
    const g = drag.current; if (!g) return;
    drag.current = null;
    rail.current.classList.remove("drag");
    go(Math.round(rail.current.scrollLeft / step()));
  };
  useEffect(() => {
    const el = rail.current; if (!el) return;
    const wheel = (e) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      const max = el.scrollWidth - el.clientWidth;
      // A sor szélén elengedjük, hogy az oldal tovább görögjön.
      if ((e.deltaY > 0 && el.scrollLeft >= max - 2) || (e.deltaY < 0 && el.scrollLeft <= 2)) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, []);

  return (
    <div className="fire-page demo-page" data-testid="demo-etterem">
      <DemoBar prefix="fire" />
      <header className="fire-hero">
        <div className="fire-glow" aria-hidden="true" />
        <Embers />
        <div className="fire-hero-in">
          <div className="fire-logo">{d.brand}</div>
          <div className="fire-eyebrow">{d.eyebrow}</div>
          <h1 className="fire-title">{d.title}</h1>
          <p className="fire-sub">{d.sub}</p>
          <div className="fire-cta">
            <a href="#foglalas" className="fire-btn solid">{d.cta}</a>
            <a href="#menu" className="fire-btn">{d.ghost}</a>
          </div>
        </div>
        <div className="fire-scroll" aria-hidden="true"><span /></div>
      </header>

      <section className="fire-sec" id="menu">
        <div className="fire-wrap">
          <Rise>
            <span className="fire-tag">{d.menuTag}</span>
            <h2 className="fire-h2">{d.menuTitle}</h2>
            <p className="fire-lead">{d.menuSub}</p>
          </Rise>
        </div>
        <div className="fire-rail" ref={rail} onScroll={onRail} tabIndex={0} aria-label={d.menuTitle}
          onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}
          onKeyDown={(e) => { if (e.key === "ArrowRight") { e.preventDefault(); go(act + 1); } if (e.key === "ArrowLeft") { e.preventDefault(); go(act - 1); } }}>
          {d.courses.map((c, i) => (
            <article key={c.n} className={`fire-course ${i === act ? "on" : ""}`}>
              <span className="fire-n">{c.n}</span>
              <Plate i={i} />
              <h3>{c.t}</h3>
              <p>{c.d}</p>
            </article>
          ))}
        </div>
        <div className="fire-wrap fire-menu-foot">
          <div className="fire-nav">
            <button type="button" onClick={() => go(act - 1)} disabled={act === 0} aria-label="‹"><ChevronLeft size={20} /></button>
            <div className="fire-dots">{d.courses.map((c, i) => (
              <button key={c.n} type="button" className={i <= act ? "on" : ""} onClick={() => go(i)} aria-label={c.t} />))}</div>
            <button type="button" onClick={() => go(act + 1)} disabled={act === d.courses.length - 1} aria-label="›"><ChevronRight size={20} /></button>
          </div>
          <div><b>{d.price}</b> · {d.pairing}</div>
        </div>
      </section>

      <section className="fire-quote">
        <Rise className="fire-wrap">
          <blockquote>“{d.quote}”</blockquote>
          <cite>— {d.quoteBy}</cite>
        </Rise>
      </section>

      <section className="fire-sec">
        <div className="fire-wrap fire-feats">
          {d.feats.map((f, i) => (
            <Rise key={f.t} delay={i * 110} className="fire-feat">
              <div className="fire-k">{f.k}</div>
              <h3>{f.t}</h3>
              <p>{f.d}</p>
            </Rise>
          ))}
        </div>
      </section>

      <section className="fire-sec fire-booking" id="foglalas">
        <div className="fire-wrap fire-book-grid">
          <Rise>
            <span className="fire-tag">{d.bookTag}</span>
            <h2 className="fire-h2">{d.bookTitle}</h2>
            <p className="fire-lead">{d.bookSub}</p>
            <dl className="fire-dl">
              <div><dt>{L.address}</dt><dd>{d.address}</dd></div>
              <div><dt>{L.phone}</dt><dd>{d.phone}</dd></div>
              <div><dt>{L.hours}</dt><dd>{d.hours}</dd></div>
            </dl>
          </Rise>
          <Booking d={d} />
        </div>
      </section>

      <footer className="fire-footer">© {d.brand} · {d.address} · {d.email}</footer>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";

/* Háttér: egy forgó gömbön ülő agent-hálózat. A csomópontok az agentek, a
 * köztük futó fényimpulzusok az üzenetek; néha borostyán impulzus jön — ez az
 * emberi jóváhagyás, ugyanaz a szín, mint a folyamat-szekcióban. */

const COLORS = ["0,233,255", "200,31,255", "123,92,255"];
const AMBER = "255,182,72";

function glowSprite(rgb) {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, `rgba(${rgb},1)`);
  gr.addColorStop(0.22, `rgba(${rgb},0.55)`);
  gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr;
  g.fillRect(0, 0, 64, 64);
  return c;
}

function buildGraph(n) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const y = 1 - ((i + 0.5) / n) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = i * 2.399963;
    const j = 0.82 + Math.random() * 0.36;
    pts.push({ x: Math.cos(th) * r * j, y: y * j, z: Math.sin(th) * r * j, c: i % 3, flash: 0, adj: [] });
  }
  const seen = new Set();
  const edges = [];
  pts.forEach((a, i) => {
    pts
      .map((b, k) => [k, (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2])
      .filter(([k]) => k !== i)
      .sort((p, q) => p[1] - q[1])
      .slice(0, 3)
      .forEach(([k]) => {
        const key = i < k ? `${i}-${k}` : `${k}-${i}`;
        if (seen.has(key)) return;
        seen.add(key);
        edges.push([i, k]);
        pts[i].adj.push(k);
        pts[k].adj.push(i);
      });
  });
  return { pts, edges };
}

export const PlasmaHero = () => {
  const canvasRef = useRef(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) { setFailed(true); return; }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const mobile = () => window.innerWidth < 900;
    const { pts, edges } = buildGraph(mobile() ? 70 : 110);
    const sprites = [...COLORS.map(glowSprite), glowSprite(AMBER)];
    const proj = pts.map(() => ({ x: 0, y: 0, d: 0, a: 0 }));

    let W = 0, H = 0;
    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas.clientWidth; H = canvas.clientHeight;
      canvas.width = Math.floor(W * dpr); canvas.height = Math.floor(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    let mx = 0, my = 0, tx = 0, ty = 0, px = -9999, py = -9999;
    function onMove(e) {
      tx = (e.clientX / window.innerWidth) * 2 - 1;
      ty = (e.clientY / window.innerHeight) * 2 - 1;
      px = e.clientX; py = e.clientY;
    }
    window.addEventListener("mousemove", onMove);

    let sy = 0;
    const pulses = [];
    let lastSpawn = 0;

    function spawn(from, now, color) {
      const a = pts[from].adj;
      if (!a.length) return;
      const to = a[(Math.random() * a.length) | 0];
      pulses.push({ from, to, t0: now, dur: 900 + Math.random() * 700,
        color: color ?? (Math.random() < 0.05 ? 3 : (Math.random() * 3) | 0) });
    }

    function frame(now) {
      mx += (tx - mx) * 0.05; my += (ty - my) * 0.05;
      const target = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 4);
      sy += (target - sy) * 0.08;

      const m = mobile();
      const t = reduce ? 0 : now / 1000;
      const rotY = t * 0.07 + mx * 0.35 + sy * 0.7;
      const rotX = 0.35 + my * 0.18;
      const cx = m ? W * 0.88 : W * 0.76;
      const cy = (m ? H * 0.14 : H * 0.5) - Math.min(sy, 1.5) * H * 0.12;
      const R = m ? W * 0.5 : Math.min(W * 0.2, H * 0.33);
      const fade = 1 - 0.55 * Math.min(sy, 1);
      const cY = Math.cos(rotY), sY = Math.sin(rotY), cX = Math.cos(rotX), sX = Math.sin(rotX);

      pts.forEach((p, i) => {
        const x1 = p.x * cY + p.z * sY, z1 = -p.x * sY + p.z * cY;
        const y2 = p.y * cX - z1 * sX, z2 = p.y * sX + z1 * cX;
        const persp = 3.6 / (3.6 - z2);
        const o = proj[i];
        o.x = cx + x1 * R * persp; o.y = cy + y2 * R * persp;
        o.d = (z2 + 1.25) / 2.5;
        // A címsor mögött ne világítson: balra halványul.
        const side = m ? 0.15 : Math.min(1, Math.max(0, (o.x - W * 0.5) / (W * 0.14)));
        o.a = fade * (0.35 + 0.65 * side);
        const dm = Math.hypot(o.x - px, o.y - py);
        if (dm < 140) p.flash = Math.max(p.flash, 0.6 * (1 - dm / 140));
      });

      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      ctx.lineWidth = 1;
      for (const [i, k] of edges) {
        const a = proj[i], b = proj[k];
        const al = (0.05 + 0.22 * Math.min(a.d, b.d)) * Math.min(a.a, b.a);
        ctx.strokeStyle = `rgba(123,92,255,${al.toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }

      pts.forEach((p, i) => {
        const o = proj[i];
        const s = (6 + 12 * o.d) * (1 + p.flash * 1.4);
        ctx.globalAlpha = Math.min(1, (0.3 + 0.7 * o.d + p.flash * 0.6) * o.a);
        ctx.drawImage(sprites[p.c], o.x - s, o.y - s, s * 2, s * 2);
        if (p.flash > 0.25) {
          ctx.fillStyle = "rgba(255,255,255,0.9)";
          ctx.fillRect(o.x - 1, o.y - 1, 2, 2);
        }
        p.flash *= 0.94;
      });

      if (!reduce) {
        if (now - lastSpawn > (m ? 260 : 160) && pulses.length < 36) {
          spawn((Math.random() * pts.length) | 0, now);
          lastSpawn = now;
        }
        for (let n = pulses.length - 1; n >= 0; n--) {
          const q = pulses[n];
          const k = (now - q.t0) / q.dur;
          if (k >= 1) {
            pts[q.to].flash = 1;
            pulses.splice(n, 1);
            if (Math.random() < 0.55 && pulses.length < 36) spawn(q.to, now, q.color);
            continue;
          }
          const a = proj[q.from], b = proj[q.to];
          const al = Math.min(a.a, b.a);
          for (let tr = 0; tr < 6; tr++) {
            const kk = Math.max(0, k - tr * 0.035);
            const e = kk * kk * (3 - 2 * kk);
            const x = a.x + (b.x - a.x) * e, y = a.y + (b.y - a.y) * e;
            const s = (tr === 0 ? 9 : 6) * (1 - tr * 0.13);
            ctx.globalAlpha = al * (tr === 0 ? 1 : 0.45 * (1 - tr / 6));
            ctx.drawImage(sprites[q.color], x - s, y - s, s * 2, s * 2);
          }
        }
      }

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      if (!reduce && !document.hidden) raf = requestAnimationFrame(frame);
    }

    let raf = requestAnimationFrame(frame);
    function onVisibility() {
      if (!document.hidden && !reduce) { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
    }
    document.addEventListener("visibilitychange", onVisibility);
    function onScrollStatic() { if (reduce) requestAnimationFrame(frame); }
    window.addEventListener("scroll", onScrollStatic, { passive: true });

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("scroll", onScrollStatic);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div className="plasma-wrap" data-testid="plasma-hero">
      {failed ? <div className="plasma-fallback" /> : <canvas ref={canvasRef} className="plasma-canvas" />}
    </div>
  );
};

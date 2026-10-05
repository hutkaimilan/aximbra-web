import { useEffect, useRef, useState } from "react";

/* Háttér: márkaszínű részecskefelhő, ami szekciónként alakot vált.
 * Fent az AXIMBRA „A” jele, az agenteknél 12 gyűrű, a folyamatnál egy
 * csővezeték, az esettanulmánynál hanghullám, a kapcsolatnál „@”.
 * Kattintásra lökéshullám szórja szét, majd újra összeáll, és a színek
 * továbbfordulnak. Minden mozgás a vertex shaderben számolódik. */

const STAGES = ["top", "agentek", "folyamat", "eset", "kapcsolat"];

const VERT = `
attribute vec2 a_s0; attribute vec2 a_s1; attribute vec2 a_s2; attribute vec2 a_s3; attribute vec2 a_s4;
attribute vec4 a_seed;
uniform float u_stage; uniform vec4 u_c[5];
uniform float u_aspect; uniform float u_time; uniform vec2 u_mouse; uniform vec3 u_click;
uniform float u_hue; uniform float u_dpr; uniform float u_halo;
varying vec3 v_col; varying float v_a;
vec3 pal(float t){
  vec3 m = vec3(0.784,0.121,1.0), v = vec3(0.482,0.361,1.0), c = vec3(0.0,0.913,1.0);
  t = fract(t) * 3.0;
  if (t < 1.0) return mix(m, v, t);
  if (t < 2.0) return mix(v, c, t - 1.0);
  return mix(c, m, t - 2.0);
}
void main(){
  float w0 = max(0.0, 1.0 - abs(u_stage - 0.0));
  float w1 = max(0.0, 1.0 - abs(u_stage - 1.0));
  float w2 = max(0.0, 1.0 - abs(u_stage - 2.0));
  float w3 = max(0.0, 1.0 - abs(u_stage - 3.0));
  float w4 = max(0.0, 1.0 - abs(u_stage - 4.0));
  vec2 P = w0 * (u_c[0].xy + u_c[0].z * a_s0) + w1 * (u_c[1].xy + u_c[1].z * a_s1)
         + w2 * (u_c[2].xy + u_c[2].z * a_s2) + w3 * (u_c[3].xy + u_c[3].z * a_s3)
         + w4 * (u_c[4].xy + u_c[4].z * a_s4);
  float A = w0 * u_c[0].w + w1 * u_c[1].w + w2 * u_c[2].w + w3 * u_c[3].w + w4 * u_c[4].w;
  float tr = 1.0 - max(max(max(w0, w1), max(w2, w3)), w4);

  float t = u_time;
  vec2 rnd = vec2(cos(a_seed.x * 6.2831 + t * 0.4), sin(a_seed.y * 6.2831 + t * 0.4));
  P += 0.008 * vec2(sin(t * 1.3 + a_seed.x * 40.0), cos(t * 1.1 + a_seed.y * 40.0));
  P += tr * 1.1 * rnd * a_seed.z;

  vec2 dm = P - u_mouse;
  P += normalize(dm + 1e-4) * 0.14 * exp(-dot(dm, dm) * 14.0);

  vec2 dc = P - u_click.xy;
  float dist = length(dc);
  float age = u_click.z;
  float wave = exp(-pow((dist - age * 1.9) * 4.5, 2.0)) * exp(-age * 1.1);
  float burst = exp(-age * 2.2) * smoothstep(0.0, 0.08, age);
  P += normalize(dc + 1e-4) * wave * 0.25;
  P += rnd * burst * 0.55 * a_seed.z;

  gl_Position = vec4(P.x / u_aspect, P.y, 0.0, 1.0);
  float glow = 1.0 + wave * 2.0;
  gl_PointSize = (1.4 + 2.4 * a_seed.w) * u_dpr * glow * mix(1.0, 6.5, u_halo);
  v_col = pal(P.x * 0.32 + P.y * 0.22 + 0.1 + u_hue);
  v_a = A * (0.55 + 0.45 * a_seed.z) * glow * mix(1.0, 0.05, u_halo);
}`;

const FRAG = `
precision mediump float;
varying vec3 v_col; varying float v_a;
void main(){
  float d = length(gl_PointCoord - 0.5);
  gl_FragColor = vec4(v_col * smoothstep(0.5, 0.0, d) * v_a, 1.0);
}`;

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.warn(gl.getShaderInfoLog(s)); return null; }
  return s;
}

/* Egy rajzolt alakzat kitöltött pixeleiből N pont, [-1, 1] tartományban. */
function sampleShape(draw, n) {
  const S = 360;
  const c = document.createElement("canvas");
  c.width = c.height = S;
  const g = c.getContext("2d");
  g.fillStyle = "#fff"; g.strokeStyle = "#fff";
  draw(g, S);
  const data = g.getImageData(0, 0, S, S).data;
  const filled = [];
  for (let y = 0; y < S; y += 2) for (let x = 0; x < S; x += 2) if (data[(y * S + x) * 4 + 3] > 128) filled.push(x, y);
  const out = new Float32Array(n * 2);
  const m = filled.length / 2 || 1;
  for (let i = 0; i < n; i++) {
    const k = ((Math.random() * m) | 0) * 2;
    out[i * 2] = ((filled[k] ?? S / 2) + Math.random() * 2) / S * 2 - 1;
    out[i * 2 + 1] = -(((filled[k + 1] ?? S / 2) + Math.random() * 2) / S * 2 - 1);
  }
  return out;
}

const DRAW = {
  top: (g, S) => {
    g.font = `700 ${S * 0.95}px "Chakra Petch", sans-serif`;
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText("A", S / 2, S * 0.54);
  },
  agentek: (g, S) => {
    g.lineWidth = S * 0.028;
    for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) {
      const x = S * (0.14 + c * 0.24), y = S * (0.24 + r * 0.26);
      g.beginPath(); g.arc(x, y, S * 0.075, 0, Math.PI * 2); g.stroke();
      g.beginPath(); g.arc(x, y, S * 0.018, 0, Math.PI * 2); g.fill();
    }
  },
  folyamat: (g, S) => {
    g.lineWidth = S * 0.02;
    g.beginPath();
    for (let x = 0; x <= S; x += 4) {
      const y = S * 0.5 + Math.sin((x / S) * Math.PI * 2) * S * 0.12;
      x === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
    }
    g.stroke();
    for (let i = 0; i < 6; i++) {
      const x = S * (0.08 + i * 0.168), y = S * 0.5 + Math.sin((x / S) * Math.PI * 2) * S * 0.12;
      g.beginPath();
      if (i === 3) { g.moveTo(x, y - S * 0.07); g.lineTo(x + S * 0.07, y); g.lineTo(x, y + S * 0.07); g.lineTo(x - S * 0.07, y); }
      else g.arc(x, y, S * 0.05, 0, Math.PI * 2);
      g.fill();
    }
  },
  eset: (g, S) => {
    const bars = 34;
    for (let i = 0; i < bars; i++) {
      const x = S * 0.06 + (i * S * 0.88) / bars;
      const env = Math.sin((i / (bars - 1)) * Math.PI);
      const h = S * (0.06 + 0.7 * env * (0.45 + 0.55 * Math.abs(Math.sin(i * 1.7))));
      g.fillRect(x, S / 2 - h / 2, S * 0.014, h);
    }
  },
  kapcsolat: (g, S) => {
    g.font = `600 ${S * 0.9}px "Chakra Petch", sans-serif`;
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText("@", S / 2, S * 0.52);
  },
};

export const PlasmaHero = () => {
  const canvasRef = useRef(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { antialias: false, alpha: false, powerPreference: "high-performance" });
    if (!gl) { setFailed(true); return; }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) { setFailed(true); return; }
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { setFailed(true); return; }
    gl.useProgram(prog);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.clearColor(0.0157, 0.0157, 0.047, 1);

    const mobile = () => window.innerWidth < 900;
    const N = mobile() ? 5000 : 9000;
    const U = (n) => gl.getUniformLocation(prog, n);
    const u = {
      stage: U("u_stage"), c: U("u_c"), aspect: U("u_aspect"), time: U("u_time"), mouse: U("u_mouse"),
      click: U("u_click"), hue: U("u_hue"), dpr: U("u_dpr"), halo: U("u_halo"),
    };

    let order = [];
    let ready = false;
    let alive = true;

    function attr(name, data, size) {
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      const l = gl.getAttribLocation(prog, name);
      gl.enableVertexAttribArray(l);
      gl.vertexAttribPointer(l, size, gl.FLOAT, false, 0, 0);
    }

    function sectionTops() {
      return STAGES.map((id) => {
        const el = document.getElementById(id);
        return { id, top: el ? el.getBoundingClientRect().top + window.scrollY : null };
      }).filter((s) => s.top !== null).sort((a, b) => a.top - b.top);
    }

    // A szakaszok helye betöltés közben is változik (képek, betűk), ezért időnként frissítjük.
    function updateTops() {
      order.forEach((s) => {
        const el = Number.isFinite(s.top) ? document.getElementById(s.id) : null;
        if (el) s.top = el.getBoundingClientRect().top + window.scrollY;
      });
    }

    function build() {
      if (!alive) return;
      order = sectionTops();
      while (order.length < 5) order.push({ id: "top", top: Infinity });
      order.slice(0, 5).forEach((s, i) => attr(`a_s${i}`, sampleShape(DRAW[s.id], N), 2));
      const seeds = new Float32Array(N * 4);
      for (let i = 0; i < N * 4; i++) seeds[i] = Math.random();
      attr("a_seed", seeds, 4);
      ready = true;
    }
    const fontsReady = document.fonts?.ready ?? Promise.resolve();
    Promise.race([fontsReady, new Promise((r) => setTimeout(r, 1500))]).then(build);

    let dpr = 1, aspect = 1;
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(canvas.clientWidth * dpr);
      canvas.height = Math.floor(canvas.clientHeight * dpr);
      aspect = canvas.width / Math.max(canvas.height, 1);
      gl.viewport(0, 0, canvas.width, canvas.height);
      updateTops();
    }
    resize();
    window.addEventListener("resize", resize);

    const toWorld = (cx, cy) => [((cx / window.innerWidth) * 2 - 1) * aspect, -((cy / window.innerHeight) * 2 - 1)];
    let mx = 9, my = 9, tmx = 9, tmy = 9;
    function onMove(e) { [tmx, tmy] = toWorld(e.clientX, e.clientY); }
    window.addEventListener("mousemove", onMove);

    let click = [9, 9], clickAt = -100, hue = 0, hueTarget = 0;
    function onClick(e) {
      click = toWorld(e.clientX, e.clientY);
      clickAt = performance.now();
      hueTarget += 1 / 3;
      if (reduce) requestAnimationFrame(frame);
    }
    window.addEventListener("pointerdown", onClick);

    function stageTarget() {
      const y = window.scrollY + window.innerHeight * 0.45;
      const real = order.filter((s) => Number.isFinite(s.top));
      for (let i = real.length - 1; i >= 0; i--) {
        if (y >= real[i].top) {
          const next = real[i + 1];
          if (!next) return i;
          const f = (y - real[i].top) / Math.max(next.top - real[i].top, 1);
          const k = Math.min(1, Math.max(0, (f - 0.55) / 0.45));
          return i + k * k * (3 - 2 * k);
        }
      }
      return 0;
    }

    function centers() {
      const m = mobile();
      const out = new Float32Array(20);
      order.slice(0, 5).forEach((s, i) => {
        let c;
        if (m) c = s.id === "top" ? [aspect * 0.42, 0.52, 0.5, 0.55] : [0, 0.1, aspect * 0.85, 0.4];
        else c = {
          top: [aspect * 0.5, 0.0, 0.92, 1.0],
          agentek: [aspect * 0.66, 0.42, 0.42, 0.9],
          folyamat: [aspect * 0.64, 0.45, 0.45, 0.9],
          eset: [aspect * 0.66, 0.42, 0.42, 0.9],
          kapcsolat: [aspect * 0.55, 0.0, 0.75, 0.75],
        }[s.id];
        out.set(c, i * 4);
      });
      return out;
    }

    let stage = 0, raf, frames = 0;
    const start = performance.now();
    function frame(now) {
      if (ready) {
        if (++frames % 60 === 0) updateTops();
        mx += (tmx - mx) * 0.08; my += (tmy - my) * 0.08;
        stage += (stageTarget() - stage) * 0.06;
        hue += (hueTarget - hue) * 0.04;
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.uniform1f(u.stage, reduce ? Math.round(stageTarget()) : stage);
        gl.uniform4fv(u.c, centers());
        gl.uniform1f(u.aspect, aspect);
        gl.uniform1f(u.time, reduce ? 0 : (now - start) / 1000);
        gl.uniform2f(u.mouse, mx, my);
        gl.uniform3f(u.click, click[0], click[1], reduce ? 9 : (now - clickAt) / 1000);
        gl.uniform1f(u.hue, hue);
        gl.uniform1f(u.dpr, dpr);
        gl.uniform1f(u.halo, 1);
        gl.drawArrays(gl.POINTS, 0, Math.floor(N / 3));
        gl.uniform1f(u.halo, 0);
        gl.drawArrays(gl.POINTS, 0, N);
      }
      if (!reduce && !document.hidden) raf = requestAnimationFrame(frame);
      else if (!ready) setTimeout(() => requestAnimationFrame(frame), 200);
    }
    raf = requestAnimationFrame(frame);

    function onVisibility() {
      if (!document.hidden && !reduce) { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
    }
    document.addEventListener("visibilitychange", onVisibility);
    function onScrollStatic() { if (reduce) requestAnimationFrame(frame); }
    window.addEventListener("scroll", onScrollStatic, { passive: true });

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("pointerdown", onClick);
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

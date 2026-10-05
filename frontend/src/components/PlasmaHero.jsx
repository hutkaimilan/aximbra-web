import { useEffect, useRef, useState } from "react";

/* Háttér: részecske-örvény. Több ezer fénypont kering egy döntött korongban
 * egy sötét mag körül; a belső pályák gyorsabbak (Kepler). Minden pozíció a
 * vertex shaderben számolódik az időből, így nincs CPU-oldali szimuláció. */

const VERT = `
attribute vec4 a_seed;
uniform float u_time; uniform vec2 u_res; uniform vec2 u_mouse; uniform float u_scroll;
uniform float u_dpr; uniform vec2 u_center; uniform float u_scale; uniform float u_mobile; uniform float u_halo;
varying vec3 v_col; varying float v_a;
void main(){
  float r = a_seed.x, a0 = a_seed.y, h = a_seed.z, k = a_seed.w;
  float R = mix(0.42, 1.75, pow(r, 1.35));
  float w = 0.32 / pow(R, 1.5);
  float ang = a0 + u_time * w;
  R += 0.045 * sin(ang * 3.0 + u_time * 0.6 + k * 6.2831);
  float y = h * 0.035 * R + 0.02 * sin(ang * 5.0 + u_time * 0.8 + k * 12.0);
  vec3 p = vec3(cos(ang) * R, y, sin(ang) * R);

  float tilt = 0.28 + u_mouse.y * 0.1 + min(u_scroll, 1.5) * 0.35;
  float roll = 0.18 + u_mouse.x * 0.06;
  p = vec3(p.x, p.y * cos(tilt) - p.z * sin(tilt), p.y * sin(tilt) + p.z * cos(tilt));
  p = vec3(p.x * cos(roll) - p.y * sin(roll), p.x * sin(roll) + p.y * cos(roll), p.z);

  float persp = 3.4 / (3.4 - p.z);
  vec2 s = p.xy * persp * u_scale;
  s.x *= u_res.y / u_res.x;
  vec2 ndc = u_center + s;
  ndc.y += min(u_scroll, 1.5) * 0.25;
  gl_Position = vec4(ndc, 0.0, 1.0);

  gl_PointSize = (1.6 + 3.2 * k * k) * persp * u_dpr * mix(1.0, 7.0, u_halo);

  float t = smoothstep(0.42, 1.75, R);
  vec3 inner = vec3(0.85, 0.97, 1.0), cyan = vec3(0.0, 0.913, 1.0);
  vec3 violet = vec3(0.482, 0.361, 1.0), magenta = vec3(0.784, 0.121, 1.0);
  vec3 c = mix(inner, cyan, smoothstep(0.0, 0.12, t));
  c = mix(c, violet, smoothstep(0.12, 0.5, t));
  c = mix(c, magenta, smoothstep(0.5, 0.95, t));
  v_col = c;

  float bright = mix(1.0, 0.35, t) * (0.55 + 0.45 * persp);
  float keepOffText = mix(smoothstep(-0.15, 0.3, ndc.x), 0.35, u_mobile);
  float fade = 1.0 - 0.6 * clamp(u_scroll, 0.0, 1.0);
  v_a = 0.95 * bright * keepOffText * fade * mix(1.0, 0.045, u_halo);
}`;

const FRAG = `
precision mediump float;
varying vec3 v_col; varying float v_a;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d);
  gl_FragColor = vec4(v_col * a * v_a, 1.0);
}`;

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.warn(gl.getShaderInfoLog(s)); return null; }
  return s;
}

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

    const mobile = () => window.innerWidth < 900;
    const N = mobile() ? 7000 : 14000;
    const seeds = new Float32Array(N * 4);
    for (let i = 0; i < N; i++) {
      seeds[i * 4] = Math.random();
      seeds[i * 4 + 1] = Math.random() * Math.PI * 2;
      seeds[i * 4 + 2] = (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;
      seeds[i * 4 + 3] = Math.random();
    }
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, seeds, gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a_seed");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 4, gl.FLOAT, false, 0, 0);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.clearColor(0.0157, 0.0157, 0.047, 1);

    const U = (n) => gl.getUniformLocation(prog, n);
    const uTime = U("u_time"), uRes = U("u_res"), uMouse = U("u_mouse"), uScroll = U("u_scroll");
    const uDpr = U("u_dpr"), uCenter = U("u_center"), uScale = U("u_scale"), uMobile = U("u_mobile"), uHalo = U("u_halo");

    let dpr = 1;
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(canvas.clientWidth * dpr);
      canvas.height = Math.floor(canvas.clientHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    resize();
    window.addEventListener("resize", resize);

    let mx = 0, my = 0, tx = 0, ty = 0;
    function onMove(e) {
      tx = (e.clientX / window.innerWidth) * 2 - 1;
      ty = -((e.clientY / window.innerHeight) * 2 - 1);
    }
    window.addEventListener("mousemove", onMove);

    let sy = 0, raf;
    const start = performance.now();
    function frame(now) {
      mx += (tx - mx) * 0.04; my += (ty - my) * 0.04;
      const target = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 4);
      sy += (target - sy) * 0.08;
      const m = mobile();
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(uTime, reduce ? 30 : (now - start) / 1000 + 30);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform2f(uMouse, mx, my);
      gl.uniform1f(uScroll, sy);
      gl.uniform1f(uDpr, dpr);
      gl.uniform2f(uCenter, m ? 0.35 : 0.42, m ? 0.6 : 0.05);
      gl.uniform1f(uScale, m ? 0.7 : 0.62);
      gl.uniform1f(uMobile, m ? 1 : 0);
      // Előbb halvány, nagy pontok (fényudvar), rá az éles részecskék.
      gl.uniform1f(uHalo, 1);
      gl.drawArrays(gl.POINTS, 0, Math.floor(N / 3));
      gl.uniform1f(uHalo, 0);
      gl.drawArrays(gl.POINTS, 0, N);
      if (!reduce && !document.hidden) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

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

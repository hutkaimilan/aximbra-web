import { useEffect, useRef, useState } from "react";

const VERT = `attribute vec2 a_pos; void main(){ gl_Position = vec4(a_pos,0.0,1.0); }`;

const FRAG = `precision highp float;
uniform vec2 u_res; uniform float u_time; uniform vec2 u_mouse; uniform float u_scroll;
float hash(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y); }
float noise(vec2 p){ vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),u.x), mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),u.x), u.y); }
const mat2 R=mat2(0.8,0.6,-0.6,0.8);
float fbm(vec2 p){ float v=0.0, a=0.5; for(int i=0;i<5;i++){ v+=a*noise(p); p=R*p*2.03; a*=0.5; } return v; }
void main(){
  vec2 p=(gl_FragCoord.xy-0.5*u_res.xy)/u_res.y;
  p*=mix(2.2,1.0,clamp(u_res.x/u_res.y,0.0,1.0));
  p.y+=u_scroll*0.18;
  float t=u_time*0.045;
  vec2 m=u_mouse*0.22;
  vec2 q=vec2(fbm(p*1.1+vec2(0.0,t)), fbm(p*1.1+vec2(5.2,1.3)-t));
  vec2 r=vec2(fbm(p*1.3+3.2*q+vec2(1.7,9.2)+1.3*t+m), fbm(p*1.3+3.2*q+vec2(8.3,2.8)-1.1*t-m));
  float f=fbm(p*1.5+3.6*r);
  vec3 bg=vec3(0.0157,0.0157,0.047);
  vec3 magenta=vec3(0.784,0.121,1.0), violet=vec3(0.482,0.361,1.0), cyan=vec3(0.0,0.913,1.0);
  vec3 col=mix(violet*0.35, magenta*0.75, smoothstep(0.25,0.85,q.x));
  col=mix(col, cyan*0.8, smoothstep(0.4,0.95,r.y)*0.85);
  float body=smoothstep(0.12,0.85,f*f*2.3);
  col*=body;
  float fold=1.0-abs(2.0*fract(f*3.2+r.x*0.6-u_time*0.02)-1.0);
  fold=pow(fold,14.0)*smoothstep(0.35,0.8,f);
  col+=mix(cyan,vec3(0.85,0.9,1.0),0.35)*fold*0.85;
  vec2 mp=u_mouse*vec2(u_res.x/u_res.y,1.0)*0.5;
  col+=violet*exp(-length(p-mp)*3.0)*0.12*body;
  col*=1.05;
  float d=length(p*vec2(0.85,1.0));
  col=mix(col,bg,smoothstep(0.75,2.0,d));
  col=max(col,bg);
  col+=(hash(gl_FragCoord.xy+fract(u_time))-0.5)/255.0*3.0;
  gl_FragColor=vec4(col,1.0);
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
    const gl = canvas.getContext("webgl", { antialias: false, powerPreference: "high-performance" });
    if (!gl) { setFailed(true); return; }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) { setFailed(true); return; }
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { setFailed(true); return; }
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(prog, "u_res");
    const uTime = gl.getUniformLocation(prog, "u_time");
    const uMouse = gl.getUniformLocation(prog, "u_mouse");
    const uScroll = gl.getUniformLocation(prog, "u_scroll");

    // Lágy, elmosódott kép: csökkentett felbontáson is ugyanúgy néz ki, a CSS
    // felskálázza. Ez a GPU-terhelés töredéke a teljes retina-felbontásnak.
    const scale = window.innerWidth < 900 ? 0.45 : 0.6;
    function resize() {
      canvas.width = Math.max(1, Math.floor(canvas.clientWidth * scale));
      canvas.height = Math.max(1, Math.floor(canvas.clientHeight * scale));
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    resize();
    window.addEventListener("resize", resize);

    let mx = 0, my = 0, tx = 0, ty = 0;
    function onMove(e) { tx = (e.clientX / window.innerWidth) * 2 - 1; ty = -((e.clientY / window.innerHeight) * 2 - 1); }
    window.addEventListener("mousemove", onMove);

    let sy = 0;
    const scrollTarget = () => Math.min(window.scrollY / Math.max(window.innerHeight, 1), 12);

    let raf, start = performance.now();
    function frame(now) {
      mx += (tx - mx) * 0.05; my += (ty - my) * 0.05;
      sy += (scrollTarget() - sy) * 0.08;
      const t = reduce ? 20 : (now - start) / 1000 + 20;
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, t);
      gl.uniform2f(uMouse, mx, my);
      gl.uniform1f(uScroll, sy);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!reduce && !document.hidden) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    function onVisibility() {
      if (!document.hidden && !reduce) { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div className="plasma-wrap" data-testid="plasma-hero">
      {failed ? <div className="plasma-fallback" /> : <canvas ref={canvasRef} className="plasma-canvas" />}
    </div>
  );
};

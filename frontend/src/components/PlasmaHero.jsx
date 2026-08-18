import { useEffect, useRef, useState } from "react";

const VERT = `attribute vec2 a_pos; void main(){ gl_Position = vec4(a_pos,0.0,1.0); }`;

const FRAG = `precision highp float;
uniform vec2 u_res; uniform float u_time; uniform vec2 u_mouse;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float noise(vec2 p){ vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),u.x), mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),u.x), u.y); }
float fbm(vec2 p){ float v=0.0, a=0.5; for(int i=0;i<6;i++){ v+=a*noise(p); p*=2.0; a*=0.5; } return v; }
void main(){
  vec2 p=(gl_FragCoord.xy-0.5*u_res.xy)/u_res.y;
  float t=u_time*0.06; vec2 m=u_mouse*0.35;
  float f=fbm(p*1.7+m+vec2(t,-t));
  float f2=fbm(p*3.0-m+vec2(-t*0.7,t*0.5)+f);
  float veins=pow(abs(sin((p.x+p.y)*3.0+f2*6.0+u_time*0.25)),22.0);
  vec3 magenta=vec3(0.784,0.121,1.0), violet=vec3(0.482,0.361,1.0), cyan=vec3(0.0,0.913,1.0);
  vec3 col=mix(magenta,violet,smoothstep(0.15,0.8,f));
  col=mix(col,cyan,smoothstep(0.3,0.95,f2));
  col+=cyan*veins*0.9;
  col*=0.42;
  float d=length(p);
  col=mix(col, vec3(0.0157,0.0157,0.047), smoothstep(0.35,1.35,d));
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

    const isMobile = window.innerWidth < 900;
    const dprCap = isMobile ? 1.6 : 2;
    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, dprCap);
      canvas.width = Math.floor(canvas.clientWidth * dpr);
      canvas.height = Math.floor(canvas.clientHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    resize();
    window.addEventListener("resize", resize);

    let mx = 0, my = 0, tx = 0, ty = 0;
    function onMove(e) { tx = (e.clientX / window.innerWidth) * 2 - 1; ty = -((e.clientY / window.innerHeight) * 2 - 1); }
    window.addEventListener("mousemove", onMove);

    let raf, start = performance.now();
    function frame(now) {
      mx += (tx - mx) * 0.06; my += (ty - my) * 0.06;
      const t = reduce ? 0 : (now - start) / 1000;
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, t);
      gl.uniform2f(uMouse, mx, my);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!reduce) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); window.removeEventListener("mousemove", onMove); };
  }, []);

  return (
    <div className="plasma-wrap" data-testid="plasma-hero">
      {failed ? <div className="plasma-fallback" /> : <canvas ref={canvasRef} className="plasma-canvas" />}
    </div>
  );
};

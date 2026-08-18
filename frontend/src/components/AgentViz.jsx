import { useEffect, useRef, useState } from "react";
import "./agentviz.css";

const R = (a) => ({ animation: a });
const growLeft = (a) => ({ animation: a, transformOrigin: "left center", transformBox: "fill-box" });

const SCENES = [
  // 0 — E-mail rendező: envelopes split into colour-coded category columns
  (
    <svg viewBox="0 0 200 88" key="0">
      <rect className="fill-m" x="150" y="18" width="12" height="52" rx="3" style={R("vRecv 3.2s ease-in-out infinite")} />
      <rect className="fill-c" x="168" y="30" width="12" height="40" rx="3" style={R("vRecv 3.2s ease-in-out .5s infinite")} />
      <rect className="fill-a" x="186" y="40" width="8" height="30" rx="3" style={R("vRecv 3.2s ease-in-out 1s infinite")} />
      <g className="stroke vz-c" style={R("vSlideR 3.2s ease-in-out infinite")}>
        <rect className="env-r" x="14" y="24" width="30" height="20" rx="3" fill="rgba(0,233,255,.08)" />
        <path d="M14 26 L29 38 L44 26" />
      </g>
      <g className="stroke vz-m" style={R("vSlideR 3.2s ease-in-out .9s infinite")}>
        <rect x="14" y="46" width="30" height="20" rx="3" fill="rgba(200,31,255,.08)" />
        <path d="M14 48 L29 60 L44 48" />
      </g>
    </svg>
  ),
  // 1 — Érdeklődő-minősítő: dots sort into A/B/C/D bands
  (
    <svg viewBox="0 0 200 88" key="1">
      {["A", "B", "C", "D"].map((l, i) => (
        <g key={l}>
          <rect className="track" x="56" y={12 + i * 18} width="132" height="12" rx="6" />
          <text x="42" y={22 + i * 18}>{l}</text>
        </g>
      ))}
      {[[110, 18, "fill-m", 0], [150, 36, "fill-c", .5], [96, 54, "fill-v", 1], [140, 72, "fill-a", 1.5], [170, 18, "fill-m", 2]].map((d, i) => (
        <circle key={i} className={d[2]} cx={d[0]} cy={d[1]} r="4.5" style={R(`vSettle 3.4s ease-in-out ${d[3]}s infinite`)} />
      ))}
    </svg>
  ),
  // 2 — Belső admin: data flows between two boxes
  (
    <svg viewBox="0 0 200 88" key="2">
      <rect className="box stroke vz-v" x="12" y="30" width="34" height="28" rx="4" />
      <rect className="box stroke vz-v" x="154" y="30" width="34" height="28" rx="4" />
      <line className="stroke vz-c" x1="46" y1="44" x2="154" y2="44" opacity=".3" />
      <rect className="fill-c" x="50" y="40" width="9" height="9" rx="2" style={R("vSlideR 2.6s ease-in-out infinite")} />
      <rect className="fill-m" x="50" y="40" width="9" height="9" rx="2" style={R("vSlideR 2.6s ease-in-out 1.3s infinite")} />
    </svg>
  ),
  // 3 — Kutatási monitor: radar sweep, a blip flashes
  (
    <svg viewBox="0 0 200 88" key="3">
      <circle className="stroke vz-c" cx="100" cy="44" r="32" opacity=".3" />
      <circle className="stroke vz-c" cx="100" cy="44" r="18" opacity=".3" />
      <line className="stroke vz-m" x1="100" y1="44" x2="132" y2="44" style={{ transformBox: "view-box", transformOrigin: "100px 44px", animation: "vSpin 3s linear infinite" }} />
      <circle className="fill-a" cx="120" cy="30" r="3.5" style={R("vBlip 3s ease-in-out infinite")} />
    </svg>
  ),
  // 4 — Ügyfélszolgálat: question → document → answer + source line
  (
    <svg viewBox="0 0 200 88" key="4">
      <circle className="stroke vz-m" cx="26" cy="40" r="12" /><text x="22" y="44">?</text>
      <rect className="page stroke vz-c" x="82" y="22" width="36" height="36" rx="3" />
      <line className="stroke vz-c" x1="88" y1="32" x2="112" y2="32" opacity=".6" />
      <line className="stroke vz-c" x1="88" y1="40" x2="112" y2="40" opacity=".6" />
      <line className="stroke vz-a" x1="88" y1="52" x2="108" y2="52" style={{ strokeDasharray: 24, strokeDashoffset: 24, animation: "vDash 2.6s ease-in-out infinite" }} />
      <circle className="stroke vz-c" cx="174" cy="40" r="12" /><path className="stroke vz-c" d="M169 40 l4 4 l7 -8" />
      <line className="stroke vz-v" x1="38" y1="40" x2="82" y2="40" opacity=".25" />
      <line className="stroke vz-v" x1="118" y1="40" x2="162" y2="40" opacity=".25" />
      <circle className="fill-c" r="3" style={{ offsetPath: "path('M40 40 L160 40')", animation: "vTravel 2.6s ease-in-out infinite" }} />
    </svg>
  ),
  // 5 — Tartalom-agent: text lines build up
  (
    <svg viewBox="0 0 200 88" key="5">
      {[[150, 0], [176, .3], [120, .6], [160, .9], [90, 1.2]].map((r, i) => (
        <rect key={i} className="fill-c" x="24" y={16 + i * 12} width={r[0]} height="5" rx="2.5" opacity=".85"
          style={growLeft(`vGrowX 2.8s ease-in-out ${r[1]}s infinite`)} />
      ))}
    </svg>
  ),
  // 6 — Webshop: product grid, one highlighted
  (
    <svg viewBox="0 0 200 88" key="6">
      {Array.from({ length: 8 }).map((_, i) => {
        const x = 30 + (i % 4) * 38, y = 20 + Math.floor(i / 4) * 30;
        const hi = i === 5;
        return <rect key={i} className={hi ? "fill-m" : "stroke vz-c"} x={x} y={y} width="30" height="22" rx="4"
          fill={hi ? "#C81FFF" : "rgba(0,233,255,.06)"} style={hi ? R("vPulse 1.8s ease-in-out infinite") : null} opacity={hi ? 1 : .6} />;
      })}
    </svg>
  ),
  // 7 — Dokumentum-elemző: page, fields rise out
  (
    <svg viewBox="0 0 200 88" key="7">
      <rect className="page stroke vz-c" x="70" y="18" width="60" height="54" rx="4" />
      <line className="stroke vz-c" x1="78" y1="30" x2="122" y2="30" opacity=".4" />
      <line className="stroke vz-c" x1="78" y1="40" x2="122" y2="40" opacity=".4" />
      {[[40, 0], [100, .8], [150, 1.6]].map((f, i) => (
        <rect key={i} className="fill-a" x={f[0]} y="30" width="26" height="9" rx="3"
          style={R(`vRise 3s ease-in-out ${f[1]}s infinite`)} />
      ))}
    </svg>
  ),
  // 8 — Pénzügyi: bar chart, one deviation red
  (
    <svg viewBox="0 0 200 88" key="8">
      <line className="stroke vz-c" x1="24" y1="70" x2="180" y2="70" opacity=".3" />
      {[[36, 30], [66, 44], [96, 22], [126, 52], [156, 36]].map((b, i) => {
        const red = i === 3;
        return <rect key={i} className={red ? "fill-red" : "fill-c"} x={b[0]} y={70 - b[1]} width="20" height={b[1]} rx="2"
          opacity={red ? 1 : .7} style={red ? R("vGlow 1.4s ease-in-out infinite") : null} />;
      })}
      <circle className="fill-red" cx="136" cy={70 - 52 - 6} r="3.5" style={R("vGlow 1.4s ease-in-out infinite")} />
    </svg>
  ),
  // 9 — Toborzás: CVs through a filter, fewer come out
  (
    <svg viewBox="0 0 200 88" key="9">
      <path className="funnel stroke vz-m" d="M70 22 L130 22 L110 46 L90 46 Z" />
      {[[86, 0], [100, .5], [114, 1], [96, 1.5]].map((d, i) => (
        <circle key={i} className="fill-c" cx={d[0]} cy="14" r="4" style={R(`vDrop 3s ease-in-out ${d[1]}s infinite`)} />
      ))}
      <line className="stroke vz-v" x1="100" y1="46" x2="100" y2="60" opacity=".4" />
      {[[92, .4], [108, 1.4]].map((d, i) => (
        <circle key={i} className="fill-a" cx={d[0]} cy="62" r="4" style={R(`vDrop 3s ease-in-out ${d[1]}s infinite`)} />
      ))}
    </svg>
  ),
  // 10 — IT/DevOps: log wave, a spike → fix
  (
    <svg viewBox="0 0 200 88" key="10">
      <polyline className="stroke vz-c" points="12,52 44,52 58,52 70,24 82,66 94,44 130,44 150,44 188,44"
        style={{ strokeDasharray: 240, strokeDashoffset: 240, animation: "vDash 3s ease-in-out infinite" }} />
      <circle className="fill-a" cx="76" cy="24" r="3.5" style={R("vGlow 1.6s ease-in-out infinite")} />
      <g style={R("vFixIn 3s ease-in-out infinite")} transform="translate(150 44)">
        <circle className="stroke vz-m" cx="0" cy="0" r="11" />
        <path className="stroke vz-m" d="M-5 0 l4 4 l7 -8" />
      </g>
    </svg>
  ),
  // 11 — Multi-agent: nodes with handoffs
  (
    <svg viewBox="0 0 200 88" key="11">
      {[[34, 26], [34, 62], [166, 26], [166, 62], [100, 44]].map((n, i) => (
        <circle key={i} className="node-f stroke vz-c" cx={n[0]} cy={n[1]} r="9" />
      ))}
      {["M34 26 L100 44", "M34 62 L100 44", "M100 44 L166 26", "M100 44 L166 62"].map((p, i) => (
        <path key={i} className="stroke vz-v" d={p} opacity=".3" />
      ))}
      <circle className="fill-m" r="3" style={{ offsetPath: "path('M34 26 L100 44 L166 62')", animation: "vTravel 2.8s ease-in-out infinite" }} />
      <circle className="fill-c" r="3" style={{ offsetPath: "path('M34 62 L100 44 L166 26')", animation: "vTravel 2.8s ease-in-out 1.2s infinite" }} />
    </svg>
  ),
];

export const AgentViz = ({ kind }) => {
  const ref = useRef(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className={`agent-viz ${on ? "viz-on" : ""}`} data-testid={`agent-viz-${kind}`} aria-hidden="true">
      {SCENES[kind] || SCENES[0]}
    </div>
  );
};

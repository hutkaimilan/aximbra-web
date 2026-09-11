#!/usr/bin/env python3
import random, pathlib
W, H = 2000, 1250
rnd = random.Random(20260911)

bokeh = []
for i in range(52):
    x = rnd.uniform(0.20, 1.03)
    y = rnd.uniform(-0.05, 0.78)
    r = rnd.uniform(20, 110) * (1.2 if y < 0.32 else 0.8)
    a = rnd.uniform(0.22, 0.62) * (1.0 if y < 0.5 else 0.7)
    hue = rnd.choice(["255,206,140", "250,182,104", "228,150,78", "255,232,190"])
    blur = r * rnd.uniform(0.3, 0.7)
    bokeh.append(
        f'<div class="b" style="left:{x*100:.2f}%;top:{y*100:.2f}%;width:{r:.0f}px;height:{r:.0f}px;'
        f'background:rgba({hue},{a:.2f});filter:blur({blur:.0f}px)"></div>'
    )

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{{margin:0;height:100%;overflow:hidden;background:#141010}}
  .stage{{position:fixed;inset:0;overflow:hidden;transform:scaleX(-1)}}
  .l{{position:absolute;inset:0}}
  .b{{position:absolute;border-radius:50%;transform:translate(-50%,-50%)}}
  .grain{{position:absolute;inset:0;opacity:.10;mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3'/></filter><rect width='200' height='200' filter='url(%23n)'/></svg>")}}
</style></head><body><div class="stage">
  <!-- alap -->
  <div class="l" style="background:radial-gradient(130% 100% at 45% 118%, #4a2a14 0%, #2a1a11 40%, #16100d 78%, #120d0b 100%)"></div>
  <!-- parazs: a kep fo fenyforrasa, bal also harmad -->
  <div class="l" style="background:radial-gradient(62% 56% at 22% 94%, rgba(255,158,54,.95) 0%, rgba(226,118,40,.55) 30%, rgba(150,72,26,.22) 55%, transparent 74%)"></div>
  <!-- pult-vonal: egy vizszintes meleg fenycsik ad szerkezetet -->
  <div class="l" style="background:linear-gradient(180deg, transparent 62%, rgba(255,176,92,.16) 70%, rgba(255,176,92,.05) 74%, transparent 80%);filter:blur(26px)"></div>
  <!-- masodik feny jobb fent -->
  <div class="l" style="background:radial-gradient(46% 42% at 88% 14%, rgba(255,206,150,.34) 0%, rgba(200,132,66,.14) 42%, transparent 70%)"></div>
  {''.join(bokeh)}
  <div class="l" style="background:linear-gradient(104deg, transparent 32%, rgba(255,214,164,.10) 50%, transparent 66%)"></div>
  <!-- vignetta -->
  <div class="l" style="background:radial-gradient(125% 118% at 46% 46%, transparent 40%, rgba(12,9,8,.42) 78%, rgba(10,7,6,.72) 100%)"></div>
  <div class="l" style="background:linear-gradient(180deg, rgba(14,10,9,.42) 0%, transparent 22%, transparent 68%, rgba(12,8,7,.34) 100%)"></div>
  <div class="grain"></div>
</div></body></html>"""
pathlib.Path("hero.html").write_text(html, encoding="utf-8")

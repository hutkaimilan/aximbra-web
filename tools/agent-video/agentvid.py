"""AXIMBRA agentvideó — egy agent, egy videó, a jóváhagyott e-mail-reklám stílusában.

Használat:  python3 agentvid.py <agent-szám> <axi-klip.mp4> [kimenet.mp4] [--preview]

Felépítés:
  horog     Axi (Veo-klip) a saját hangjával, a telefonján az agent kártyája
  átvezetés ráközelítés a telefonra
  bemutató  a valódi aximbra.hu képernyő, ütemenként: narráció + felirat +
            kiemelő keret + koppintás; az időzítést a felolvasás hossza adja
  zárókép   AXIMBRA, aximbra.hu, felhívás, lábjegyzet

A képernyőtartalom éles, teljes kártyás képekből jön (sims.json / live.json),
a mozgás kamera. Kimenet: 1080x1920, 30 fps.
"""
from __future__ import annotations
import json, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
from cfg import AGENTS            # noqa: E402
from tts_all import make as tts_make, dur as tts_dur   # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PREVIEW = "--preview" in sys.argv
if len(args) < 2:
    sys.exit("hasznalat: agentvid.py <agent> <klip.mp4> [kimenet.mp4] [--preview]")
K = int(args[0])
AXI = os.path.abspath(args[1])
A = AGENTS[K]
OUT = args[2] if len(args) > 2 else f"agent{K:02d}.mp4"
if not os.path.exists(AXI):
    sys.exit(f"nincs ilyen klip: {AXI}")

W, H, FPS = 1080, 1920, 30
SR = 48000
CYAN = (0, 233, 255)
F_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
F_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
fnt = ImageFont.truetype
ease_out = lambda k: 1 - (1 - k) ** 3
ease_in = lambda k: k * k * k
smooth = lambda k: k * k * (3 - 2 * k)

# ─────────────────────────── adatok ───────────────────────────
DATA = json.load(open("sims.json" if A["src"] == "sims" else "live.json"))[A["key"]]
RECTS = dict(DATA["states"])
STATES = {}
if A["kind"] == "sim":
    STATES = {"I": f"s{K}_I.png", "D": f"s{K}_D.png"}
    for i in DATA["runFrames"]:
        STATES[f"R{i}"] = f"s{K}_R{i}.png"
        RECTS.setdefault(f"R{i}", DATA["states"]["R"])
    for e in A.get("extra", ()):
        STATES[e] = f"s{K}_{e}.png"
else:
    STATES = dict(A["states"])
RUN_FRAMES = sorted(DATA.get("runFrames", []))

def ref(spec):
    """'ÁLLAPOT.elem[i:j]' → keret képpontban (a CSS-érték kétszerese), vagy None."""
    if spec is None:
        return None
    if isinstance(spec, (list, tuple)):
        rs = [ref(s) for s in spec]
        rs = [r for r in rs if r]
        if not rs:
            return None
        return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))
    m = re.fullmatch(r"(\w+)\.(\w+)(?:\[(\d*)(?::(\d*))?\])?", spec)
    if not m:
        raise ValueError(f"rossz hivatkozas: {spec}")
    st, name, i, j = m.group(1), m.group(2), m.group(3), m.group(4)
    v = RECTS.get(st, {}).get(name)
    if v is None:
        raise KeyError(f"nincs ilyen elem: {spec}")
    items = v if isinstance(v[0], list) else [v]
    if i is not None and i != "":
        if j is None:
            items = [items[int(i)]]
        else:
            items = items[int(i): int(j) if j else None]
    elif j is not None:
        items = items[: int(j) if j else None]
    x0 = min(r[0] for r in items); y0 = min(r[1] for r in items)
    x1 = max(r[2] for r in items); y1 = max(r[3] for r in items)
    return (x0 * 2, y0 * 2, x1 * 2, y1 * 2)

# Az állapotképek egyforma magasra töltve: így két állapot közti áttűnésnél a
# kivágás ugyanott van, és a kártya nem ugrik.
_raw = {k: Image.open(f).convert("RGB") for k, f in STATES.items()}
PH = max(max(im.height for im in _raw.values()), 2340 + 420)
CONTENT_H = {k: im.height for k, im in _raw.items()}
PAGES = {}
for k, im in _raw.items():
    if im.height < PH:
        bg = im.getpixel((6, im.height - 6))
        c = Image.new("RGB", (im.width, PH), bg)
        c.paste(im, (0, 0))
        im = c
    PAGES[k] = im
PW = W
LIGHT = sum(PAGES[A["first"]].getpixel((6, PH - 6))) > 450      # világos lap (webshop)
# A kártya belső tartalma (CSS 57..483 px) kitölti a képet, egy betű sem esik ki.
# A webshop bekezdése a teljes lapszélességet használja: ott nincs nagyítás.
Z = 1.02 if K == 6 else 1.20

# ─────────────────────────── a klip: beszéd, időzítés ───────────────────────────
def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768

CLIP_AUDIO = load(AXI)
CLIP_DUR = len(CLIP_AUDIO) / SR

def speech_span(a):
    hop = int(0.02 * SR)
    e = np.array([np.sqrt((a[i:i + hop] ** 2).mean() + 1e-12) for i in range(0, len(a) - hop, hop)])
    thr = max(np.percentile(e, 20) * 3.0, e.max() * 0.10)
    on = np.nonzero(e > thr)[0]
    if not len(on):
        return 0.5, min(4.5, CLIP_DUR - 1)
    return on[0] * 0.02, (on[-1] + 1) * 0.02

def whisper_words():
    """Szóidőzítés a klip hangjából; hiba esetén üres lista."""
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel("small", device="cpu", compute_type="int8")
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", AXI, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                             capture_output=True, check=True).stdout
        segs, _ = m.transcribe(np.frombuffer(raw, np.float32).copy(), language="hu",
                               word_timestamps=True, vad_filter=False)
        out = []
        for s in segs:
            for w_ in (s.words or []):
                out.append((w_.start, w_.end, w_.word.strip()))
        return out
    except Exception as e:   # noqa - a feliratozás arányos becsléssel is működik
        print("whisper nem futott:", type(e).__name__, e)
        return []

S0, S1 = speech_span(CLIP_AUDIO)
WW = whisper_words()
if WW:
    print("klip szovege:", " ".join(w for _, _, w in WW))
    # A beszéd határa a felismert első és utolsó szó: a hangerő szerinti becslés
    # a klip háttérzenéjét is beszédnek venné, és Axi szótlanul ülne a végén.
    S0 = max(0.0, WW[0][0] - 0.05)
    S1 = WW[-1][1] + 0.08

# Ha a záró „Élőben!” / „Nézd!” külön, hosszú szünet után jön, a szünetet
# kivágjuk (kép és hang együtt): így egy mondatnak hangzik, nem külön kiáltásnak.
# Az „élőben” szó soha nem kerül a videóba: ha a klip mégis kimondja a végén,
# a horog a szó előtt véget ér (kép és hang együtt), és a felirat sem írja ki.
if WW and len(WW) >= 2 and re.sub(r"[^\w]", "", WW[-1][2]).upper() == "ÉLŐBEN":
    WW = WW[:-1]
    S1 = WW[-1][1] + 0.12
    print("az 'eloben' szo kivagva a horog vegerol")
    HOLD = S1          # ettől kezdve a kép áll (a száj ne mondja ki némán sem)
else:
    HOLD = None
TAIL_WORDS = {"NÉZD"}
CUT = None          # (kezdet, vég, hossz) forrásidőben
TAIL = None         # a záró szó (kezdet, vég) a vágás utáni forrásidőben
if WW and len(WW) >= 2 and re.sub(r"[^\w]", "", WW[-1][2]).upper() in TAIL_WORDS:
    gap = WW[-1][0] - WW[-2][1]
    if gap > 0.30:
        c0, c1 = WW[-2][1] + 0.08, WW[-1][0] - 0.06
        # A szóhatárt a hangerő is ellenőrzi: a felismerő időzítése ±50 ms-ot téved,
        # és a záró szó első hangját nem vághatjuk le.
        hop = int(0.01 * SR)
        def rms_at(t):
            i = int(t * SR); return float(np.sqrt((CLIP_AUDIO[i:i + hop] ** 2).mean() + 1e-12))
        sp_r = [rms_at(t) for t in np.arange(S0, S1, 0.01)]
        thr = 0.30 * float(np.median([v for v in sp_r if v > max(sp_r) * 0.2]))
        for t in np.arange(c0, WW[-1][0] + 0.2, 0.01):      # a záró szó tényleges kezdete
            if rms_at(t) > thr:
                c1 = min(c1, t - 0.05); break
        for t in np.arange(c1, WW[-2][1] - 0.15, -0.01):    # az előző szó tényleges vége
            if rms_at(t) > thr:
                c0 = max(c0, t + 0.06); break
        CUT = (c0, c1, c1 - c0) if c1 - c0 > 0.12 else None
    if CUT is not None:
        D = CUT[2]
        WW[-1] = (WW[-1][0] - D, WW[-1][1] - D, WW[-1][2])
        S1 -= D
        print(f"szunet a zaro szo elott: {gap:.2f} s -> {gap - D:.2f} s (vagas {CUT[0]:.2f}-{CUT[1]:.2f})")
    TAIL = (WW[-1][0], WW[-1][1])
CUT_D = CUT[2] if CUT else 0.0
# A kép a kivágott szünetet nem ugorja át, hanem egy rövid szakaszon gyorsítva
# pörgeti át (a vágás előtt PRE, utána POST másodperc): a szünetben a száj
# nyugalomban van, így a gyorsítás nem látszik szájmozgás-csúszásnak.
PRE, POST = 0.16, 0.12

def src_time(u):
    """Kimeneti (vágás nélküli) forrásidő → valódi forrásidő a klipben."""
    if HOLD is not None:
        return min(u, HOLD)
    if CUT is None or u < CUT[0] - PRE:
        return u
    c0, _c1, d = CUT
    if u < c0 + POST:
        return (c0 - PRE) + (u - (c0 - PRE)) * (PRE + POST + d) / (PRE + POST)
    return u + d

def in_warp(u):
    return CUT is not None and CUT[0] - PRE <= u < CUT[0] + POST

AXI_OFF = max(0.0, S0 - 0.50)
A_END = S1 - AXI_OFF + 0.40
B_END = A_END + 1.15
if AXI_OFF + B_END + CUT_D > CLIP_DUR - 0.05:    # rövid klip: kevesebb ráhagyás
    B_END = CLIP_DUR - 0.05 - AXI_OFF - CUT_D
    A_END = min(A_END, B_END - 0.9)
print(f"beszed {S0:.2f}-{S1:.2f} s, klip {CLIP_DUR:.2f} s -> AXI_OFF {AXI_OFF:.2f}, A_END {A_END:.2f}, B_END {B_END:.2f}")

def hook_captions():
    """A horog feliratai a tudott mondatból, a klip szóidőzítésével."""
    words = A["line"].split()
    times = []
    if WW:
        # A tudott szavakat a felismert szavak idővonalára vetítjük a betűszám
        # arányában: így a félrehallás („E.I.” az „AI” helyett) sem csúsztatja el.
        def letters(w_):
            return max(1, len(re.sub(r"[^\w]", "", w_)))
        xs, ts = [0.0], [WW[0][0]]
        acc = 0.0
        for s_, e_, w_ in WW:
            xs.append(acc); ts.append(s_)
            acc += letters(w_)
            xs.append(acc); ts.append(e_)
        tot_w = sum(letters(w_) for w_ in words)
        acc2 = 0.0
        for w_ in words:
            a0 = acc2 / tot_w * acc
            acc2 += letters(w_)
            a1 = acc2 / tot_w * acc
            times.append((float(np.interp(a0, xs, ts)) - AXI_OFF, float(np.interp(a1, xs, ts)) - AXI_OFF))
    else:                                        # arányos becslés a betűszám szerint
        L = sum(len(w) + 1 for w in words)
        t, span = S0 - AXI_OFF, S1 - S0
        for w_ in words:
            d = span * (len(w_) + 1) / L
            times.append((t, t + d)); t += d
    # csoportok: az első tagmondat a vesszőig („MEGMUTATOM”), a többi az „AI”
    # előtti szónál kettéválik („HOGYAN RANGSOROLJA” | „EGY AI …”). A záró
    # „Élőben” / „Nézd” nem kap külön feliratot: a mondat része, nem felkiáltás.
    fe = next((i for i, w_ in enumerate(words) if w_.endswith(",")), 0)
    rest = list(range(fe + 1, len(words)))
    ai = next((i for i in rest if words[i].strip(",.!?").upper() == "AI"), None)
    cut = (ai - 1) if ai is not None and ai - 1 > rest[0] else (rest[0] + len(rest) // 2)
    groups = [list(range(0, fe + 1))] + [g for g in ([i for i in rest if i < cut], [i for i in rest if i >= cut]) if g]
    caps = []
    for gi, g in enumerate(groups):
        st = max(0.05, times[g[0]][0] - 0.06)
        en = times[groups[gi + 1][0]][0] - 0.04 if gi + 1 < len(groups) else min(A_END, times[g[-1]][1] + 0.9)
        text = re.sub(r"[,.!?]", "", " ".join(words[j] for j in g).upper())
        hi = " ".join(w_ for w_ in text.split() if w_ == "AI")
        caps.append((st, max(0.35, en - st), text, hi))
    return caps

# ─────────────────────────── ütemek időzítése ───────────────────────────
STATE_TL = []      # (idő, állapot)
CAM = []           # (idő, cy)
BOXES = []         # (kezdet, vég, keret)
TAPS = []          # (idő, x, y)
CAPS = hook_captions()
VOICE = []         # (fájl, idő)
DINGS = []
CLICKS = []
FAST = []          # (kezdet, vég): gyorsított várakozás jelzése

def target_cy(region, state):
    """A kamera függőleges közepe: a téma a kép felső-középső részére kerül,
    a felirat (a kép 61,5%-ánál) alá."""
    hv = H / Z
    x0, y0, x1, y1 = region
    rc, rh = (y0 + y1) / 2, y1 - y0
    cy = rc + 0.10 * hv if rh <= 0.55 * hv else rc + max(0.0, 0.5 * hv - rh / 2 - 60)
    if rh > hv - 120:                            # nem fér ki: a teteje látsszon
        cy = y0 - 60 + hv / 2
    # a tartalom alja alá csak egy keskeny sáv lóghat: üres, sötét képrész ne legyen
    lim = max(hv / 2, CONTENT_H.get(state, PH) - hv / 2 + 0.03 * hv)
    return min(max(cy, hv / 2), min(lim, PH - hv / 2))

first = A["first"]
STATE_TL.append((0.0, first))
first_region = ref(A["beats"][0].get("focus") or A["beats"][0].get("box")) or (0, 0, W, 900)
cy0 = target_cy(first_region, first)
CAM.append((B_END, cy0))
t = B_END + 0.25
for bi, b in enumerate(A["beats"]):
    t0 = t
    focus = ref(b.get("focus") or b.get("box"))
    tap = ref(b.get("tap"))
    region = focus
    if tap and focus:
        u = (min(focus[0], tap[0]), min(focus[1], tap[1]), max(focus[2], tap[2]), max(focus[3], tap[3]))
        if u[3] - u[1] <= H / Z - 160:
            region = u
    elif tap:
        region = tap
    show = b.get("show")
    if region and tap and b.get("wait"):
        # töltés közben a gombon marad a kép (az eredmény még nincs ott)
        CAM.append((t0 - 0.10, CAM[-1][1]))
        CAM.append((t0 + 0.50, target_cy(tap, b["wait"])))
    elif region:
        CAM.append((t0 - 0.10, CAM[-1][1]))
        CAM.append((t0 + 0.50, target_cy(region, show or first)))
    if tap:
        tt = t0 + 0.55
        TAPS.append((tt, (tap[0] + tap[2]) / 2, (tap[1] + tap[3]) / 2))
        CLICKS.append(tt)
        sw = tt + 0.28
        if b.get("wait"):
            STATE_TL.append((sw, b["wait"]))
            FAST.append((sw + 0.05, sw + 1.05))
            sw += 0.85
            CAM.append((sw, CAM[-1][1]))
            CAM.append((sw + 0.55, target_cy(region, show or first)))
        speech = sw + 0.12
    else:
        sw = t0 + 0.15
        speech = t0 + 0.35
    say = b.get("say")
    d = tts_dur(tts_make(say)) if say else 1.2
    end = speech + d
    if b.get("run"):
        run = b["run"]
        frames = RUN_FRAMES
        if isinstance(run, str):
            lo, _, hi = run.replace("R", "").partition(":")
            lo = int(lo) if lo else 1
            hi = int(hi) if hi else 10 ** 6
            frames = [f for f in RUN_FRAMES if lo <= f <= hi]
        span = max(end - sw, 0.45 * len(frames))
        end = max(end, sw + span)
        for i, f in enumerate(frames):
            STATE_TL.append((sw + span * i / max(1, len(frames)), f"R{f}"))
    elif show:
        STATE_TL.append((sw, show))
    if b.get("ding"):
        DINGS.append(sw)
    if say:
        VOICE.append((tts_make(say), speech))
        txt, hi = b.get("cap") or ("", "")
        CAPS.append((speech + 0.02, d + 0.10, txt, hi))
    box = ref(b.get("box"))
    if box:
        if BOXES and BOXES[-1][2] == box and speech - BOXES[-1][1] < 0.8:
            BOXES[-1] = (BOXES[-1][0], end + 0.25, box)      # ugyanaz a keret: nem rajzoljuk újra
        else:
            BOXES.append((speech + 0.05, end + 0.25, box))
    t = end + 0.38

C_END = t + 0.15
CTA = tts_make(A["cta"])
TOTAL = C_END + max(5.0, tts_dur(CTA) + 1.35)
VOICE.append((CTA, C_END + 0.45))
N = int(TOTAL * FPS)
print(f"hossz {TOTAL:.1f} s (horog {A_END:.1f}, bemutato {B_END:.1f}-{C_END:.1f}, zarokep {TOTAL - C_END:.1f})")

def cam_at(tt):
    if tt <= CAM[0][0]:
        return CAM[0][1]
    for a, b in zip(CAM, CAM[1:]):
        if tt <= b[0]:
            k = (tt - a[0]) / max(b[0] - a[0], 1e-6)
            return a[1] + (b[1] - a[1]) * smooth(max(0.0, min(1.0, k)))
    return CAM[-1][1]

XF = 0.22
def state_at(tt):
    cur, prev, ts = STATE_TL[0][1], None, -9
    for t_, s_ in STATE_TL:
        if tt >= t_:
            prev, cur, ts = cur, s_, t_
    k = (tt - ts) / XF
    if prev and prev != cur and k < 1:
        return prev, cur, smooth(max(0.0, k))
    return cur, cur, 0.0

# ─────────────────────────── a klip képe ───────────────────────────
class Clip:
    def __init__(self, path, w, h):
        self.w, self.h, self.n = w, h, -1
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS},scale={w}:{h}",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, bufsize=w * h * 3 * 4)
        self.cur = None
        self._next()

    def _next(self):
        b = self.p.stdout.read(self.w * self.h * 3)
        if len(b) < self.w * self.h * 3:
            return False
        self.cur = np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)
        self.n += 1
        return True

    def at(self, tt):
        want = max(0, int(round(tt * FPS)))
        while self.n < want and self._next():
            pass
        return self.cur

def quad_of(frame):
    f = frame.astype(np.int16)
    g = (f[..., 1] > 110) & (f[..., 1] - f[..., 0] > 45) & (f[..., 1] - f[..., 2] > 45)
    if g.sum() < 4000:
        return None, None
    q = fit_quad(g)
    return q, g

def _envelope_fit(t, v, outward):
    """Egyenes v = a*t + b a kijelző külső szélére. Az ujjak és a notch csak
    befelé harapnak a maszkba, ezért a befelé eső pontokat kidobjuk és újraillesztünk."""
    keep = np.ones(len(t), bool)
    a, b = 0.0, float(np.median(v))
    for _ in range(6):
        if keep.sum() < 8:
            break
        a, b = np.polyfit(t[keep], v[keep], 1)
        r = (v - (a * t + b)) * outward          # pozitív: kifelé
        keep = r > -2.5
    return a, b

def fit_quad(g):
    """A kijelző négy sarka a négy oldalegyenes metszéspontjaként. A sarkok
    lekerekítettek, és az ujjak rálógnak a szélre: a szélső pontok helyett a
    szélekre illesztett egyenesek adják a pontos, nem csúszó négyszöget."""
    ys, xs = np.nonzero(g)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    hh, ww = y1 - y0, x1 - x0
    rows = np.arange(int(y0 + 0.14 * hh), int(y1 - 0.14 * hh))
    cols = np.arange(int(x0 + 0.16 * ww), int(x1 - 0.16 * ww))
    L, R, T, B = [], [], [], []
    for y in rows:
        r = np.nonzero(g[y])[0]
        if len(r):
            L.append((y, r[0])); R.append((y, r[-1]))
    for x in cols:
        c = np.nonzero(g[:, x])[0]
        if len(c):
            T.append((x, c[0])); B.append((x, c[-1]))
    if min(len(L), len(T)) < 20:
        return None
    L, R, T, B = map(np.array, (L, R, T, B))
    la, lb = _envelope_fit(L[:, 0], L[:, 1], -1)      # x = la*y + lb
    ra, rb = _envelope_fit(R[:, 0], R[:, 1], +1)
    ta, tb = _envelope_fit(T[:, 0], T[:, 1], -1)      # y = ta*x + tb
    ba, bb = _envelope_fit(B[:, 0], B[:, 1], +1)
    def meet(xa, xb, ya, yb):                          # x = xa*y+xb, y = ya*x+yb
        y = (ya * xb + yb) / (1 - ya * xa)
        return [xa * y + xb, y]
    q = np.array([meet(la, lb, ta, tb), meet(ra, rb, ta, tb), meet(ra, rb, ba, bb), meet(la, lb, ba, bb)], float)
    c = q.mean(0)
    return c + (q - c) * 1.006

def persp(dst, src):
    Am, Bm = [], []
    for (x, y), (u, v) in zip(dst, src):
        Am += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        Bm += [u, v]
    return tuple(np.linalg.solve(np.array(Am, float), np.array(Bm, float)))

def _phone_aspect():
    probe = Clip(AXI, W, H)
    vals = []
    for tt in (AXI_OFF + 0.2, AXI_OFF + 1.0, AXI_OFF + 2.0):
        fr = probe.at(tt)
        q, _ = quad_of(fr) if fr is not None else (None, None)
        if q is not None:
            hgt = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
            wid = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
            vals.append(hgt / max(wid, 1))
    probe.p.kill()
    return float(np.median(vals)) if vals else None

PHONE_ASPECT = None
axi = Clip(AXI, W, H)
smooth_q = None
def axi_frame(t_src, z, ccx, ccy, screen):
    global smooth_q
    base = axi.at(t_src)
    q, mask = quad_of(base)
    if q is not None:
        smooth_q = q if smooth_q is None else smooth_q * 0.5 + q * 0.5
    cw, ch = W / z, H / z
    x0 = min(max(ccx - cw / 2, 0), W - cw)
    y0 = min(max(ccy - ch / 2, 0), H - ch)
    img = Image.fromarray(base).crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS)
    if smooth_q is None or mask is None:
        return img
    oq = [((px - x0) * z, (py - y0) * z) for px, py in smooth_q]
    sw, sh = screen.size
    try:
        warped = screen.transform((W, H), Image.PERSPECTIVE,
                                  persp(oq, [(0, 0), (sw, 0), (sw, sh), (0, sh)]), Image.BICUBIC)
    except np.linalg.LinAlgError:
        return img
    m = Image.fromarray((mask * 255).astype(np.uint8)).crop(
        (int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR)
    m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.1))
    img.paste(warped, (0, 0), m)
    return img

_SCR = {}
def phone_content(tt):
    global PHONE_ASPECT
    if PHONE_ASPECT is None:
        PHONE_ASPECT = _phone_aspect() or 2.17
        print(f"kijelzo aranya {PHONE_ASPECT:.2f}")
    """A telefon kijelzőjén az agent kártyája, lassan gördülve; világosabban,
    mert egy kijelző maga világít."""
    # A kivágás a kijelző arányát követi, és a kártyát tölti ki: alul nem marad
    # üres sáv. Ha a kártya hosszabb, mint ami kifér, lassan legördül.
    asp = PHONE_ASPECT or 2.17
    ch_full = CONTENT_H[first] + 40
    cw = min(PW, ch_full / asp)
    ch = cw * asp
    extra = max(0.0, CONTENT_H[first] + 40 - ch)
    sy = int(min(extra, 260) * ease_out(max(0.0, min(1, (tt - 1.0) / max(0.5, B_END - 1.0)))))
    key = (sy, int(cw))
    if key not in _SCR:
        x0 = (PW - cw) / 2
        im = PAGES[first].crop((int(x0), sy, int(x0 + cw), int(sy + ch)))
        if not LIGHT:
            im = ImageEnhance.Brightness(im).enhance(1.20)
        _SCR[key] = ImageEnhance.Color(im).enhance(1.10)
    return _SCR[key]

# ─────────────────────────── a lap, teljes képernyőn ───────────────────────────
def crop_of(im, z, cx, cy):
    cw, ch = W / z, H / z
    x0 = min(max(cx - cw / 2, 0), PW - cw)
    y0 = min(max(cy - ch / 2, 0), PH - ch)
    return im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS), x0, y0

def page_frame(tt):
    # enyhe ráközelítés egész idő alatt, hogy a kép éljen
    z = Z * (1.0 + 0.012 * min(1.0, max(0.0, (tt - B_END) / max(1.0, C_END - B_END))))
    cy = cam_at(tt)
    a, b, k = state_at(tt)
    ia, x0, y0 = crop_of(PAGES[a], z, W / 2, cy)
    if a != b:
        ib, _, _ = crop_of(PAGES[b], z, W / 2, cy)
        ia = Image.blend(ia, ib, k)
    return ia, z, x0, y0

BOX_OUT = None      # az épp látszó keret függőleges helye a kimeneten
def draw_boxes(img, tt, z, x0, y0):
    global BOX_OUT
    BOX_OUT = None
    for b0, b1, (rx0, ry0, rx1, ry1) in BOXES:
        if not (b0 <= tt < b1):
            continue
        BOX_OUT = ((ry0 - 10 - y0) * z, (ry1 + 10 - y0) * z)
        X0, Y0 = (rx0 - 10 - x0) * z, (ry0 - 10 - y0) * z
        X1, Y1 = (rx1 + 10 - x0) * z, (ry1 + 10 - y0) * z
        X0, X1 = max(X0, 14), min(X1, W - 14)
        k = ease_out(min(1.0, (tt - b0) / 0.28))
        fade = 1.0 if tt < b1 - 0.26 else (b1 - tt) / 0.26
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle([X0, Y0, X1, Y1], radius=26,
                                               outline=CYAN + (int(130 * fade * k),), width=18)
        lay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(13)))
        ImageDraw.Draw(lay).rounded_rectangle([X0, Y0, X0 + (X1 - X0) * k, Y1], radius=26,
                                              outline=CYAN + (int(240 * fade),), width=6)
        img.alpha_composite(lay)
        return

def draw_tap(img, tt, z, x0, y0):
    for t_, px, py in TAPS:
        d = tt - t_
        if not (-0.02 <= d < 0.52):
            continue
        X, Y = (px - x0) * z, (py - y0) * z
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(lay)
        k = min(1.0, d / 0.22)
        r = 96 - 56 * ease_out(k)
        ring = (40, 40, 60) if LIGHT else (255, 255, 255)
        dr.ellipse([X - r, Y - r, X + r, Y + r], outline=ring + (int(235 * (1 - 0.3 * k)),), width=7)
        if d > 0.16:
            q = (d - 0.16) / 0.36
            rr = 54 + 150 * ease_out(min(1, q))
            dr.ellipse([X - rr, Y - rr, X + rr, Y + rr], outline=CYAN + (int(200 * max(0, 1 - q)),), width=6)
        img.alpha_composite(lay)
        return

FAST_F = fnt(F_MONO, 26)
def draw_fast(img, tt):
    for f0, f1 in FAST:
        if f0 <= tt < f1 + 0.25:
            a = min(1.0, (tt - f0) / 0.15, max(0.0, (f1 + 0.25 - tt) / 0.25))
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            txt = "GYORSÍTVA  ›››"
            tw = d.textlength(txt, font=FAST_F)
            d.rounded_rectangle([W / 2 - tw / 2 - 22, 118, W / 2 + tw / 2 + 22, 166], radius=24,
                                fill=(6, 8, 18, int(200 * a)), outline=CYAN + (int(200 * a),), width=2)
            d.text((W / 2, 128), txt, font=FAST_F, fill=CYAN + (int(255 * a),), anchor="ma")
            img.alpha_composite(lay)
            return

# ─────────────────────────── feliratok ───────────────────────────
CF = fnt(F_BLACK, 76)
def draw_caption(img, tt):
    for st, du, text, hi in CAPS:
        if not text or not (st <= tt < st + du):
            continue
        k = (tt - st) / du
        pop = 1.0 if (tt - st) > 0.16 else 0.80 + 1.25 * (tt - st)
        fade = 1.0 if k < 0.88 else 1 - (k - 0.88) / 0.12
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        lines, cur = [], ""
        for w_ in text.split():
            t2 = (cur + " " + w_).strip()
            if d.textlength(t2, font=CF) > W - 150 and cur:
                lines.append(cur); cur = w_
            else:
                cur = t2
        lines.append(cur)
        hiw = set(hi.split())
        yb = int(H * 0.615) - (len(lines) - 1) * 46
        if BOX_OUT is not None and tt >= B_END:
            capt, capb = yb - 20, yb + 92 * len(lines) + 10
            bt, bb = BOX_OUT
            if bb > capt and bt < capb:                       # rálógna a kiemelt elemre
                if bb + 40 + (capb - capt) < H - 150:
                    yb = int(bb + 50)
                elif bt - 40 - (capb - capt) > 200:
                    yb = int(bt - 30 - (capb - capt))
        for ln in lines:
            x = (W - d.textlength(ln, font=CF)) / 2
            for w_ in ln.split():
                col = CYAN if w_.strip(".,·:?!") in {h.strip(".,·:?!") for h in hiw} else (255, 255, 255)
                d.text((x, yb), w_, font=CF, fill=col + (255,), stroke_width=10, stroke_fill=(3, 3, 10, 235))
                x += d.textlength(w_ + " ", font=CF)
            yb += 92
        if pop != 1.0:
            nw, nh = int(W * pop), int(H * pop)
            c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            c.paste(lay.resize((nw, nh), Image.BICUBIC), ((W - nw) // 2, int((yb - 92 * len(lines) + 46) * (1 - pop))))
            lay = c
        if fade < 1:
            lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
        img.alpha_composite(lay)
        return

LOGO_F = fnt(F_BOLD, 34)
AI_F = fnt(F_MED, 22)
TOPGRAD = Image.new("RGBA", (W, 190), (0, 0, 0, 0))
_g = np.zeros((190, W, 4), np.uint8)
_ramp = np.clip((190 - np.arange(190)) / 95.0, 0, 1)          # 0..95 px: teljesen fedett
_g[..., 3] = (248 * _ramp ** 1.3).astype(np.uint8)[:, None]
_g[..., :3] = (4, 4, 12)
TOPGRAD = Image.fromarray(_g, "RGBA")

def draw_chrome(img, tt):
    a = int(255 * min(1, max(0, (tt - 0.25) / 0.5)))
    if tt >= B_END - 0.3:
        img.alpha_composite(TOPGRAD.copy() if tt > B_END else
                            Image.fromarray(np.dstack([_g[..., :3], (_g[..., 3] * max(0, (tt - B_END + 0.3) / 0.3)).astype(np.uint8)]), "RGBA"))
    d = ImageDraw.Draw(img)
    if a > 0:
        d.ellipse([58, 60, 78, 80], fill=CYAN + (a,))
        d.text((92, 54), "AXIMBRA", font=LOGO_F, fill=(255, 255, 255, a))
        d.text((W - 58, 62), "AI-GENERÁLT", font=AI_F, fill=(255, 255, 255, 120), anchor="ra")

# ─────────────────────────── zárókép ───────────────────────────
E_BRAND, E_URL, E_SUB, E_MONO = fnt(F_BLACK, 104), fnt(F_BOLD, 62), fnt(F_MED, 40), fnt(F_MONO, 25)
E_AGENT = fnt(F_MONO, 30)

def end_card(bg, k):
    img = bg.filter(ImageFilter.GaussianBlur(26)).convert("RGBA")
    img.alpha_composite(Image.new("RGBA", (W, H), (4, 4, 12, 222)))
    d = ImageDraw.Draw(img)
    app = ease_out(min(1, k / 0.22)); al = int(255 * app)
    y = int(H * 0.36) + int((1 - app) * 40)
    d.text((W // 2, y - 78), A["name"].upper(), font=E_AGENT, fill=CYAN + (int(al * 0.9),), anchor="ma")
    d.ellipse([W // 2 - 192, y + 28, W // 2 - 160, y + 60], fill=CYAN + (al,))
    d.text((W // 2 + 22, y), "AXIMBRA", font=E_BRAND, fill=(255, 255, 255, al), anchor="ma")
    w2 = ease_out(min(1, max(0, (k - 0.14) / 0.26)))
    d.rectangle([W // 2 - int(235 * w2), y + 152, W // 2 + int(235 * w2), y + 156], fill=CYAN + (al,))
    a2 = int(255 * ease_out(min(1, max(0, (k - 0.22) / 0.25))))
    d.text((W // 2, y + 212), "aximbra.hu", font=E_URL, fill=CYAN + (a2,), anchor="ma")
    a3 = int(255 * ease_out(min(1, max(0, (k - 0.34) / 0.25))))
    s1, s2 = A["end_sub"]
    d.text((W // 2, y + 312), s1, font=E_SUB, fill=(255, 255, 255, a3), anchor="ma")
    d.text((W // 2, y + 368), s2, font=E_SUB, fill=(190, 195, 215, a3), anchor="ma")
    d.text((W // 2, H - 158), A["note"], font=E_MONO, fill=(150, 156, 180, a3), anchor="ma")
    d.text((W // 2, H - 118), "A videó AI-val készült", font=E_MONO, fill=(120, 126, 150, a3), anchor="ma")
    return img

# ─────────────────────────── hang ───────────────────────────
def level(x):
    """Hangszintkiegyenlítés: ahol a klip hangja a beszéd szokásos szintje fölé
    ugrik (a Veo gyakran kiabálja a záró szót), ott lehalkítjuk — csak lefelé
    nyúl, a halk részekhez nem."""
    hop = int(0.01 * SR)
    n = len(x) // hop
    if n < 10:
        return x
    e = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    sm = np.zeros_like(e)
    for i in range(n):                                    # gyors felfutás, lassú lecsengés
        p = sm[i - 1] if i else e[0]
        sm[i] = p + (e[i] - p) * (0.5 if e[i] > p else 0.06)
    speech = sm[sm > sm.max() * 0.25]
    target = float(np.median(speech)) * 1.0 if len(speech) else float(sm.max())
    gain = np.minimum(1.0, target / np.maximum(sm, 1e-9))
    k = 6
    gain = np.convolve(gain, np.ones(k) / k, mode="same")
    g = np.repeat(gain, hop)
    out = x.copy()
    out[: len(g)] *= g
    return out

def build_audio(path):
    n = int(TOTAL * SR)
    out = np.zeros(n, np.float32); duck = np.zeros(n, np.float32)
    def put(sig, tt, g=1.0):
        i = int(tt * SR); j = min(n, i + len(sig))
        if j > i:
            out[i:j] += sig[:j - i] * g
            duck[i:j] = 1.0
    # A horogban a klip saját hangja szól: a szájmozgás így szótagra pontos.
    src_a = CLIP_AUDIO
    if CUT is not None:                       # a szünet kivágása 40 ms-os áttűnéssel
        i0, i1, xf = int(CUT[0] * SR), int(CUT[1] * SR), int(0.04 * SR)
        ramp = np.linspace(0, 1, xf, dtype=np.float32)
        src_a = np.concatenate([src_a[:i0], src_a[i0:i0 + xf] * (1 - ramp) + src_a[i1:i1 + xf] * ramp, src_a[i1 + xf:]])
    hook = src_a[int(AXI_OFF * SR): int((AXI_OFF + B_END + 0.25) * SR)].copy()
    if HOLD is not None:                       # a kivágott szó hangja se maradjon benne
        i = int((HOLD - AXI_OFF) * SR); f = int(0.10 * SR)
        hook[i:i + f] *= np.linspace(1, 0, len(hook[i:i + f]))
        hook[i + f:] = 0
    sp = src_a[int(S0 * SR): int(S1 * SR)]
    hook_rms = float(np.sqrt((sp ** 2).mean())) or 1.0
    ref_sig = np.concatenate([load(f) for f, _ in VOICE[:3]])
    ref_rms = float(np.sqrt((ref_sig ** 2).mean())) or hook_rms
    hook *= min(1.6, ref_rms / hook_rms)
    hook = level(hook)
    if TAIL is not None:                      # a záró szó ne legyen kiemelve
        i0 = max(0, int((TAIL[0] - AXI_OFF - 0.03) * SR)); i1 = min(len(hook), int((TAIL[1] - AXI_OFF + 0.12) * SR))
        if i1 > i0:
            seg = hook[i0:i1].copy()
            lp = np.zeros_like(seg); acc = 0.0; k = 0.35       # egypólusú aluláteresztő: a kiabálás éle
            for i in range(len(seg)):
                acc += k * (seg[i] - acc); lp[i] = acc
            soft = (0.45 * seg + 0.55 * lp) * 0.72
            r = min(int(0.03 * SR), (i1 - i0) // 2)
            w = np.ones(i1 - i0, np.float32); w[:r] = np.linspace(0, 1, r); w[-r:] = np.linspace(1, 0, r)
            hook[i0:i1] = seg * (1 - w) + soft * w
    fl = int(0.45 * SR)
    hook[-fl:] *= np.linspace(1, 0, fl)
    put(hook, 0.0, 1.18)
    for f, tt in VOICE:
        put(load(f), tt, 1.18)

    tt = np.arange(n) / SR
    pad = np.zeros(n, np.float32)
    for f0, g in [(110.0, .50), (164.81, .34), (220.0, .20), (329.63, .09)]:
        pad += g * np.sin(2 * np.pi * f0 * tt + 0.6 * np.sin(2 * np.pi * 0.07 * tt))
    pad *= (0.55 + 0.45 * np.sin(2 * np.pi * 0.055 * tt - 1.2))
    beat = 1.2
    sub = np.sin(2 * np.pi * 52 * tt) * np.exp(-((tt % beat) / beat) * 14) * (tt > B_END - 0.5)
    rng = np.random.default_rng(3)
    tick = rng.standard_normal(n).astype(np.float32) * np.exp(-((tt % (beat / 2)) / (beat / 2)) * 90) * 0.5 * (tt > B_END + 3.5)
    for i in range(1, 6):
        tick[i:] = tick[i:] * .55 + tick[:-i] * .45
    music = pad * 0.055 + sub * 0.075 + tick * 0.030
    for ct in (B_END - 0.55, C_END - 0.30):
        L = int(0.75 * SR); t2 = np.arange(L) / SR
        nz = rng.standard_normal(L).astype(np.float32)
        for i in range(1, 9):
            nz[i:] = nz[i:] * .6 + nz[:-i] * .4
        s = nz * (t2 / t2[-1]) ** 2 * np.sin(2 * np.pi * (300 + 1500 * t2 / t2[-1]) * t2) * 0.9
        i0 = int(ct * SR); j = min(n, i0 + L); music[i0:j] += s[:j - i0] * 0.34
    L = int(1.1 * SR); t2 = np.arange(L) / SR
    ding = (np.sin(2 * np.pi * 1320 * t2) + 0.5 * np.sin(2 * np.pi * 1980 * t2)) * np.exp(-t2 * 7)
    for dt in [B_END + 0.05] + DINGS:
        i0 = int(dt * SR); j = min(n, i0 + L); music[i0:j] += ding[: j - i0] * 0.09
    L = int(0.05 * SR); t2 = np.arange(L) / SR
    click = rng.standard_normal(L).astype(np.float32) * np.exp(-t2 * 160) * 0.5 + np.sin(2 * np.pi * 2400 * t2) * np.exp(-t2 * 120) * 0.5
    for ct in CLICKS:
        i0 = int(ct * SR); j = min(n, i0 + L); music[i0:j] += click[: j - i0] * 0.16
    k = int(0.22 * SR)
    env = np.clip(np.convolve(duck, np.ones(k) / k, mode="same"), 0, 1)
    music *= (1 - 0.62 * env)
    music[: int(0.5 * SR)] *= np.linspace(0, 1, int(0.5 * SR))
    music[-int(1.2 * SR):] *= np.linspace(1, 0, int(1.2 * SR))
    out += music
    pk = float(np.abs(out).max())
    if pk > 0:
        out = out / pk * 0.94
    out[-int(0.5 * SR):] *= np.linspace(1, 0, int(0.5 * SR))
    open(path, "wb").write((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())

# ─────────────────────────── renderelés ───────────────────────────
def frame(tt):
    global LAST
    if tt < B_END:
        if tt < A_END:
            e = ease_out(tt / A_END)
            z, ccx, ccy = 1.0 + 0.055 * e, W / 2, H / 2 - 40 * e
        else:
            k = ease_in((tt - A_END) / (B_END - A_END))
            qx, qy = (smooth_q.mean(0) if smooth_q is not None else (W / 2, H / 2))
            z = 1.055 + (4.30 - 1.055) * k
            ccx = W / 2 + (qx - W / 2) * k
            ccy = (H / 2 - 40) + (qy - (H / 2 - 40)) * k
        img = axi_frame(src_time(tt + AXI_OFF), z, ccx, ccy, phone_content(tt)).convert("RGBA")
        if in_warp(tt + AXI_OFF) and PREV_HOOK is not None:      # gyorsított rész: mozgáselmosás
            img = Image.blend(PREV_HOOK, img, 0.6)
        globals()["PREV_HOOK"] = img
        if tt > B_END - 0.18:           # a telefon kijelzője kitölti a képet: átúszás a lapra
            im0, *_ = page_frame(B_END)
            img = Image.blend(img, im0.convert("RGBA"), (tt - (B_END - 0.18)) / 0.18)
    elif tt < C_END:
        im0, z, x0, y0 = page_frame(tt)
        img = im0.convert("RGBA")
        draw_boxes(img, tt, z, x0, y0)
        draw_tap(img, tt, z, x0, y0)
        LAST = img
    else:
        k = (tt - C_END) / (TOTAL - C_END)
        base = LAST if LAST is not None else Image.new("RGBA", (W, H), (4, 4, 12, 255))
        zz = 1.0 + 0.06 * k
        cw, ch = int(W / zz), int(H / zz)
        img = end_card(base.crop(((W - cw) // 2, (H - ch) // 2, (W - cw) // 2 + cw, (H - ch) // 2 + ch))
                       .resize((W, H), Image.BICUBIC), k)
    if tt < B_END or tt >= C_END:
        globals()["BOX_OUT"] = None
    if tt < C_END:
        draw_caption(img, tt)
        draw_chrome(img, tt)
        draw_fast(img, tt)
    if tt > TOTAL - 0.6:
        img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)), (tt - (TOTAL - 0.6)) / 0.6)
    return img.convert("RGB")

LAST = None
PREV_HOOK = None
if __name__ == "__main__":
    if PREVIEW:                      # néhány kulcskép ellenőrzésre, videó nélkül
        marks = [1.0, A_END - 0.3, B_END + 0.4] + [b0 + 0.6 for b0, _, _ in BOXES] + [C_END + 2.5]
        ims = []
        for i in range(N):
            tt = i / FPS
            im = frame(tt) if (tt < B_END or any(abs(tt - m) < 0.5 / FPS for m in marks) or tt >= C_END - 1 / FPS) else None
            if im is not None and any(abs(tt - m) < 0.5 / FPS for m in marks):
                ims.append(im.resize((W // 3, H // 3)))
            if tt > max(marks) + 0.1:
                break
        cols = 6
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (W // 3 + 8), rows * (H // 3 + 8)), (50, 50, 50))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * (W // 3 + 8), (i // cols) * (H // 3 + 8)))
        sheet.save(f"preview{K:02d}.png")
        print("elonezet:", f"preview{K:02d}.png", len(ims), "kep")
        sys.exit(0)
    mix = f"mix{K:02d}.raw"
    build_audio(mix)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", mix,
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", OUT], stdin=subprocess.PIPE)
    for i in range(N):
        ff.stdin.write(frame(i / FPS).tobytes())
        if i % 150 == 0:
            print(f"{i}/{N}", flush=True)
    ff.stdin.close()
    axi.p.kill()
    if ff.wait() != 0:
        sys.exit("ffmpeg hiba")
    os.remove(mix)
    print("kesz", OUT)

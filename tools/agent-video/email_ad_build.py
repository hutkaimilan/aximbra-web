"""AXIMBRA reklám — végleges összeállítás.

Forrás:
  clips/c1.mp4      Axi (Veo), zöld telefonkijelzővel, 720x1280
  shot_full.png     az aximbra.hu e-mail agent valódi eredménye, 1080x6142, éles
  shot_running.png  a futás közbeni állapot
  h*.mp3 / v*.mp3   magyar narráció

A képernyőtartalom álló képből jön, a görgetés és a ráközelítés kamerával
készül: így minden betű éles marad, és pontosan a narrációhoz igazítható.
Kimenet: 1080x1920, 30 fps.
"""
from __future__ import annotations
import subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

W, H, FPS = 1080, 1920, 30
CYAN = (0, 233, 255)
OUT = sys.argv[1] if len(sys.argv) > 1 else "aximbra_reklam.mp4"
AXI = "clips/c1.mp4"
AXI_OFF = 0.75          # ennyivel kesobbrol indul a klip

F_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
F_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
fnt = ImageFont.truetype

# D_END = C_END: a bemutato utan nincs visszateres a figurara, rogton a zarokep jon.
A_END, B_END, C_END, D_END, TOTAL = 6.25, 7.40, 36.60, 36.60, 42.10
INS0 = 28.90        # innentol a valodi kuldes-gombok betetje
# A jovahagyasi mondat a kepernyo felett szol, ahol nem latszik arc. A Veo-klip
# szaja a sajat hangjahoz sem pontos, ezert uj mondatot nem adunk a szajaba.

# A bemutato negy allapotbol all: eredmeny -> levél kinyitva -> valasz keszul ->
# valasz kesz. Mindegyik egy eles, teljes oldalas kep; a gorgetes kamera.
PAGES = {}
ST = [("A", "st_A.png", 7.40), ("B", "st_B.png", 15.60),
      ("W", "st_W.png", 21.40), ("C", "st_C.png", 22.45)]
XF = 0.22                                    # atuszas hossza allapotvaltaskor
N = int(TOTAL * FPS)

# a lap elemei a teljes képen (képpont, a layout.json CSS-értékeinek kétszerese)

# out → (zoom, vízszintes közép, függőleges közép). A zoom sehol nem nagyobb
# 1.08-nál: a lap tartalma (x 40..1040) így mindig teljes szélességében látszik.
CAM = [(7.40, 1.00, 540, 1150),
       (8.00, 1.08, 540, 762), (9.60, 1.08, 540, 778),      # FELDOLGOZOTT 10
       (10.15, 1.08, 540, 958), (11.35, 1.08, 540, 974),    # VÁLASZ SZÜKSÉGES 4
       (11.95, 1.02, 540, 1950), (13.70, 1.02, 540, 1990),  # kategóriák
       (14.25, 1.00, 540, 2470), (15.55, 1.00, 540, 2470),  # az első levél
       (16.15, 1.00, 540, 2880), (18.00, 1.00, 540, 2960),  # miért sürgős
       (18.35, 1.00, 540, 3020), (19.25, 1.00, 540, 3070),  # következő lépés
       (19.80, 1.06, 542, 3700), (21.00, 1.12, 542, 3870),  # a gomb
       (22.40, 1.14, 542, 3900),
       (22.60, 1.16, 542, 4010), (24.80, 1.16, 542, 4030),  # tárgy
       (25.85, 1.16, 542, 4330), (28.60, 1.16, 542, 4360),  # a megírt válasz
       (29.30, 1.16, 542, 4620), (32.00, 1.16, 542, 4640)]  # „nem küldi el”
# 1.16-nál a kivágás x 77..1008: pont a válaszdoboz szélessége, semmi nem esik ki.

# (kezdet, vég, keret az oldalon)  — a kiemelt rész mindig a beszélt dolog
BOXES = [(8.15, 9.55, (48, 584, 1032, 790)),        # 10
         (10.30, 11.30, (48, 812, 1032, 1060)),     # 4
         (18.40, 19.20, (78, 2856, 1006, 3064)),    # következő lépés
         (20.15, 21.32, (78, 3810, 486, 3900)),     # „Megfogalmazom a választ”
         (22.95, 24.70, (78, 3914, 1006, 3996))]    # tárgy
# (idopont, x, y) – koppintas jelzes
TAPS = [(15.18, 540, 2470), (20.98, 278, 3856)]
# (kezdet, vég, kiemelendő kártya)

def interp(tab, t, i=1):
    if t <= tab[0][0]:
        return tab[0][i]
    for a, b in zip(tab, tab[1:]):
        if t <= b[0]:
            k = (t - a[0]) / max(b[0] - a[0], 1e-6)
            k = k * k * (3 - 2 * k)
            return a[i] + (b[i] - a[i]) * k
    return tab[-1][i]

ease_out = lambda k: 1 - (1 - k) ** 3
ease_in = lambda k: k * k * k

# ─────────────────────────── források ───────────────────────────
for _k, _f, _t in ST:
    PAGES[_k] = Image.open(_f).convert("RGB")
PAGE = PAGES["A"]                 # ez kerul a telefon kijelzojere is
# A kuldes-gombok a tulajdonos sajat, eles postafiokjabol valo kepernyokep
# gombsavja. Szemelyes adat nincs rajta; kulon betetkent jelenik meg, nem
# a mintapostafiok kepebe vagva.
SEND = Image.open("send_card.png").convert("RGB")
SEND = SEND.resize((940, round(SEND.height * 940 / SEND.width)), Image.LANCZOS)
SEND_XY = (70, 648)
SEND_BOXES = [(29.55, 31.30, (130, 774, 716, 866)),    # Mentés a Gmail vázlatok közé
              (31.50, 33.30, (130, 899, 516, 989)),    # E-mail elküldése
              (34.00, 36.25, (126, 1012, 930, 1124))]  # elküldeni csak te tudod
LBL = fnt(F_MONO, 30)

def insert_frame(t, bg):
    """A kuldes-gombok betetje: elmosott lap folott egy kartya."""
    img = bg.filter(ImageFilter.GaussianBlur(16)).convert("RGBA")
    img.alpha_composite(Image.new("RGBA", (W, H), (4, 4, 12, 170)))
    k = ease_out(min(1.0, (t - INS0) / 0.40))
    card = Image.new("RGBA", (SEND.width + 16, SEND.height + 16), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle([0, 0, card.width - 1, card.height - 1],
                                           radius=22, fill=(8, 8, 18, 255),
                                           outline=CYAN + (170,), width=3)
    card.paste(SEND, (8, 8))
    x, y = SEND_XY[0] - 8, int(SEND_XY[1] - 8 + (1 - k) * 70)
    if k < 1:
        card.putalpha(card.getchannel("A").point(lambda v: int(v * k)))
    img.alpha_composite(card, (x, y))
    d = ImageDraw.Draw(img)
    d.text((W // 2, SEND_XY[1] - 62), "SAJÁT POSTAFIÓKON", font=LBL,
           fill=CYAN + (int(220 * k),), anchor="ma")
    for b0, b1, (X0, Y0, X1, Y1) in SEND_BOXES:
        if not (b0 <= t < b1):
            continue
        kk = ease_out(min(1.0, (t - b0) / 0.26))
        fade = 1.0 if t < b1 - 0.24 else (b1 - t) / 0.24
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle([X0, Y0, X1, Y1], radius=20,
                                               outline=CYAN + (int(140 * fade * kk),), width=18)
        lay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(12)))
        ImageDraw.Draw(lay).rounded_rectangle([X0, Y0, X0 + (X1 - X0) * kk, Y1], radius=20,
                                              outline=CYAN + (int(245 * fade),), width=6)
        img.alpha_composite(lay)
        break
    return img
PW, PH = PAGE.size

class Clip:
    """A Veo-klip képkockái 30 fps-en, egy menetben olvasva."""
    def __init__(self, path, w, h):
        self.w, self.h, self.n = w, h, -1
        self.p = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS},scale={w}:{h}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, bufsize=w * h * 3 * 4)
        self.cur = None
        self._next()

    def _next(self):
        b = self.p.stdout.read(self.w * self.h * 3)
        if len(b) < self.w * self.h * 3:
            return False
        self.cur = np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)
        self.n += 1
        return True

    def at(self, t):
        want = max(0, int(round(t * FPS)))
        while self.n < want and self._next():
            pass
        return self.cur

axi = Clip(AXI, W, H)
axi_end = Clip(AXI, W, H)      # a zaro beallitashoz, kulon olvasoval

def page_view(cy, sy_h=2340):
    """A telefon kijelzőjére illő, 9:19.5 arányú kivágás a lapból."""
    y0 = int(min(max(cy, 0), PH - sy_h))
    return PAGE.crop((0, y0, PW, y0 + sy_h))

_SCR = {}
def phone_content(t):
    """A kijelzon az aximbra.hu valodi eredmenye, lassan gordulve.
    A tartalom vilagosabb, mert egy telefonkijelzo maga vilagit."""
    sy = int(300 * ease_out(max(0.0, min(1, (t - 1.2) / (B_END - 1.2)))))   # elobb a fejlec latszik
    if sy not in _SCR:
        im = page_view(sy)
        im = ImageEnhance.Brightness(im).enhance(1.20)
        _SCR[sy] = ImageEnhance.Color(im).enhance(1.10)
    return _SCR[sy]

# ─────────────────────────── Axi + telefon ───────────────────────────
def quad_of(frame):
    f = frame.astype(np.int16)
    g = (f[..., 1] > 110) & (f[..., 1] - f[..., 0] > 45) & (f[..., 1] - f[..., 2] > 45)
    if g.sum() < 4000:
        return None, None
    ys, xs = np.nonzero(g)
    s, d = xs + ys, xs - ys
    q = np.array([[xs[s.argmin()], ys[s.argmin()]], [xs[d.argmax()], ys[d.argmax()]],
                  [xs[s.argmax()], ys[s.argmax()]], [xs[d.argmin()], ys[d.argmin()]]], float)
    c = q.mean(0)
    return c + (q - c) * 1.035, g

def persp(dst, src):
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        B += [u, v]
    return tuple(np.linalg.solve(np.array(A, float), np.array(B, float)))

smooth_q = None
def axi_frame(t_src, z, ccx, ccy, screen, clip=None):
    global smooth_q
    base = (clip or axi).at(t_src)
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

# ─────────────────────────── a lap, teljes képernyőn ───────────────────────────
def crop_of(im, z, cx, cy):
    pw, ph = im.size
    cw, ch = W / z, H / z
    x0 = min(max(cx - cw / 2, 0), pw - cw)
    y0 = min(max(cy - ch / 2, 0), ph - ch)
    return im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS), x0, y0

def state_at(t):
    """Melyik allapotkep latszik, es kell-e atuszas a kovetkezore."""
    for i, (k, _f, t0) in enumerate(ST):
        if i and abs(t - t0) < XF / 2:
            return ST[i - 1][0], k, (t - (t0 - XF / 2)) / XF
    cur = ST[0][0]
    for k, _f, t0 in ST:
        if t >= t0 - XF / 2:
            cur = k
    return cur, cur, 0.0

def page_frame(t):
    z = interp(CAM, t, 1); cx = interp(CAM, t, 2); cy = interp(CAM, t, 3)
    a, b, k = state_at(t)
    ia, x0, y0 = crop_of(PAGES[a], z, cx, cy)
    if a != b:
        ib, x0b, y0b = crop_of(PAGES[b], z, cx, cy)
        kk = k * k * (3 - 2 * k)
        ia = Image.blend(ia, ib, kk)
        if kk > 0.5:
            x0, y0 = x0b, y0b
    return ia, z, x0, y0

def draw_boxes(img, t, z, x0, y0):
    """Cian keret arra, amirol epp szo van."""
    for b0, b1, (rx0, ry0, rx1, ry1) in BOXES:
        if not (b0 <= t < b1):
            continue
        X0, Y0 = (rx0 - x0) * z, (ry0 - y0) * z
        X1, Y1 = (rx1 - x0) * z, (ry1 - y0) * z
        k = ease_out(min(1.0, (t - b0) / 0.28))
        fade = 1.0 if t < b1 - 0.26 else (b1 - t) / 0.26
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle([X0, Y0, X1, Y1], radius=26,
                                               outline=CYAN + (int(130 * fade * k),), width=18)
        lay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(13)))
        ImageDraw.Draw(lay).rounded_rectangle([X0, Y0, X0 + (X1 - X0) * k, Y1], radius=26,
                                              outline=CYAN + (int(240 * fade),), width=6)
        img.alpha_composite(lay)
        return

def draw_tap(img, t, z, x0, y0):
    """Koppintas: osszehuzodo gyuru, majd egy kifuto hullam."""
    for tt, px, py in TAPS:
        d = t - tt
        if not (-0.02 <= d < 0.52):
            continue
        X, Y = (px - x0) * z, (py - y0) * z
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(lay)
        k = min(1.0, d / 0.22)
        r = 96 - 56 * ease_out(k)
        dr.ellipse([X - r, Y - r, X + r, Y + r], outline=(255, 255, 255, int(235 * (1 - 0.3 * k))), width=7)
        if d > 0.16:
            q = (d - 0.16) / 0.36
            rr = 54 + 150 * ease_out(min(1, q))
            dr.ellipse([X - rr, Y - rr, X + rr, Y + rr], outline=CYAN + (int(200 * max(0, 1 - q)),), width=6)
        img.alpha_composite(lay)
        return


# ─────────────────────────── feliratok ───────────────────────────
CAPS = [
    (0.50, 0.62, "MEGMUTATOM", ""),
    (1.15, 1.18, "HOGYAN VÁLOGATJA SZÉT", "SZÉT"),
    (2.38, 1.55, "EGY AI A LEVELEIDET", "AI"),
    (4.55, 1.10, "ÉLŐBEN", "ÉLŐBEN"),
    (7.72, 1.72, "TÍZ LEVÉL A POSTAFIÓKBAN", "TÍZ"),
    (10.02, 1.30, "NÉGYRE KELL MA VÁLASZOLNI", "NÉGYRE"),
    (11.92, 1.70, "A TÖBBIT KATEGÓRIÁBA SOROLTA", "KATEGÓRIÁBA"),
    (14.22, 1.20, "NYISD MEG BÁRMELYIKET", ""),
    (16.12, 1.42, "MEGMONDJA, MIÉRT SÜRGŐS", "SÜRGŐS"),
    (17.60, 1.52, "ÉS MI A KÖVETKEZŐ LÉPÉS", "KÖVETKEZŐ LÉPÉS"),
    (19.72, 1.55, "EGY GOMBBAL MEGÍRJA A VÁLASZT", "MEGÍRJA"),
    (22.82, 2.40, "TÁRGGYAL, VÁLASZTHATÓ HANGNEMBEN", "HANGNEMBEN"),
    (25.82, 2.80, "AMIT NEM TUD, AZT JELÖLI NEKED", "JELÖLI"),
    (29.24, 2.05, "A GMAIL VÁZLATOK KÖZÉ IS BETESZI", "VÁZLATOK"),
    (31.42, 1.78, "VAGY EL IS KÜLDI", "EL IS KÜLDI"),
    (34.02, 2.00, "ELKÜLDENI CSAK TE TUDOD", "CSAK TE"),
]
CF = fnt(F_BLACK, 76)

def draw_caption(img, t):
    for st, du, text, hi in CAPS:
        if not (st <= t < st + du):
            continue
        k = (t - st) / du
        pop = 1.0 if (t - st) > 0.16 else 0.80 + 1.25 * (t - st)
        fade = 1.0 if k < 0.88 else 1 - (k - 0.88) / 0.12
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        lines, cur = [], ""
        for w_ in text.split():
            tt = (cur + " " + w_).strip()
            if d.textlength(tt, font=CF) > W - 150 and cur:
                lines.append(cur); cur = w_
            else:
                cur = tt
        lines.append(cur)
        hiw = set(hi.split())
        yb = int(H * 0.615) - (len(lines) - 1) * 46
        for ln in lines:
            x = (W - d.textlength(ln, font=CF)) / 2
            for w_ in ln.split():
                col = CYAN if w_.strip(".,·") in hiw else (255, 255, 255)
                d.text((x, yb), w_, font=CF, fill=col + (255,), stroke_width=10, stroke_fill=(3, 3, 10, 235))
                x += d.textlength(w_ + " ", font=CF)
            yb += 92
        if pop != 1.0:
            nw, nh = int(W * pop), int(H * pop)
            c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            c.paste(lay.resize((nw, nh), Image.BICUBIC), ((W - nw) // 2, int(H * 0.615 * (1 - pop))))
            lay = c
        if fade < 1:
            lay.putalpha(lay.getchannel("A").point(lambda v: int(v * fade)))
        img.alpha_composite(lay)
        return

LOGO_F = fnt(F_BOLD, 34)
AI_F = fnt(F_MED, 22)

def draw_chrome(img, t):
    d = ImageDraw.Draw(img)
    a = int(255 * min(1, max(0, (t - 0.25) / 0.5)))
    if 7.0 < t < 11.5:                 # ott a lap sajat AXIMBRA fejlece
        a = int(a * max(0.0, 1 - min((t - 7.0) / 0.5, (11.5 - t) / 0.5, 1)))
    if a > 0:
        d.ellipse([58, 60, 78, 80], fill=CYAN + (a,))
        d.text((92, 54), "AXIMBRA", font=LOGO_F, fill=(255, 255, 255, a))
        d.text((W - 58, 62), "AI-GENERÁLT", font=AI_F, fill=(255, 255, 255, 120), anchor="ra")

# ─────────────────────────── zárókép ───────────────────────────
E_BRAND, E_URL, E_SUB, E_MONO = fnt(F_BLACK, 104), fnt(F_BOLD, 62), fnt(F_MED, 40), fnt(F_MONO, 25)
E_NOTE = fnt(F_MED, 32)

def end_card(bg, k):
    img = bg.filter(ImageFilter.GaussianBlur(26)).convert("RGBA")
    img.alpha_composite(Image.new("RGBA", (W, H), (4, 4, 12, 216)))
    d = ImageDraw.Draw(img)
    app = ease_out(min(1, k / 0.22)); al = int(255 * app)
    y = int(H * 0.36) + int((1 - app) * 40)
    d.ellipse([W // 2 - 192, y + 28, W // 2 - 160, y + 60], fill=CYAN + (al,))
    d.text((W // 2 + 22, y), "AXIMBRA", font=E_BRAND, fill=(255, 255, 255, al), anchor="ma")
    w2 = ease_out(min(1, max(0, (k - 0.14) / 0.26)))
    d.rectangle([W // 2 - int(235 * w2), y + 152, W // 2 + int(235 * w2), y + 156], fill=CYAN + (al,))
    a2 = int(255 * ease_out(min(1, max(0, (k - 0.22) / 0.25))))
    d.text((W // 2, y + 212), "aximbra.hu", font=E_URL, fill=CYAN + (a2,), anchor="ma")
    a3 = int(255 * ease_out(min(1, max(0, (k - 0.34) / 0.25))))
    d.text((W // 2, y + 312), "Próbáld ki élőben", font=E_SUB, fill=(255, 255, 255, a3), anchor="ma")
    d.text((W // 2, y + 368), "regisztráció nélkül", font=E_SUB, fill=(190, 195, 215, a3), anchor="ma")
    d.text((W // 2, H - 158), "A mintapostafiók levelei kitaláltak · az osztályozás valódi",
           font=E_MONO, fill=(150, 156, 180, a3), anchor="ma")
    d.text((W // 2, H - 118), "A videó AI-val készült", font=E_MONO, fill=(120, 126, 150, a3), anchor="ma")
    return img

# ─────────────────────────── hang ───────────────────────────
SR = 48000
def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768

def trim(a, thr=0.012):
    nz = np.nonzero(np.abs(a) > thr)[0]
    return a[max(0, nz[0] - 1500): nz[-1] + 3000] if len(nz) else a

def build_audio():
    n = int(TOTAL * SR)
    out = np.zeros(n, np.float32); duck = np.zeros(n, np.float32)
    def put(sig, t, g=1.0):
        i = int(t * SR); j = min(n, i + len(sig))
        if j > i:
            out[i:j] += sig[:j - i] * g
            duck[i:j] = 1.0
    # A horogban a klip sajat hangja szol. Igy a szajmozgas szotagra pontos,
    # mert ugyanaz a felvetel hajtja a kepet es a hangot.
    hook = load(AXI)[int(AXI_OFF * SR): int((AXI_OFF + 6.60) * SR)].copy()
    sp = hook[int(0.45 * SR): int(4.60 * SR)]
    hook_rms = float(np.sqrt((sp ** 2).mean())) or 1.0
    ref = np.concatenate([load(f) for f in ("v1T.wav", "n2T.wav", "n5T.wav")])
    ref_rms = float(np.sqrt((ref ** 2).mean())) or hook_rms
    hook *= min(1.6, ref_rms / hook_rms)
    hook[-int(0.45 * SR):] *= np.linspace(1, 0, int(0.45 * SR))
    put(hook, 0.0, 1.18)
    for f, t in [("v1T.wav", 7.70), ("v3T.wav", 10.00), ("n0T.wav", 11.90),
                 ("n1T.wav", 14.20), ("n2T.wav", 16.10), ("n3T.wav", 19.70),
                 ("n4T.wav", 22.80), ("n5T.wav", 25.80),
                 ("n6T.wav", 29.20), ("n8T.wav", 34.00), ("v8bT.wav", 37.25)]:
        put(load(f), t, 1.18)

    t = np.arange(n) / SR
    pad = np.zeros(n, np.float32)
    for f0, g in [(110.0, .50), (164.81, .34), (220.0, .20), (329.63, .09)]:
        pad += g * np.sin(2 * np.pi * f0 * t + 0.6 * np.sin(2 * np.pi * 0.07 * t))
    pad *= (0.55 + 0.45 * np.sin(2 * np.pi * 0.055 * t - 1.2))
    beat = 1.2
    sub = np.sin(2 * np.pi * 52 * t) * np.exp(-((t % beat) / beat) * 14) * (t > 6.9)
    rng = np.random.default_rng(3)
    tick = rng.standard_normal(n).astype(np.float32) * np.exp(-((t % (beat / 2)) / (beat / 2)) * 90) * 0.5 * (t > 11)
    for i in range(1, 6):
        tick[i:] = tick[i:] * .55 + tick[:-i] * .45
    music = pad * 0.055 + sub * 0.075 + tick * 0.030

    for ct, up in [(B_END - 0.55, True), (C_END - 0.30, True)]:
        L = int(0.75 * SR); tt = np.arange(L) / SR
        nz = rng.standard_normal(L).astype(np.float32)
        for i in range(1, 9):
            nz[i:] = nz[i:] * .6 + nz[:-i] * .4
        sh = (tt / tt[-1]) ** 2 if up else (1 - tt / tt[-1]) ** 2
        s = nz * sh * np.sin(2 * np.pi * (300 + 1500 * tt / tt[-1]) * tt) * 0.9
        i0 = int(ct * SR); j = min(n, i0 + L); music[i0:j] += s[:j - i0] * 0.34
    L = int(1.1 * SR); tt = np.arange(L) / SR
    ding = (np.sin(2 * np.pi * 1320 * tt) + 0.5 * np.sin(2 * np.pi * 1980 * tt)) * np.exp(-tt * 7)
    for dt in (7.45, 22.52):
        i0 = int(dt * SR); music[i0:i0 + L] += ding[: n - i0] * 0.09

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
    open("mix.raw", "wb").write((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())

build_audio(); print("hang kesz", flush=True)

# ─────────────────────────── renderelés ───────────────────────────
ff = subprocess.Popen(
    ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
     "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "mix.raw",
     "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", OUT], stdin=subprocess.PIPE)

last = None
for i in range(N):
    t = i / FPS
    if t < B_END:
        if t < A_END:
            e = ease_out(t / A_END)
            z, ccx, ccy = 1.0 + 0.055 * e, W / 2, H / 2 - 40 * e
        else:
            k = ease_in((t - A_END) / (B_END - A_END))
            qx, qy = (smooth_q.mean(0) if smooth_q is not None else (904, 926))
            z = 1.055 + (4.30 - 1.055) * k
            ccx = W / 2 + (qx - W / 2) * k
            ccy = (H / 2 - 40) + (qy - (H / 2 - 40)) * k
        img = axi_frame(t + AXI_OFF, z, ccx, ccy, phone_content(t)).convert("RGBA")
    elif t < C_END:
        if t >= INS0:
            im0, _z, _x, _y = page_frame(INS0 - 0.05)
            img = insert_frame(t, im0)
        else:
            im0, z, x0, y0 = page_frame(t)
            img = im0.convert("RGBA")
            draw_boxes(img, t, z, x0, y0)
            draw_tap(img, t, z, x0, y0)
        if t >= C_END - 0.12:          # a zarokep hattere a bemutato utolso kepe
            last = img.copy()
    elif t < D_END:                                  # rovid zaro beallitas, beszed nelkul
        e = ease_out((t - C_END) / (D_END - C_END))
        img = axi_frame(min(8.25 + (t - C_END) * 1.05, 9.90), 1.38 - 0.30 * e,
                        540 - 20 * e, 760 + 180 * e, page_view(300), clip=axi_end).convert("RGBA")
        last = img
    else:
        k = (t - D_END) / (TOTAL - D_END)
        base = last if last is not None else Image.new("RGBA", (W, H), (4, 4, 12, 255))
        zz = 1.0 + 0.06 * k
        cw, ch = int(W / zz), int(H / zz)
        img = end_card(base.crop(((W - cw) // 2, (H - ch) // 2, (W - cw) // 2 + cw, (H - ch) // 2 + ch))
                       .resize((W, H), Image.BICUBIC), k)

    if t < D_END:
        draw_caption(img, t)
        draw_chrome(img, t)
    if t > TOTAL - 0.6:
        img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)), (t - (TOTAL - 0.6)) / 0.6)
    ff.stdin.write(img.convert("RGB").tobytes())
    if i % 120 == 0:
        print(f"{i}/{N}", flush=True)

ff.stdin.close(); ff.wait()
print("kesz", OUT)

"""Személyes adatok elmosása feltöltött képen és képernyőfelvételen.

Egy képernyőfelvételen (pl. egy postafiók, ahogy az agent rendezi) nevek,
e-mail-címek, telefonszámok látszanak. Ezek nem kerülhetnek ki egy nyilvános
posztba, ezért a feltöltött anyagot a médiatárba kerülés előtt kitakarjuk:

1. A felvételből másodpercenként SAMPLE_FPS képkockát veszünk, és a Tesseract
   minden szövegsort megtalál rajta, a helyével együtt.
2. Az e-mail-cím és a telefonszám szabállyal megy; hogy egy sor név-e (ember
   vagy cég), azt a modell dönti el a sorok szövegéből. Kétség esetén takarunk.
3. MINDEN képkockán pixelezzük ezeket a sorokat. Két minta között a sort
   követjük: ugyanaz a szöveg a következő mintán máshol van (görgetés), a
   kettő között a helyét arányosan számoljuk. Ami csak az egyik mintán
   látszik, azt a görgetés irányában visszafelé/előre toljuk.

Az eredeti fájl nem marad meg: a médiatárba csak az elmosott változat kerül.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

SAMPLE_FPS = 3
PAD = 8               # px: a felismert sor köré ennyivel nagyobb takarás
PIXEL = 14            # px: ekkora „kockákra" esik szét a takart rész
MATCH_RATIO = 0.82    # ennyire hasonló szöveg ugyanaz a sor a következő mintán
# Ami ezeket tartalmazza, az látszik (a saját fiók és márka); minden más
# tartalom elmosódik. Pl. a Google fiókválasztóban csak az aximbra-s fiók.
KEEP_TERMS = tuple(t.strip().lower() for t in os.environ.get("REDACT_KEEP", "aximbra,episteme").split(",") if t.strip())
# Az elmosási szabály változata: ha szigorodik, a korábban feldolgozott
# felvételeket újra átnézzük (media.resume_pending).
POLICY_VERSION = 3  # 3: a halványszürke szöveget is olvassuk (négy OCR-változat)

EMAIL_RE = re.compile(r"[\w.+-]+\s?@\s?[\w-]+(?:\.[\w-]+)+", re.I)
PHONE_RE = re.compile(r"(?:\+|00)?\d[\d\s/().-]{7,}\d")
AT_RE = re.compile(r"@|\bgmail\b|\bfreemail\b|\bcitromail\b", re.I)


class RedactError(RuntimeError):
    pass


def _ffmpeg() -> str:
    exe = os.environ.get("FFMPEG_PATH")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def available() -> bool:
    """Van-e szövegfelismerő a gépen (a Dockerfile telepíti)."""
    try:
        return subprocess.run(["tesseract", "--version"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---- 1. szövegsorok egy képen ------------------------------------------------

def ocr_lines(png_path: str) -> list[dict]:
    """A kép szövegsorai: [{"text", "box": [x0, y0, x1, y1]}].

    Egy menet nem elég: sötét felületen a Tesseract a megfordított képet olvassa
    jobban, a halványszürke másodlagos szöveget (pl. egy levél összefoglalója)
    pedig csak kontrasztnövelés után látja — élesben egy név így maradt kint.
    Ezért négy változatot olvasunk, és a sorokat összefésüljük."""
    from PIL import Image, ImageOps

    img = Image.open(png_path).convert("L")
    w, h = img.size
    scale = 2 if w < 700 else 1    # a kis képet nagyítva jobban olvassa; 720 px-en már nem kell
    big = img.resize((w * scale, h * scale), Image.LANCZOS) if scale > 1 else img
    hist = big.histogram()
    half, acc, bg = (big.size[0] * big.size[1]) / 2, 0, 0
    for v, n in enumerate(hist):
        acc += n
        if acc >= half:
            bg = v
            break
    dark = bg < 128
    # Küszöbölés a háttérhez képest: ami attól eltér, az fekete betű fehér alapon.
    binar = big.point(lambda v: 0 if (v > bg + 25 if dark else v < bg - 25) else 255)
    eq = ImageOps.equalize(big)
    variants = (big, ImageOps.invert(big), binar, ImageOps.invert(eq) if dark else eq)
    lines: list[dict] = []
    with tempfile.TemporaryDirectory() as d:
        for i, variant in enumerate(variants):
            p = os.path.join(d, f"v{i}.png")
            variant.save(p)
            # Egy szálon: a felvétel kockáit párhuzamosan olvassuk, és ha mindegyik
            # Tesseract az összes magot akarná, egymást fojtanák meg.
            r = subprocess.run(["tesseract", p, "stdout", "-l", "hun+eng", "--psm", "11", "tsv"],
                               capture_output=True, timeout=180, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
            if r.returncode != 0:
                continue
            lines += _tsv_lines(r.stdout.decode("utf-8", "replace"), scale)
    return _dedupe(lines)


def _tsv_lines(tsv: str, scale: int) -> list[dict]:
    groups: dict = {}
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5":
            continue
        text = c[11].strip()
        try:
            conf = float(c[10])
        except ValueError:
            conf = -1
        if not text or conf < 30:
            continue
        x, y, ww, hh = (int(v) for v in c[6:10])
        key = (c[2], c[3], c[4])  # blokk, bekezdés, sor
        g = groups.setdefault(key, {"words": [], "box": [x, y, x + ww, y + hh]})
        g["words"].append(text)
        b = g["box"]
        g["box"] = [min(b[0], x), min(b[1], y), max(b[2], x + ww), max(b[3], y + hh)]
    return [{"text": " ".join(g["words"]), "box": [v // scale for v in g["box"]]} for g in groups.values()]


def _overlap(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return inter / small


def _dedupe(lines: list[dict]) -> list[dict]:
    out: list[dict] = []
    for ln in sorted(lines, key=lambda l: -len(l["text"])):
        if any(_overlap(ln["box"], o["box"]) > 0.6 for o in out):
            continue
        out.append(ln)
    return out


# ---- 2. melyik sor személyes adat -------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def rule_sensitive(text: str) -> bool:
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text) or AT_RE.search(text))


CLASSIFY_PROMPT = """Below are text lines read from a screen recording of an app (for example a Google sign-in or
account chooser, Gmail, or an email-sorting agent showing its results). The recording will be posted publicly.
Decide for every line whether it is INTERFACE text or CONTENT.
INTERFACE — keep it readable: app and product names, page headings, buttons, menu items, field labels, category
tags, status words, counters, dates and times on their own, and generic system messages or warnings (Google's
sign-in, consent and "unverified app" screens are interface).
CONTENT — blur it: anything that comes from a mailbox or an account: account names and addresses in an account
chooser, senders, recipients, names of people or companies, email addresses, subjects, message previews, email
text, summaries and suggested next steps written about an email, suggested replies, phone numbers, street
addresses, order, invoice or account numbers.
Lines that mention AXIMBRA or EPISTEME are kept, the rest of the content is blurred. When unsure, blur.

LINES (id: text):
{lines}

Answer ONLY with JSON: {{"blur": [ids of the lines to blur]}}"""


def _kept(n: str) -> bool:
    return any(k in n for k in KEEP_TERMS)


def _looks_like_content(text: str) -> bool:
    """Modell nélküli tartalék: a felület feliratai rövidek (gomb, címke,
    fejléc); ami hosszabb, számot vagy @-ot tartalmaz, vagy névnek látszik,
    az tartalom."""
    words = text.split()
    return (len(words) > 3 or bool(re.search(r"\d|@", text))
            or bool(re.search(r"\b[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+", text)))


def classify(texts: list[str]) -> set[str]:
    """A takarandó sorok normalizált szövege. Szigorú szabály: a felület
    feliratai maradnak, minden tartalom (küldő, tárgy, levélszöveg, fiók)
    elmosódik; ami a saját fiókot/márkát (KEEP_TERMS) tartalmazza, az látszik.
    E-mail-cím és telefonszám szabállyal megy; a többit a modell dönti el, és
    ha nem érhető el, minden hosszabb vagy névszerű sort elmosunk."""
    originals: dict = {}
    for t in texts:
        n = _norm(t)
        if n and n not in originals:
            originals[n] = t
    hit = {n for n in originals if rule_sensitive(n)}
    rest = [n for n in originals if n not in hit and len(n) >= 2 and not _kept(n)]
    if rest:
        try:
            import llm
            listing = "\n".join(f"{i}: {t[:90]}" for i, t in enumerate(rest[:800]))
            data = llm.extract_json(llm._ask(CLASSIFY_PROMPT.format(lines=listing)))
            ids = (data.get("blur") or data.get("ids")) if isinstance(data, dict) else data
            for i in ids or []:
                try:
                    hit.add(rest[int(i)])
                except (ValueError, TypeError, IndexError):
                    continue
            # Ami a modell válaszlistáján túl volt (800 sor fölött), azt a tartalék szabály dönti el.
            hit |= {n for n in rest[800:] if _looks_like_content(originals[n])}
        except Exception as e:  # noqa: BLE001 — modell nélkül óvatosabban takarunk
            logger.warning("tartalom-felismerés modell nélkül: %s", e)
            hit |= {n for n in rest if _looks_like_content(originals[n])}
    return {n for n in hit if not _kept(n)}


# ---- 3. követés két minta között ---------------------------------------------

def _similar(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= MATCH_RATIO


def plan(samples: list[dict], sensitive: set[str], dt: float) -> list[dict]:
    """Takarási terv: minden mintaközre a sorok kezdő és záró helye.
    samples: [{"t", "lines": [{"text", "box"}]}] időrendben.
    Visszaad: [{"t0", "t1", "boxes": [(box_at_t0, box_at_t1)]}]."""
    marked = [{"t": s["t"], "lines": [l for l in s["lines"] if _norm(l["text"]) in sensitive]} for s in samples]
    out = []
    for i, cur in enumerate(marked):
        nxt = marked[i + 1] if i + 1 < len(marked) else None
        t0, t1 = cur["t"], (nxt["t"] if nxt else cur["t"] + dt)
        pairs, used, dys = [], set(), []
        if nxt:
            for a in cur["lines"]:
                for j, b in enumerate(nxt["lines"]):
                    if j not in used and _similar(_norm(a["text"]), _norm(b["text"])):
                        used.add(j)
                        pairs.append((a["box"], b["box"]))
                        dys.append(b["box"][1] - a["box"][1])
                        break
        # A görgetés iránya és mértéke ebben a mintaközben (a párosított sorokból).
        dy = sorted(dys)[len(dys) // 2] if dys else 0
        matched_a = {tuple(p[0]) for p in pairs}
        for a in cur["lines"]:
            if tuple(a["box"]) not in matched_a:            # eltűnik: tovább gördül
                pairs.append((a["box"], _shift(a["box"], dy)))
        for j, b in enumerate(nxt["lines"] if nxt else []):
            if j not in used:                                 # most jön be: visszafelé
                pairs.append((_shift(b["box"], -dy), b["box"]))
        # A görgetés nem egyenletes (elindul, lassul, megáll): a két minta közti
        # helyet csak becsüljük. A takarás ezért a mozgás felével magasabb,
        # állóképen pedig nem nő.
        grow = abs(dy) / 2
        pairs = [(_grow(a, grow), _grow(b, grow)) for a, b in pairs]
        out.append({"t0": t0, "t1": t1, "boxes": pairs})
    # Az első minta előtti rész (a felvétel eleje) is takarva legyen.
    if out:
        first = out[0]
        out.insert(0, {"t0": max(0.0, first["t0"] - dt), "t1": first["t0"],
                       "boxes": [(p[0], p[0]) for p in first["boxes"]]})
    return out


def _grow(box, g):
    return [box[0], box[1] - g, box[2], box[3] + g]


def _shift(box, dy):
    return [box[0], box[1] + dy, box[2], box[3] + dy]


def boxes_at(plan_: list[dict], t: float) -> list[list[int]]:
    """A t időpontban takarandó téglalapok (a két szomszédos mintaközé is)."""
    out = []
    for seg in plan_:
        if seg["t0"] - 1e-6 <= t <= seg["t1"] + 1e-6:
            span = (seg["t1"] - seg["t0"]) or 1.0
            k = min(1.0, max(0.0, (t - seg["t0"]) / span))
            for a, b in seg["boxes"]:
                out.append([round(a[n] + (b[n] - a[n]) * k) for n in range(4)])
    return out


# ---- 4. a takarás rárajzolása --------------------------------------------------

def pixelate(img, boxes: list[list[int]]):
    """A téglalapok pixelezése (visszafordíthatatlan: a kockákból a szöveg nem áll vissza)."""
    from PIL import Image

    w, h = img.size
    for b in boxes:
        x0, y0 = max(0, b[0] - PAD), max(0, b[1] - PAD)
        x1, y1 = min(w, b[2] + PAD), min(h, b[3] + PAD)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        reg = img.crop((x0, y0, x1, y1))
        small = reg.resize((max(1, (x1 - x0) // PIXEL), max(1, (y1 - y0) // PIXEL)), Image.BILINEAR)
        img.paste(small.resize(reg.size, Image.NEAREST), (x0, y0))
    return img


def redact_image(path: str) -> int:
    """Egy kép takarása helyben. Visszaadja, hány sort takart ki."""
    from PIL import Image

    lines = ocr_lines(path)
    sens = classify([l["text"] for l in lines])
    boxes = [l["box"] for l in lines if _norm(l["text"]) in sens]
    if boxes:
        img = Image.open(path).convert("RGB")
        pixelate(img, boxes).save(path, quality=92)
    return len(boxes)


def _probe(path: str) -> tuple[int, int, float]:
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, timeout=60)
    text = r.stderr.decode(errors="replace")
    m = re.search(r",\s(\d{2,5})x(\d{2,5})[\s,]", text)
    d = re.search(r"Duration:\s(\d+):(\d+):(\d+\.?\d*)", text)
    f = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    if not m:
        raise RedactError("a felvétel méretét nem sikerült kiolvasni")
    secs = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else 0.0
    return int(m.group(1)), int(m.group(2)), float(f.group(1)) if f else 30.0


def redact_clip(path: str, say=lambda m: None) -> int:
    """Egy (néma, WebM) klip takarása helyben. Visszaadja a takart sorok számát
    (különböző szövegek). Hiba esetén RedactError: a hívó ilyenkor nem engedheti
    a klipet videóba, mert nem tudjuk, mi maradt rajta."""
    from PIL import Image

    if not available():
        raise RedactError("nincs szövegfelismerő a gépen")
    w, h, fps = _probe(path)
    fps = fps or 30.0
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                            "-vf", f"fps={SAMPLE_FPS}", os.path.join(d, "s%05d.png")], capture_output=True, timeout=900)
        if r.returncode != 0:
            raise RedactError("a felvételből nem sikerült képkockát venni")
        names = sorted(n for n in os.listdir(d) if n.startswith("s"))
        say(f"Személyes adatok keresése: {len(names)} képkocka…")
        # A Tesseract külön folyamat: a magokon párhuzamosan futtatjuk, így egy
        # kétperces felvétel sem tart tovább néhány percnél.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1, min(6, os.cpu_count() or 2))) as ex:
            found = list(ex.map(lambda n: ocr_lines(os.path.join(d, n)), names))
        # Az fps szűrő az i-edik kockát az i/SAMPLE_FPS időpont köré teszi.
        samples = [{"t": (i + 0.5) / SAMPLE_FPS, "lines": lines} for i, lines in enumerate(found)]
        sensitive = classify([l["text"] for s in samples for l in s["lines"]])
        steps = plan(samples, sensitive, 1.0 / SAMPLE_FPS)
        say(f"Elmosás: {len(sensitive)} különböző név/e-mail/szám…")
        # A kész fájl a végleges mellé készül (ugyanarra a kötetre): a /tmp és a
        # /data külön lemez, a kettő között az átnevezés nem megy — élesben egy
        # kész elmosás ezen hasalt el ("Invalid cross-device link").
        out = path + ".redacting.webm"
        dec = subprocess.Popen([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", path,
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        enc = subprocess.Popen([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
                                "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "36", "-deadline", "realtime",
                                "-cpu-used", "8", "-row-mt", "1", out], stdin=subprocess.PIPE)
        size, k = w * h * 3, 0
        try:
            while True:
                buf = dec.stdout.read(size)
                if len(buf) < size:
                    break
                boxes = boxes_at(steps, k / fps)
                if boxes:
                    img = pixelate(Image.frombytes("RGB", (w, h), buf), boxes)
                    buf = img.tobytes()
                enc.stdin.write(buf)
                k += 1
        finally:
            enc.stdin.close()
            dec.stdout.close()
            dec.wait(timeout=60)
            enc.wait(timeout=900)
        if enc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0 or k == 0:
            try:
                os.remove(out)
            except OSError:
                pass
            raise RedactError("az elmosott felvételt nem sikerült elkészíteni")
        os.replace(out, path)
    return len(sensitive)

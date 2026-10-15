"""A rendező: a feltöltött elemekből jelenetterv — mi, meddig, hogyan.

Szándékosan nincs benne nyelvi modell. Az előző agent minden gyártásnál a
Gemini ingyenes keretére támaszkodott, és ha az elfogyott, nem lett videó.
Ez a rendező a te utasításaidból és a fájlok tulajdonságaiból dolgozik, tehát
mindig lefut, kulcs és költség nélkül. (A szövegíró modell később ráépíthető:
csak a `text` és a sorrend mezőket kell felülírnia.)

A vágás ütemre megy: egy ütem BEAT másodperc, és a jelenethosszak egy ismétlődő
mintát követnek (rövid-rövid-hosszú), ettől lesz TikTok-érzete. Fotónál
ráközelítés vagy -húzás, klipnél a legjobb pillanat.
"""
from __future__ import annotations

import re
import unicodedata

# Egy jelenet ennél rövidebb ne legyen (nem látszik), és ennél hosszabb se
# (unalmas lesz egy montázsban).
MIN_SCENE = 0.38
MAX_SCENE = 2.2
# A jelenethosszak szorzói, körbe-körbe: ettől lesz ritmusa a vágásnak.
RHYTHM = (1.0, 0.72, 1.0, 1.32, 0.72, 1.0, 0.86, 1.46)
FLASH_EVERY = 5          # ennyi vágásonként egy villanás
FADE_EVERY = 7           # ennyi vágásonként egy áttűnés
FADE_SECONDS = 0.28
FLASH_SECONDS = 0.07
EFFECTS = ("punch_in", "punch_out", "pan_right", "punch_in", "pan_left", "punch_in")

ASPECTS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}


def _fold(s: str) -> str:
    """Ékezet nélküli kisbetűs alak — hogy a „nyitókép" és a „nyitokep" is menjen."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# „írd rá: …", „felirat: …", „text: …" — a kettőspont utáni rész a felirat.
# Ékezettel és anélkül is: „írd rá:", „ird ra:", „felirat:", „text:".
TEXT_RE = re.compile(r"(?:[ií]rd\s*r[aá]|felirat|sz[öo]veg|text|caption)\s*[:\-]\s*(.+)", re.I)
# „a 3. mp-től", „3 mp-tol", „from 3s", „0:12-től"
FROM_RE = re.compile(r"(?:(\d+):(\d{1,2})|(\d+(?:[.,]\d+)?)\s*(?:\.?\s*)?(?:mp|s|sec|masodperc))"
                     r"\s*(?:-?t[oó]l|-?t[oő]l|from|kezdve|$)", re.I)
FROM_EN_RE = re.compile(r"from\s+(\d+(?:[.,]\d+)?)\s*s", re.I)


def read_note(note: str) -> dict:
    """Egy elem utasításának értelmezése. Amit nem ért, azt békén hagyja."""
    raw = (note or "").strip()
    f = _fold(raw)
    out: dict = {"first": False, "last": False, "skip": False, "start": None, "text": "",
                 "hold": False}
    if any(w in f for w in ("nyitokep", "nyito kep", "nyitokocka", "legyen az elso",
                            "elso legyen", "opening", "first shot", "first frame")):
        out["first"] = True
    if any(w in f for w in ("zarokep", "zaro kep", "utolso legyen", "legyen az utolso",
                            "closing", "last shot", "vegere")):
        out["last"] = True
    if any(w in f for w in ("ne hasznald", "kihagy", "hagyd ki", "skip", "ne kerüljon",
                            "ne kerüljon bele", "ne kerujon")):
        out["skip"] = True
    if any(w in f for w in ("hosszabban", "tovabb lassodjon", "maradjon tovabb", "hold",
                            "lassabban")):
        out["hold"] = True
    m = TEXT_RE.search(raw)
    if m:
        out["text"] = m.group(1).strip().strip('"„”')[:120]
    m = FROM_RE.search(f) or FROM_EN_RE.search(f)
    if m:
        g = m.groups()
        if len(g) >= 2 and g[0] and g[1]:
            out["start"] = int(g[0]) * 60 + int(g[1])
        else:
            num = next((x for x in g if x), None)
            if num:
                try:
                    out["start"] = float(str(num).replace(",", "."))
                except ValueError:
                    pass
    return out


def _interleave(a: list[dict], b: list[dict]) -> list[dict]:
    """Két lista egyenletesen összefésülve — hogy a klipek ne egy kupacban
    legyenek a végén, hanem végig keveredjenek a fotók közé."""
    if not a:
        return list(b)
    if not b:
        return list(a)
    long_, short = (a, b) if len(a) >= len(b) else (b, a)
    step = len(long_) / (len(short) + 1)
    out = list(long_)
    for i, item in enumerate(short):
        out.insert(min(len(out), int(round(step * (i + 1))) + i), item)
    return out


def order(items: list[dict]) -> list[dict]:
    """Sorrend: amit nyitónak kértél, elöl; amit zárónak, hátul; közte a fotók
    és a klipek egyenletesen keverve (a feltöltés sorrendjében haladva)."""
    live = [m for m in items if not read_note(m.get("note", ""))["skip"]]
    live = sorted(live, key=lambda m: m.get("created_at", ""))
    first = [m for m in live if read_note(m.get("note", ""))["first"]]
    rest = [m for m in live if m not in first]
    last = [m for m in rest if read_note(m.get("note", ""))["last"]]
    mid = [m for m in rest if m not in last]
    photos = [m for m in mid if m.get("kind") != "clip"]
    clips = [m for m in mid if m.get("kind") == "clip"]
    return first + _interleave(photos, clips) + last


def _lengths(n: int, target: float) -> list[float]:
    """Jelenethosszak: a célhossz elosztva, de ritmussal és korlátok közt."""
    if n <= 0:
        return []
    base = max(MIN_SCENE, min(MAX_SCENE, target / n))
    raw = [base * RHYTHM[i % len(RHYTHM)] for i in range(n)]
    raw = [max(MIN_SCENE, min(MAX_SCENE, x)) for x in raw]
    # A ritmus ne vigye el a teljes hosszt: arányosan visszahúzzuk a célra,
    # amennyire a korlátok engedik.
    total = sum(raw)
    want = max(n * MIN_SCENE, min(n * MAX_SCENE, target))
    k = want / total if total else 1.0
    return [round(max(MIN_SCENE, min(MAX_SCENE, x * k)), 3) for x in raw]


def best_window(m: dict, want: float, asked_start: float | None) -> float:
    """Honnan vágjunk ki egy klipből. Ha mondtál kezdetet, az számít; egyébként
    a mozgalmas rész, amit a tár az elemzéskor megjelölt (`hot`), és ha az
    sincs, akkor az első harmad után — egy felvétel eleje általában üres."""
    dur = float(m.get("seconds") or 0)
    if dur <= 0:
        return 0.0
    if asked_start is not None:
        return max(0.0, min(asked_start, max(0.0, dur - want)))
    hot = m.get("hot")
    if isinstance(hot, (int, float)) and 0 <= hot <= dur:
        return max(0.0, min(float(hot), max(0.0, dur - want)))
    return min(dur * 0.3, max(0.0, dur - want))


def plan(items: list[dict], seconds: float = 25.0, aspect: str = "9:16",
         title: str = "", lang: str = "hu") -> dict:
    """A teljes terv: jelenetek, effektek, átmenetek, feliratok."""
    if aspect not in ASPECTS:
        aspect = "9:16"
    chosen = order(items)
    if not chosen:
        raise ValueError("nincs használható elem")
    lens = _lengths(len(chosen), float(seconds))
    scenes = []
    cuts = 0
    for i, (m, want) in enumerate(zip(chosen, lens)):
        note = read_note(m.get("note", ""))
        if note["hold"]:
            want = min(MAX_SCENE, want * 1.6)
        is_clip = m.get("kind") == "clip"
        if is_clip:
            # Egy jelenet nem lehet hosszabb magánál a klipnél: különben az
            # ffmpeg a végén elfogyna, és a jelenet rövidebb lenne a tervezettnél.
            dur = float(m.get("seconds") or 0)
            if dur > 0:
                want = min(want, dur)
        # Az utolsó jelenet után nincs átmenet.
        last_one = i == len(chosen) - 1
        trans = "cut"
        if not last_one:
            cuts += 1
            if cuts % FADE_EVERY == 0:
                trans = "fade"
            elif cuts % FLASH_EVERY == 0:
                trans = "flash"
        scenes.append({
            "id": m["id"],
            "kind": m.get("kind"),
            "name": m.get("name", ""),
            "seconds": round(want, 3),
            "start": round(best_window(m, want, note["start"]), 3) if is_clip else 0.0,
            "source_seconds": m.get("seconds"),
            # Klipnél nem erőltetünk ráközelítést: már van benne mozgás.
            "effect": "none" if is_clip else EFFECTS[i % len(EFFECTS)],
            "text": note["text"] or (title if i == 0 and title else ""),
            "transition": trans,
        })
    w, h = ASPECTS[aspect]
    total = sum(s["seconds"] for s in scenes) \
        + sum(FLASH_SECONDS for s in scenes if s["transition"] == "flash")
    return {"aspect": aspect, "width": w, "height": h, "lang": lang, "title": title[:120],
            "scenes": scenes, "seconds": round(total, 2),
            "fade_seconds": FADE_SECONDS, "flash_seconds": FLASH_SECONDS}

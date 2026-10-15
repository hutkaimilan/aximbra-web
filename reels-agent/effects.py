"""Az effekt-készlet: minden, amit a rendező kérhet, és amit az ffmpeg tud.

Ez a fájl egyetlen helyen mondja meg, mi létezik. A rendező (a modell) csak
innen választhat, a renderelő pedig csak ezt tudja végrehajtani — így a modell
nem tud olyat kérni, ami elhasal, és új effektet elég egy helyen felvenni.

A szűrőláncok a 9:16-os (vagy más arányú) keretre már ráskálázott, levágott
képre épülnek; a `w`/`h` a kimeneti méret, a `d` a jelenet hossza.
"""
from __future__ import annotations

FPS = 30

# ---- mozgás a képen --------------------------------------------------------
# Állóképnél ettől lesz élet a kockában; klipnél általában "none", mert
# már van benne mozgás.
MOTIONS = ("none", "punch_in", "punch_out", "pan_left", "pan_right", "pan_up", "pan_down",
           "ken_burns", "zoom_pulse", "shake", "rotate_in", "drift_in")

# ---- színezés és képi hatás ------------------------------------------------
LOOKS = ("none", "bw", "sepia", "vivid", "moody", "warm", "cool", "vhs", "grain",
         "vignette", "rgb_split", "glitch", "blur_in", "sharp", "mirror", "flip",
         "neon", "faded", "contrast_pop")

# ---- átmenetek -------------------------------------------------------------
# A "cut" és a "flash"/"blackout" a sajátunk; a többit az ffmpeg xfade adja,
# és pont ezek a TikTokon látható csúsztatások, törlések, kinyílások.
OWN_TRANSITIONS = ("cut", "flash", "blackout")
XFADE = (
    "fade", "fadeblack", "fadewhite", "fadegrays", "fadefast", "fadeslow", "dissolve",
    "distance", "pixelize", "radial",
    "wipeleft", "wiperight", "wipeup", "wipedown", "wipetl", "wipetr", "wipebl", "wipebr",
    "slideleft", "slideright", "slideup", "slidedown",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circlecrop", "rectcrop", "circleopen", "circleclose",
    "vertopen", "vertclose", "horzopen", "horzclose",
    "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice",
    "hlwind", "hrwind", "vuwind", "vdwind",
    "squeezeh", "squeezev", "zoomin", "hblur",
    "coverleft", "coverright", "coverup", "coverdown",
    "revealleft", "revealright", "revealup", "revealdown",
)
TRANSITIONS = OWN_TRANSITIONS + XFADE

# ---- felirat ---------------------------------------------------------------
TEXT_POSITIONS = ("top", "middle", "lower", "bottom")
TEXT_STYLES = ("outline", "box", "bar", "caption")
TEXT_ANIMS = ("none", "fade", "pop", "slide_up", "shake")


def is_motion(x: str) -> bool:
    return x in MOTIONS


def is_look(x: str) -> bool:
    return x in LOOKS


def is_transition(x: str) -> bool:
    return x in TRANSITIONS


def motion_filter(motion: str, d: float, w: int, h: int) -> str:
    """Mozgás-szűrő egy állóképhez. A bemenet már 2x méretű, hogy a zoompan
    ne lépcsőzzön; a kimenet w×h."""
    n = max(2, int(round(d * FPS)))
    mid = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "punch_in":
        z, x, y = f"min(1.0+{0.14 / n:.6f}*on,1.14)", *mid
    elif motion == "punch_out":
        z, x, y = f"max(1.16-{0.16 / n:.6f}*on,1.0)", *mid
    elif motion == "ken_burns":
        z, x, y = f"min(1.0+{0.18 / n:.6f}*on,1.18)", f"(iw-iw/zoom)*on/{n}", f"(ih-ih/zoom)*on/{n}"
    elif motion == "pan_left":
        z, x, y = "1.12", f"(iw-iw/zoom)*(1-on/{n})", mid[1]
    elif motion == "pan_right":
        z, x, y = "1.12", f"(iw-iw/zoom)*on/{n}", mid[1]
    elif motion == "pan_up":
        z, x, y = "1.12", mid[0], f"(ih-ih/zoom)*(1-on/{n})"
    elif motion == "pan_down":
        z, x, y = "1.12", mid[0], f"(ih-ih/zoom)*on/{n}"
    elif motion == "zoom_pulse":
        # Lüktet, mintha ütemre pattanna.
        z, x, y = f"1.06+0.06*sin(on/{max(1, n // 3)})", *mid
    elif motion == "shake":
        z = "1.10"
        x = f"iw/2-(iw/zoom/2)+{int(w * 0.012)}*sin(on/1.7)"
        y = f"ih/2-(ih/zoom/2)+{int(h * 0.010)}*cos(on/2.3)"
    elif motion == "drift_in":
        z, x, y = f"min(1.02+{0.08 / n:.6f}*on,1.10)", f"(iw-iw/zoom)*0.5+{int(w * 0.05)}*(1-on/{n})", mid[1]
    elif motion == "rotate_in":
        # A forgatás nem a zoompan dolga: utána jön, lentebb.
        z, x, y = "1.18", *mid
    else:
        return ""
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={FPS}"


def after_motion(motion: str, d: float) -> str:
    """Ami a zoompan után kell (pl. a lassú bedőlés)."""
    if motion == "rotate_in":
        return f"rotate='(-0.05+0.05*t/{max(0.1, d):.3f})':c=none:ow=iw:oh=ih"
    return ""


def look_filter(look: str, d: float, w: int, h: int) -> str:
    """Színezés és képi hatás. Minden ág yuv420p-vel kompatibilis maradjon."""
    if look == "bw":
        return "hue=s=0,eq=contrast=1.12"
    if look == "sepia":
        return "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"
    if look == "vivid":
        return "eq=saturation=1.45:contrast=1.14:brightness=0.02"
    if look == "moody":
        return "eq=saturation=0.72:contrast=1.22:brightness=-0.05,colorbalance=rs=-0.06:bs=0.10"
    if look == "warm":
        return "colorbalance=rs=0.10:gs=0.03:bs=-0.08,eq=saturation=1.1"
    if look == "cool":
        return "colorbalance=rs=-0.08:bs=0.12,eq=saturation=1.05"
    if look == "neon":
        return "eq=saturation=1.8:contrast=1.25,colorbalance=rm=0.08:bm=0.12"
    if look == "faded":
        return "eq=saturation=0.8:contrast=0.9:brightness=0.06,curves=all='0/0.08 1/0.94'"
    if look == "contrast_pop":
        return "eq=contrast=1.35:saturation=1.2,unsharp=5:5:0.8"
    if look == "vhs":
        # Színcsúszás + zaj + enyhe vízszintes elkenés: a kazettás hatás.
        return ("colorchannelmixer=1.05:0:0:0:0:1:0:0:0:0:1.05,noise=alls=14:allf=t+u,"
                "eq=saturation=1.25:contrast=1.1")
    if look == "grain":
        return "noise=alls=10:allf=t"
    if look == "vignette":
        return "vignette=PI/4"
    if look == "sharp":
        return "unsharp=5:5:1.0:5:5:0.0"
    if look == "mirror":
        return "hflip"
    if look == "flip":
        return "vflip"
    if look == "blur_in":
        # Életlenül indul, és kitisztul. A gblur sigma-ja nem vesz be
        # időfüggő kifejezést, ezért két lépcsőben kapcsoljuk be-ki.
        t1 = max(0.08, d * 0.18)
        t2 = max(t1 + 0.08, d * 0.38)
        return (f"gblur=sigma=14:steps=2:enable='lt(t,{t1:.3f})',"
                f"gblur=sigma=5:steps=2:enable='between(t,{t1:.3f},{t2:.3f})'")
    if look == "rgb_split":
        # A piros és a kék csatorna elcsúszik — az "anaglif" hatás.
        off = max(3, int(w * 0.006))
        return (f"split=3[r][g][b];[r]lutrgb=g=0:b=0,crop=iw-{off}:ih:{off}:0,pad=iw+{off}:ih:0:0[r2];"
                f"[g]lutrgb=r=0:b=0[g2];[b]lutrgb=r=0:g=0,crop=iw-{off}:ih:0:0,pad=iw+{off}:ih:{off}:0[b2];"
                f"[r2][g2]blend=all_mode=addition[rg];[rg][b2]blend=all_mode=addition")
    if look == "glitch":
        # Erős zaj + színcsúszás + apró vízszintes szakadás.
        off = max(4, int(w * 0.010))
        return (f"split=2[a][bb];[bb]crop=iw:ih/8:0:ih/3,pad=iw:ih:{off}:ih/3:black@0[s];"
                f"[a][s]overlay=0:0:enable='lt(mod(t\\,0.5)\\,0.08)',"
                f"noise=alls=22:allf=t+u,eq=saturation=1.3")
    return ""


def needs_complex(look: str) -> bool:
    """Ezek a hatások több ágat használnak, ezért filter_complex kell hozzájuk."""
    return look in ("rgb_split", "glitch")


def clamp_speed(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 1.0
    return max(0.2, min(5.0, v))


def catalogue() -> dict:
    """Amit a rendezőnek átadunk: pontosan ezek a nevek használhatók."""
    return {"motion": list(MOTIONS), "look": list(LOOKS), "transition": list(TRANSITIONS),
            "text_position": list(TEXT_POSITIONS), "text_style": list(TEXT_STYLES),
            "text_anim": list(TEXT_ANIMS), "speed": "0.2 – 5.0 (klipnél)"}

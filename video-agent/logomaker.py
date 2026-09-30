"""Logó és profilkép: a modell vektoros SVG-t tervez, mi lerendereljük.

Pixeles képmodellt szándékosan nem használunk erre: az ingyenes tartalék
vízjelet tesz a képre, és egy logónál minden futás mást rajzolna. Az SVG
éles marad bármekkora méretben, és a kész fájl tovább is szerkeszthető.

A modell SVG-jét nem engedjük be úgy, ahogy van. Egy SVG futtathat
szkriptet, és hivatkozhat külső vagy helyi fájlra — a renderelő böngésző
betöltené. Ezért egy engedélylistán átszűrjük: csak rajzoló elemek és
attribútumok maradnak, hivatkozás csak a saját elemeire (#id) mutathat.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import playbook

SIZE = 1080
MAX_SVG = 24000
VARIANTS = 3
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

# A weboldal ikonja: ebből indul ki minden AXIMBRA-logó, hogy a márka egy maradjon.
AXIMBRA_MARK = """<svg viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="64" y2="64"
gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#00E9FF"/><stop offset="1" stop-color="#C81FFF"/>
</linearGradient></defs><rect width="64" height="64" rx="14" fill="#04040C"/>
<path d="M32 13 L47 51 H39.4 L36.2 42.4 H27.8 L24.6 51 H17 Z M30.1 35.6 h3.8 L32 30.2 Z" fill="url(#g)"/>
<circle cx="50" cy="16" r="4.5" fill="#00E9FF"/></svg>"""

ELEMENTS = {"svg", "g", "defs", "title", "desc", "path", "circle", "ellipse", "rect", "line", "polygon",
            "polyline", "text", "tspan", "linearGradient", "radialGradient", "stop", "clipPath", "mask",
            "use", "filter", "feGaussianBlur", "feOffset", "feMerge", "feMergeNode", "feColorMatrix",
            "feBlend", "feComposite", "feFlood", "feDropShadow"}
ATTRS = {"id", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy", "width", "height",
         "points", "viewBox", "transform", "fill", "fill-opacity", "fill-rule", "clip-rule", "stroke",
         "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
         "stroke-miterlimit", "opacity", "offset", "stop-color", "stop-opacity", "gradientUnits",
         "gradientTransform", "spreadMethod", "clip-path", "mask", "filter", "font-family", "font-size",
         "font-weight", "font-style", "letter-spacing", "text-anchor", "dominant-baseline", "dx", "dy",
         "stdDeviation", "in", "in2", "result", "mode", "operator", "values", "type", "k1", "k2", "k3", "k4",
         "flood-color", "flood-opacity", "preserveAspectRatio", "maskUnits", "clipPathUnits",
         "filterUnits", "primitiveUnits", "href", "xmlns"}
# Attribútumértékben csak a saját elemre mutató url(#id) engedett.
_URL_RE = re.compile(r"url\(\s*(?!['\"]?#)[^)]*\)", re.I)


class LogoError(RuntimeError):
    pass


def logo_prompt(brief: str, pages_text: str, lang: str, feedback: str = "", previous: list[str] | None = None) -> str:
    redo = ""
    if feedback:
        prev = "\n\n".join(f"PREVIOUS VARIANT {i + 1}:\n{s[:6000]}" for i, s in enumerate(previous or []))
        redo = f"""
This is a REVISION. The client saw the previous variants and said:
\"\"\"{feedback}\"\"\"
Apply that precisely. Keep what they did not complain about.

{prev}
"""
    return f"""You are a senior brand designer. Design a logo mark as hand-written SVG code.

THE BRIEF:
\"\"\"{brief}\"\"\"
{redo}
Company facts (when the brief is about AXIMBRA):
{playbook.AXIMBRA_FACTS}

AXIMBRA's existing mark (the website icon). For an AXIMBRA logo or profile picture, evolve THIS mark — same
letterform idea, same palette: background #04040C, gradient #00E9FF → #C81FFF, accent cyan #00E9FF, optional
ring gradient #00E5FF → #8B5CFF → #FF3DF2. Invent an unrelated mark only if the brief asks for a new concept.
{AXIMBRA_MARK}

Source text from the brief's links, if any:
{pages_text or "(none)"}

Make {VARIANTS} clearly different variants.

Rules for every variant:
- One <svg> element, xmlns="http://www.w3.org/2000/svg", viewBox="0 0 {SIZE} {SIZE}", width="{SIZE}" height="{SIZE}".
- It will be shown as a ROUND profile picture: fill the whole square with the background, and keep every
  important shape inside a centred circle of radius 430. Nothing important near the corners.
- It must still read at 40 px: bold, simple shapes, at most 3 colours plus the background, no thin hairlines,
  no tiny text. Prefer a symbol or letterform to a long word.
- Only these elements: g, defs, path, circle, ellipse, rect, line, polygon, polyline, text, tspan,
  linearGradient, radialGradient, stop, clipPath, mask, use, filter with feGaussianBlur/feOffset/feMerge.
- No <image>, no <script>, no <style>, no <foreignObject>, no external links or fonts, no CSS classes.
- Text only if the brief asks for it: font-family="Arial, Helvetica, sans-serif", font-weight="700".
- Geometry must be exact and symmetric where intended; compute coordinates, do not guess.

Answer in exactly this format and nothing else:
TITLE: <short name, {"Hungarian" if lang == "hu" else "English"}>
=== VARIANT: <one sentence, {"Hungarian" if lang == "hu" else "English"}: the idea of this variant>
<svg ...>...</svg>
=== VARIANT: <idea>
<svg ...>...</svg>
=== VARIANT: <idea>
<svg ...>...</svg>"""


def parse(text: str) -> dict:
    """A modell válaszából a cím és a változatok (ötlet + nyers SVG)."""
    text = text or ""
    m = re.search(r"^\s*TITLE:\s*(.+)$", text, re.M)
    title = (m.group(1).strip() if m else "Logó")[:80]
    variants = []
    for block in re.split(r"^\s*===\s*VARIANT:\s*", text, flags=re.M)[1:]:
        idea, _, rest = block.partition("\n")
        svg = re.search(r"<svg\b.*?</svg>", rest, re.S | re.I)
        if svg:
            variants.append({"idea": idea.strip()[:200], "svg": svg.group(0)})
    if not variants:   # ha a formát nem tartotta, a nyers SVG-ket még kivesszük
        variants = [{"idea": "", "svg": s} for s in re.findall(r"<svg\b.*?</svg>", text, re.S | re.I)]
    return {"title": title, "variants": variants[:VARIANTS]}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sanitize(svg: str) -> str:
    """Engedélylistás tisztítás. Ami nem rajzol, az kimarad; ha a gyökér nem
    SVG vagy a fájl nem értelmezhető, LogoError."""
    if len(svg) > MAX_SVG:
        raise LogoError("túl nagy SVG")
    if re.search(r"<!DOCTYPE|<!ENTITY", svg, re.I):
        raise LogoError("tiltott DTD az SVG-ben")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        raise LogoError(f"hibás SVG ({e})") from e
    if _local(root.tag) != "svg":
        raise LogoError("a gyökérelem nem svg")

    def clean(el):
        for child in list(el):
            if not isinstance(child.tag, str) or _local(child.tag) not in ELEMENTS:
                el.remove(child)
                continue
            clean(child)
        for key in list(el.attrib):
            name = _local(key)
            val = el.attrib[key]
            if name not in ATTRS or name.lower().startswith("on"):
                del el.attrib[key]
            elif name == "href" and not val.strip().startswith("#"):
                del el.attrib[key]
            elif _URL_RE.search(val) or "javascript:" in val.lower():
                del el.attrib[key]

    clean(root)
    root.set("viewBox", root.get("viewBox") or f"0 0 {SIZE} {SIZE}")
    root.set("width", str(SIZE))
    root.set("height", str(SIZE))
    out = ET.tostring(root, encoding="unicode")
    if not re.search(r"<(path|circle|ellipse|rect|polygon|polyline|line|text)\b", out.replace(f"{{{SVG_NS}}}", "")):
        raise LogoError("az SVG-ben nincs rajzoló elem")
    return out

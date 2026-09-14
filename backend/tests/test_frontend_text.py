"""A lapon megjelenő szöveg ellenőrzése — nem a kódé, hanem amit az olvasó lát.

Miért itt van: a projektben a pytest az egyetlen automatikus kapu, és ez a
hibaosztály olyan, amit kódolvasással nem lehet észrevenni. A JSX eldobja a
címkék melletti sortöréseket, tehát ez:

    ... legfeljebb <b>2 évig</b>
    őrizzük.

a lapon „2 évigőrizzük"-ként jelenik meg. Kettő ilyen volt az adatkezelési
tájékoztatóban — egy jogi szövegben, ahol a legkevésbé hihető, hogy elírás.
A javítás a sor végén egy explicit `{" "}`.
"""
import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"

# Csak beágyazott (inline) címkék. A `span` szándékosan hiányzik: ebben a
# projektben blokk-elemként is használjuk (`display: block`), ott pedig a
# szóköz hiánya nem látszik, tehát csak vaklármát adna.
TAGS = r"(?:b|i|em|strong|code|a|Link)"
CLOSE_AT_EOL = re.compile(r"</" + TAGS + r">\s*$")
OPEN_AT_BOL = re.compile(r"^\s*<" + TAGS + r"[ >]")
WORD_END = re.compile(r"[\w.,;:)»”]$")
WORD_START = re.compile(r"^\s*[\w(„«]")
CLOSER = re.compile(r"^\s*</")
COMMENT = ("//", "*", "/*", "{/*")


def missing_spaces(path: pathlib.Path):
    lines = path.read_text(encoding="utf-8").split("\n")
    out = []
    for i in range(len(lines) - 1):
        cur, nxt = lines[i].rstrip(), lines[i + 1]
        if not cur or CLOSER.match(nxt):
            continue
        if cur.lstrip().startswith(COMMENT) or nxt.lstrip().startswith(COMMENT):
            continue
        if CLOSE_AT_EOL.search(cur) and WORD_START.match(nxt):
            out.append((i + 1, cur.strip(), nxt.strip()))
        elif OPEN_AT_BOL.match(nxt) and WORD_END.search(cur):
            out.append((i + 1, cur.strip(), nxt.strip()))
    return out


@pytest.mark.parametrize("path", sorted(FRONTEND.rglob("*.jsx")), ids=lambda p: p.name)
def test_no_words_glued_together_by_jsx(path):
    hits = missing_spaces(path)
    assert not hits, "A JSX itt elnyeli a szóközt (tegyél a sor végére {\" \"}):\n" + "\n".join(
        f"  {path.name}:{ln}\n    …{a[-70:]}\n  > {b[:70]}…" for ln, a, b in hits
    )


# --------------------------------------------------------- olvashatóság ---
def test_the_cards_are_not_rotated_in_3d():
    """A kártya ne dőljön meg a kurzor alatt.

    A 14 fokos térbeli forgatás miatt a böngésző egyszer kirajzolta a kártyát
    egy rétegre, és azt a kész képet döntötte meg — a szöveg pedig
    újramintázva, homályosan jelent meg, pontosan addig, amíg az ember
    olvasni akarta. A visszajelzés maradt (fénypont, megemelkedés), csak nem
    a szöveg torzításával.

    A `will-change: transform` és a `transform-style: preserve-3d` ugyanezt a
    réteget kényszeríti ki, ezért azok sem térhetnek vissza a kártyára.
    """
    agents = (FRONTEND / "components" / "Agents.jsx").read_text(encoding="utf-8")
    code = "\n".join(l for l in agents.split("\n") if not l.strip().startswith("//"))
    assert "rotateY(" not in code and "rotateX(" not in code, "a kártya megint térben forog"

    css = (FRONTEND / "index.css").read_text(encoding="utf-8")
    card_rule = css[css.index(".card { position: relative;"):]
    card_rule = card_rule[:card_rule.index("}") + 1]
    for forbidden in ("will-change", "preserve-3d"):
        assert forbidden not in card_rule, f"{forbidden} visszakerült a .card szabályba"


# A szövegdobozokat hoverkor nem toljuk el `transform`-mal. Azok a dobozok,
# amelyeken `backdrop-filter` van, saját rétegre kerülnek; egy kész réteget a
# böngésző nem rajzol újra, csak eltol. Ha az eltolás nem egész eszközpixel —
# 125%-os Windows-nagyításnál a -3px épp 3,75 —, akkor a kész képet mintázza
# újra, és a szöveg elmosódik. A `scale()` ugyanezt csinálja minden
# nagyításnál. Az emelést ezért `position: relative` + `top` adja.
STYLESHEETS = ("index.css", "components/agentsim.css")

# Csak a szöveget hordozó dobozok. A tisztán dekoratív rétegeken (.liquid a
# gomb alatt, a pulzáló pont) a transform maradhat: nincs rajtuk betű.
TEXT_BOXES = (".card", ".btn", ".ref-card", ".pkg-card", ".hero-phone", ".sim-btn", ".cf-submit")
DECORATIVE = (".liquid", ".glow", ".ref-dot", ".dot")


def _hover_rules():
    for name in STYLESHEETS:
        css = (FRONTEND / name).read_text(encoding="utf-8")
        for block in css.split("}"):
            head, _, body = block.rpartition("{")
            if not head:
                continue
            selector = head.split("\n")[-1].strip()
            if ":hover" not in selector and ":active" not in selector:
                continue
            yield name, selector, body


def test_hover_does_not_resample_text():
    offenders = []
    for name, selector, body in _hover_rules():
        if any(d in selector for d in DECORATIVE):
            continue
        if not any(b in selector for b in TEXT_BOXES):
            continue
        if "transform" in body:
            offenders.append(f"{name}: {selector} -> {body.strip()[:70]}")
    assert not offenders, (
        "Hoverkor `transform` került egy szövegdobozra — ettől lesz homályos a "
        "betű a kurzor alatt. Használj `position: relative` + `top` emelést:\n  "
        + "\n  ".join(offenders)
    )


def test_no_fractional_scale_anywhere_on_a_text_box():
    """A `scale(1.02)` minden nagyításnál újramintázza a szöveget."""
    offenders = []
    for name, selector, body in _hover_rules():
        if "scale(" in body:
            offenders.append(f"{name}: {selector} -> {body.strip()[:70]}")
    assert not offenders, "Hoverkor nagyítás:\n  " + "\n  ".join(offenders)


def test_the_simulation_has_no_copy_link_button():
    """A „Link másolása" gomb lekerült a kártyáról; ne szivárogjon vissza."""
    sim = (FRONTEND / "components" / "AgentSim.jsx").read_text(encoding="utf-8")
    assert "sim-copy" not in sim and "clipboard" not in sim, "visszakerült a link-másoló gomb"
    css = (FRONTEND / "components" / "agentsim.css").read_text(encoding="utf-8")
    assert ".sim-copy" not in css, "a .sim-copy szabály itt maradt"


def test_the_founder_introduces_himself_in_every_language():
    """A bemutatkozás magyarul és angolul is megvan.

    A többi nyelv az angolra esik vissza, tehát ha az angol hiányzik, a német
    lapon magyar szöveg jelenne meg — pontosan az a hiba, ami az agentnél már
    egyszer kiment élesbe.
    """
    for code in ("hu", "en"):
        text = (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")
        founder = text[text.index("founder: {"):]
        founder = founder[:founder.index("\n  }")]
        for key in ("bioTag:", "bio:", "facts:"):
            assert key in founder, f"{code}.js: hiányzik a founder.{key}"


def test_the_header_sits_in_the_same_column_as_the_page():
    """A fejléc tartalma ugyanabban az oszlopban áll, mint a lap szövege.

    Széles képernyőn a sáv a teljes szélességet fogta, a lap többi része viszont
    egy 1200 pixeles oszlopban ül — 1920 pixeles ablakban a logó 332 pixerrel a
    szöveg bal széle előtt állt. Ezért a sáv háttere maradt teljes szélességű, a
    tartalma viszont egy `.nav-inner` dobozba került, ugyanazzal a
    max-szélességgel és belső margóval, mint a `.container`.
    """
    nav = (FRONTEND / "components" / "Nav.jsx").read_text(encoding="utf-8")
    assert 'className="nav-inner"' in nav, "a fejléc tartalma kikerült a tartalomoszlopból"

    css = (FRONTEND / "index.css").read_text(encoding="utf-8")
    inner = css[css.index(".nav-inner {"):]
    inner = inner[:inner.index("}") + 1]
    container = css[css.index(".container {"):]
    container = container[:container.index("}") + 1]
    for prop in ("max-width: 1200px", "margin: 0 auto", "padding: 0 28px"):
        assert prop in container, f"a .container már nem {prop} — igazítsd hozzá a fejlécet"
        assert prop in inner, f"a fejléc belső sávjából hiányzik: {prop}"

    # A hívás-pirula 334 pixel, és szűk ablakban ez tolta le a menüt a képernyőről.
    assert "@media (max-width: 1280px){ .nav-links .btn-callbar { display: none; } }" in css, \
        "a hívás-pirula megint ott van szűk ablakban is"

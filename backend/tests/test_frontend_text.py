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

"""A közös felületen ne maradjon beégetett magyar szöveg.

Ezt egy képernyőkép hívta életre: az angol lapon, két angol gomb között ott
állt egy „Nézd meg működés közben". Egyetlen sor volt, és pontosan az a fajta
hiba, amit a fejlesztő nem lát — ő magyarul nézi az oldalt.

Kivétel két helyen van, és mindkettő szándékos:
  * a jogi oldalak (impresszum, adatkezelési tájékoztató) csak magyarul
    léteznek, és a lap canonicalja is ezt mondja;
  * maguk az i18n-fájlok, ahol a magyar szöveg a helyén van.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
HUN = re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")
COMMENT = ("//", "*", "/*", "{/*")
# Csak magyarul létező oldalak (useDocumentMeta: translated: false).
HU_ONLY = {"pages/Impresszum.jsx", "pages/Adatkezeles.jsx"}


def offenders():
    """A magyar sorok a megjegyzéseken kívül.

    A megjegyzés több sorra is átnyúlhat, ezért állapotot kell vezetni: a
    folytatósorok nem kezdődnek `//`-rel, és enélkül minden kommentár
    vaklárma lenne.
    """
    out = []
    for path in sorted(SRC.rglob("*.jsx")):
        # as_posix: Windowson a str() visszaperrel adna, es a HU_ONLY nem illeszkedne.
        rel = path.relative_to(SRC).as_posix()
        if rel in HU_ONLY or rel.startswith("i18n/"):
            continue
        in_block = False
        for i, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            stripped = line.strip()
            opened = "/*" in line
            closed = "*/" in line
            was_in_block = in_block
            if opened and not closed:
                in_block = True
            elif closed:
                in_block = False
            if was_in_block or opened or stripped.startswith(COMMENT):
                continue
            if HUN.search(line):
                out.append(f"{rel}:{i}  {stripped[:100]}")
    return out


def test_no_hungarian_text_outside_the_translation_files():
    found = offenders()
    assert not found, (
        "Beégetett magyar szöveg a felületen — ez idegen nyelvű lapon is így "
        "jelenik meg. Tedd az i18n-be:\n  " + "\n  ".join(found)
    )

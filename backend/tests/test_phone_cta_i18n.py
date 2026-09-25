"""A hero telefon-doboz szövege ne keveredjen angollal a többi hét nyelven.

Élesben a német (és 5 másik) oldalon a `phoneCta.note` angolul jelent meg,
mert csak az `origin` sort fordítottuk le a +36-os átirányítás bevezetésekor.
A hiba nem dobott hibát, csendben esett vissza az en.js szövegére — pontosan
az a fajta hiba, amit egy teljes körű ellenőrzés hivatott elkapni.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
LANGS = ["hu", "en", "de", "es", "fr", "it", "ro", "sk", "zh"]


def test_every_language_defines_its_own_hero_phone_note():
    for code in LANGS:
        text = (SRC / f"{code}.js").read_text(encoding="utf-8")
        m = re.search(r"phoneCta:\s*\{([^}]*)\}", text)
        assert m, f"{code}.js: nincs phoneCta blokk"
        assert "note:" in m.group(1), f"{code}.js: a phoneCta.note nincs lefordítva, angolra esik vissza"
        assert "badge:" in m.group(1), f"{code}.js: a phoneCta.badge hiányzik"

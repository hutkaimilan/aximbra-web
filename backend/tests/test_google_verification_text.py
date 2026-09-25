"""A szövegek, amelyeket a Google OAuth-verifikáció ellenőre összevet a működéssel.

A Gmail-bekötés jóváhagyásánál a Google ember olvassa el, mit ígér a lap, és
megnézi, azt csinálja-e az alkalmazás. Két dolog bukta el ezt eddig csendben:

- A felület nyolc nyelven azt írta, hogy „ez a kód soha nem küld, a küldés
  kódszinten tiltott" — miközben a /draft/send megerősítés után küld. Ez a
  látogatónak is valótlan volt, nem csak a Google-nak.
- A korlátozott felhasználásról (Limited Use) szóló nyilatkozat csak a magyar
  tájékoztatóban állt, a bekötés gombjánál és angolul nem.

Ezek a tesztek azt tartják fenn, hogy mindkettő igaz maradjon.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
AGENT_JS = (SRC / "i18n" / "agent.js").read_text(encoding="utf-8")
LANGS = ["hu", "en", "de", "es", "fr", "it", "ro", "sk", "zh"]


def lang_block(code: str) -> str:
    start = re.search(rf"^  {code}: \{{", AGENT_JS, re.M)
    assert start, f"nincs {code} blokk az agent.js-ben"
    rest = AGENT_JS[start.end():]
    nxt = re.search(r"^  [a-z]{2}: \{", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def test_every_language_shows_the_limited_use_statement_at_the_connect_button():
    for code in LANGS:
        block = lang_block(code)
        lead = re.search(r'privacyLead: "([^"]+)"', block)
        assert lead, f"{code}: hiányzik a privacyLead"
        assert "Google API Services User Data Policy" in lead.group(1), code
        assert "Limited Use" in lead.group(1), code
        assert re.search(r'privacyLink: "[^"]+"', block), f"{code}: hiányzik a privacyLink"


def test_the_connect_screen_links_the_privacy_notice():
    jsx = (SRC / "demos" / "EmailAgent.jsx").read_text(encoding="utf-8")
    assert "a.connect.privacyLead" in jsx
    assert '"/en/adatkezeles"' in jsx and '"/adatkezeles"' in jsx


def test_no_language_claims_the_agent_cannot_send():
    """A küldés létezik, megerősítéshez kötve. Aki ezt tagadja, valótlant állít."""
    stale = [
        "kódszinten", "code level", "Code-Ebene", "nivel de código", "niveau du code",
        "livello di codice", "nivel de cod", "úrovni kódu",
    ]
    for word in stale:
        assert word not in AGENT_JS, f"visszakerült a „soha nem küld” állítás: {word}"


def test_the_english_privacy_notice_carries_the_limited_use_statement():
    en = (SRC / "pages" / "PrivacyEn.jsx").read_text(encoding="utf-8")
    assert "including the Limited Use requirements" in en
    assert "Google API Services User Data Policy" in en
    assert "do not use it to train any artificial intelligence model" in en
    # Az angol lap a magyarra mutat, mint irányadóra.
    assert 'to="/adatkezeles"' in en


def test_the_privacy_page_serves_english_on_the_english_route():
    hu = (SRC / "pages" / "Adatkezeles.jsx").read_text(encoding="utf-8")
    assert 'lang === "en" ? <PrivacyEn' in hu


def test_the_processors_have_english_columns():
    legal = (SRC / "legal.js").read_text(encoding="utf-8")
    names = re.findall(r'name: "([^"]+)"', legal.split("export const PROCESSORS")[1])
    assert names, "nincs adatfeldolgozó"
    assert legal.count("roleEn:") == len(names) and legal.count("whereEn:") == len(names)

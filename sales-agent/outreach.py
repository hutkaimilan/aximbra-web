"""LinkedIn-megkeresés: a profilt te másolod be, a szöveget az agent írja, elküldeni te küldöd el.

Miért kézi bemásolás, és nem összekötés: a LinkedIn nem ad hozzáférést más
emberek profiljának olvasásához. Önkiszolgálóan a saját profil, a saját e-mail
cím és a posztolás kérhető; a profilolvasás partnerprogramhoz kötött. A
lekaparás pedig a felhasználási feltételekbe ütközik (fiókzárolás), és mivel
nem az érintettől gyűjtené az adatot, a GDPR 14. cikke szerint értesítési
kötelezettséggel is jár. Amit viszont a böngésződben jogosultan elolvasol, azt
be is másolhatod: ugyanaz az információ, csak nem automatizáltan szerezve.

Két dolgot ad vissza, és az első a fontosabb: egy ítéletet arról, hogy érdemes-e
egyáltalán írni, és csak utána a szöveget. A félresikerült megkeresések nem
attól lettek rosszak, hogy kevés volt bennük a személyre szabás, hanem attól,
hogy olyannak mentek, aki maga építi ugyanezt.

Amit a modell állít, azt a kód ellenőrzi: a hivatkozott mondatnak tényleg a
bemásolt szövegben kell lennie (ugyanaz az egyezésvizsgálat, mint a leveleknél),
és ár nem kerülhet bele. Ami nem áll, az a panelen figyelmeztetésként látszik —
nem némán javítjuk, mert a szöveget te küldöd el, és neked kell látnod, mi
gyanús benne.
"""
from __future__ import annotations

import logging

import llm
import playbook
import verify

logger = logging.getLogger(__name__)

VERDICTS = ("ir", "ne_irj")
MIN_PROFILE = 80
MAX_PROFILE = 12000
MIN_MESSAGE = 80


def draft(profile: str, note: str = "", lang: str = "hu") -> dict:
    """Ítélet és szöveg a bemásolt profilra. ValueError, ha a bemenet kevés."""
    profile = (profile or "").strip()
    if not MIN_PROFILE <= len(profile) <= MAX_PROFILE:
        raise ValueError(f"A bemásolt profil {MIN_PROFILE} és {MAX_PROFILE} karakter között legyen "
                         f"(most {len(profile)}).")
    if lang not in playbook.LANG_NAMES:
        raise ValueError(f"Ismeretlen nyelv: {lang}")

    data = llm.extract_json(llm._ask(playbook.linkedin_prompt(profile, (note or "").strip(), lang)))
    if not isinstance(data, dict):
        raise llm.LLMError("a megkeresés-író nem objektumot adott")

    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        raise llm.LLMError(f"ismeretlen ítélet: {verdict!r}")
    reason = str(data.get("reason") or "").strip()[:300]

    if verdict == "ne_irj":
        # Szöveget ilyenkor szándékosan nem adunk vissza, akkor sem, ha a modell
        # írt egyet: ha ott van a mezőben, előbb-utóbb valaki kimásolja.
        return {"verdict": verdict, "reason": reason or "Nem célcsoport.",
                "quote": "", "message": "", "problems": []}

    quote = str(data.get("quote") or "").strip()
    message = str(data.get("message") or "").strip()
    if len(message) < MIN_MESSAGE:
        raise llm.LLMError("a megkeresés-író üres vagy túl rövid szöveget adott")

    problems = []
    if not quote:
        problems.append("Nem jelölte meg, melyik mondatra hivatkozik a profilból.")
    elif not verify.quote_on_page(quote, profile):
        problems.append("A hivatkozott mondat nincs benne a bemásolt szövegben — ellenőrizd, "
                        "mielőtt elküldöd.")
    if verify.has_price(message):
        problems.append("Árat említ. A megkeresésben nem árazunk.")
    if len(message) > playbook.LINKEDIN_MAX_CHARS:
        problems.append(f"Hosszabb {playbook.LINKEDIN_MAX_CHARS} karakternél "
                        f"({len(message)}) — LinkedInen ennyit nem olvasnak el.")
    return {"verdict": verdict, "reason": reason, "quote": quote,
            "message": message, "problems": problems}

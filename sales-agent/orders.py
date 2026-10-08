"""Egyszeri videómegbízások: Milán kérése, amit a sales agent ír át a videós
agentnek szóló briefté.

Miért a sales agenten át, és nem közvetlenül: a sales agent tudja, kinek
szól az AXIMBRA, mire reagálnak a cégvezetők, és mi igaz az oldalon (a
tényeket a playbook tartja). Milán megmondja, MIT akar; a sales agent írja
meg, HOGYAN lesz belőle jó videó; a videós agent pedig elkészíti.

Egy megbízás egyszer fut le (az azonosítón szűrünk, a kész állapot a
beállítások között van). Új megbízáshoz új azonosítóval kell felvenni ide.
A videó „hold" módban megy: elkészül, de nem posztolódik — a videós agent
paneljén lehet átnézni és kiküldeni.
"""
from __future__ import annotations

ORDERS = (
    {
        "id": "aximbra-osszefoglalo-2026-10",
        "lang": "hu",
        "form": "video",
        "seconds": 90,
        "hold": True,
        # Üres szándékosan: a videó a panelen vár, onnan megy ki. Egy régi
        # videós agent (amelyik a „hold"-ot nem ismeri) cél nélkül elutasítja,
        # így jóváhagyás nélkül akkor sem posztolhat.
        "targets": [],
        # A videós agent ezekről készít telefonos képernyőfelvételt (legfeljebb
        # hat). A #szakasz a hosszú főoldal egy-egy részétől indítja a képet.
        "urls": [
            "https://aximbra.hu",
            "https://aximbra.hu/#agentek",
            "https://aximbra.hu/#folyamat",
            "https://aximbra.hu/#megterules",
            "https://aximbra.hu/#eset",
            "https://epistemebudapest.up.railway.app",
        ],
        "instruction": """Összefoglaló videó az AXIMBRA-ról, az aximbra.hu oldalról. Legfeljebb 90 másodperc, magyarul,
álló (9:16), LinkedInre és Instagramra.

Végig az aximbra.hu-t mutassa: a jelenetek túlnyomó része az oldal képernyőfelvétele legyen (telefonon görgetve),
ne általános grafika. Ahol egy agent működését mutatja, ott használhat telefonhívás- vagy postafiók-animációt is,
de az oldal maradjon a gerinc.

Mutassa be az oldal legfontosabb elemeit, ebben a sorrendben:
1. A nyitóképernyő: mit csinál az AXIMBRA — egyedi AI agentek cégeknek, a cég saját rendszerén, és semmi nem megy
   ki emberi jóváhagyás nélkül.
2. Az agentek: tizenöt kész agent-típus kártyákon (e-mail rendező, érdeklődő-minősítő, dokumentum-elemző,
   ügyfélszolgálat, NIS2-megfelelés, értékesítő agent, multi-agent rendszer…), élő demókkal, regisztráció nélkül.
3. A folyamat: hogyan készül egy agent — felmérés, specifikáció, építés izolált környezetben, független ellenőrzés,
   emberi jóváhagyás, átadás.
4. A megtérülés-kalkulátor: a látogató maga számolja ki, mennyi idő után térül meg.
5. Nagyon röviden az EPISTEME: az AXIMBRA saját, kész bemutató rendszere (kitalált budapesti fine dining étterem,
   NEM ügyfélmunka — ezt ki kell mondani). A weboldal asztalfoglalása és a hozzá tartozó telefonos AI agent
   ugyanazt a szabadhely-számlálót írja; a telefonos agent valódi számon fut, magyarul, angolul és spanyolul beszél,
   hívás közben vált, és SMS-ben visszaigazol.
6. Zárás: aximbra.hu — a demók most is kipróbálhatók.

A hangnem nyugodt, szakmai, magabiztos; a cél, hogy egy kkv-vezető a végén kipróbálja az egyik demót.""",
    },
)

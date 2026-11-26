"""Agentenkénti forgatókönyv a videókhoz.

Minden ütem (beat) egy narrációs mondat. Az időzítést a builder számolja a
felolvasás hosszából, kézzel nem kell igazítani.

Mezők:
  say   a narráció (Tamás hangja); None = csak kép
  cap   felirat, (szöveg, kiemelt szavak)
  tap   ide koppint az ütem elején (keret-hivatkozás)
  wait  koppintás után egy pillanatra ez az állapot (töltés), „GYORSÍTVA” jellel
  show  ez az állapot látszik az ütemben
  run   állapotok sora, egyenletesen elosztva a mondat alatt (futás közben)
  box   kiemelő keret (hivatkozás vagy hivatkozások listája → befoglaló)
  focus erre áll a kamera (alapból a box)
  ding  csengő, amikor az állapot megjelenik

Keret-hivatkozás: "ÁLLAPOT.elem" vagy "ÁLLAPOT.elem[i]" vagy "ÁLLAPOT.elem[i:j]".
A számok mind a képernyőn látható, valódi tartalomból jönnek (sims.json /
live.json); az élő demóknál a rögzített futás eredményéből.
"""

SIM_CTA = "Nézd meg működés közben: aximbra pont hu."
LIVE_CTA = "Próbáld ki regisztráció nélkül: aximbra pont hu."
SIM_NOTE = "Illusztráció magyar mintaadatokkal"


def sim_states(k, n_run, extra=()):
    st = {"I": f"s{k}_I.png", "D": f"s{k}_D.png"}
    for i in n_run:
        st[f"R{i}"] = f"s{k}_R{i}.png"
    for e in extra:
        st[e] = f"s{k}_{e}.png"
    return st


AGENTS = {
    # ───────────────────────── élő demók ─────────────────────────
    1: dict(
        name="Érdeklődő-minősítő", kind="live", src="live", key="1",
        line="Megmutatom, hogyan rangsorolja egy AI az érdeklődőidet.",
        hook_hi={"AI"},
        states={"I": "l1_I.png", "SA": "l1_SA.png", "WA": "l1_WA.png", "RA": "l1_RA.png",
                "SB": "l1_SB.png", "WB": "l1_WB.png", "RB": "l1_RB.png"},
        first="I",
        beats=[
            dict(say="Bemásolom a beérkező érdeklődést.", cap=("BEMÁSOLOM AZ ÉRDEKLŐDŐT", "ÉRDEKLŐDŐT"),
                 tap="I.samples[0]", show="SA", box="SA.input"),
            dict(say="Egy negyvenfős könyvelőiroda ügyvezetője.", cap=("40 FŐS KÖNYVELŐIRODA", "40"),
                 show="SA", box="SA.input"),
            dict(say="Á kategóriás érdeklődő: ma érdemes felhívni.", cap=("MINŐSÍTÉS: A", "A"),
                 tap="SA.run", wait="WA", show="RA", box="RA.fields[0]", focus="RA.fields[0:5]", ding=True),
            dict(say="Igény, keret, döntéshozó, határidő: mindegyik igazolt.", cap=("MIND IGAZOLT", "IGAZOLT"),
                 show="RA", box="RA.fields[1:5]"),
            dict(say="Megindokolja, és megmondja a következő lépést.", cap=("MEGMONDJA A KÖVETKEZŐ LÉPÉST", "KÖVETKEZŐ"),
                 show="RA", box="RA.fields[5:7]"),
            dict(say="És ha egy egyetemista kérne ingyen agentet?", cap=("ÉS HA INGYEN KÉRNÉK?", "INGYEN"),
                 tap="RA.samples[1]", show="SB", box="SB.input"),
            dict(say="Dé kategória: a költségvetés nem illeszkedik.", cap=("MINŐSÍTÉS: D", "D"),
                 tap="SB.run", wait="WB", show="RB", box="RB.fields[0:3]", focus="RB.fields[0:5]", ding=True),
            dict(say="Így tudod, kit hívj fel ma, és kire ne menjen el a napod.", cap=("KIT HÍVJ FEL MA", "MA"),
                 show="RB", box="RB.fields[5:7]"),
        ],
        cta=LIVE_CTA, end_sub=("Próbáld ki", "regisztráció nélkül"),
        note="Az érdeklődők kitaláltak · a minősítés valódi",
    ),
    6: dict(
        name="Webshop-asszisztens", kind="live", src="live", key="6",
        line="Megmutatom, hogyan válaszol egy AI a vásárlóidnak.",
        hook_hi={"AI"},
        states={"SA": "l6_SA.png", "WA": "l6_WA.png", "RA": "l6_RA.png",
                "SB": "l6_SB.png", "WB": "l6_WB.png", "RB": "l6_RB.png"},
        first="SA",
        beats=[
            dict(say="Egy vásárló ír: hol tart a rendelésem? Holnapra kellene.", cap=("HOL TART A RENDELÉSEM?", "RENDELÉSEM?"),
                 show="SA", box="SA.textarea", focus=["SA.inputs[1]", "SA.textarea"]),
            dict(say="Az agent megnézi: a rendelő címéről jött.", cap=("A RENDELŐ CÍMÉRŐL JÖTT", "RENDELŐ"),
                 tap="SA.send", wait="WA", show="RA", box="RA.tags", focus="RA.out", ding=True),
            dict(say="Megírja a választ: feladták, futár, csomagszám, követési link.", cap=("MEGÍRJA A VÁLASZT", "VÁLASZT"),
                 show="RA", box="RA.pre"),
            dict(say="És ha valaki más kérdez ugyanarról a rendelésről?", cap=("ÉS HA MÁS KÉRDEZ?", "MÁS"),
                 tap="RA.chips[1]", show="SB", box="SB.inputs[1]", focus=["SB.inputs[1]", "SB.textarea"]),
            dict(say="Nem a rendelő címe, ezért adatot nem ad ki.", cap=("ADATOT NEM AD KI", "NEM"),
                 tap="SB.send", wait="WB", show="RB", box="RB.tags", focus="RB.out", ding=True),
            dict(say="Egy éles boltban a választ egy munkatárs hagyja jóvá.", cap=("MUNKATÁRS HAGYJA JÓVÁ", "JÓVÁ"),
                 show="RB", box="RB.pre"),
        ],
        cta=LIVE_CTA, end_sub=("Próbáld ki", "regisztráció nélkül"),
        note="A demóbolt és a rendelések kitaláltak · a válasz valódi",
    ),
    7: dict(
        name="Dokumentum-elemző", kind="live", src="live", key="7",
        line="Megmutatom, hogyan olvas át egy AI egy szerződést.",
        hook_hi={"AI"},
        states={"I": "l7_I.png", "W": "l7_W.png", "R": "l7_R.png"},
        first="I",
        beats=[
            dict(say="Feltöltöd a szerződésed, vagy kipróbálod egy mintán.", cap=("TÖLTSD FEL A SZERZŐDÉSED", "SZERZŐDÉSED"),
                 show="I", box="I.upload", focus=["I.upload", "I.run"]),
            dict(say="Összefoglalja, kik a felek, és miről szól.", cap=("ÖSSZEFOGLALJA", "ÖSSZEFOGLALJA"),
                 tap="I.run", wait="W", show="R", box="R.fields[1:3]", ding=True),
            dict(say="Kiveszi a fő adatokat: összeg, időtartam, fizetési határidő.", cap=("KIVESZI A FŐ ADATOKAT", "FŐ ADATOKAT"),
                 show="R", box="R.fields[5:9]"),
            dict(say="Minden adat mellett ott a forrásmondat.", cap=("OTT A FORRÁSMONDAT", "FORRÁSMONDAT"),
                 show="R", box="R.srcs[4]", focus="R.fields[6]"),
            dict(say="Kiemeli a kockázatot: két év hűségidő, és egyoldalú díjemelés.", cap=("KIEMELI A KOCKÁZATOT", "KOCKÁZATOT"),
                 show="R", box="R.fields[10]"),
            dict(say="És megmondja, mit tárgyalj újra aláírás előtt.", cap=("MIT TÁRGYALJ ÚJRA", "ÚJRA"),
                 show="R", box="R.fields[12]"),
        ],
        cta=LIVE_CTA, end_sub=("Próbáld ki", "regisztráció nélkül"),
        note="A mintaszerződés kitalált · az elemzés valódi · nem jogi tanács",
    ),

    # ───────────────────────── szimulációk ─────────────────────────
    2: dict(
        name="Belső admin agent", kind="sim", key="2",
        line="Megmutatom, hogyan viszi át egy AI az adatot a rendszereid között.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Adatot visz át a rendszereid között, és jelentést állít össze.", cap=("ADATOT VISZ ÁT", "ÁT"),
                 show="I", box="I.desc"),
            dict(say="Tizennyolc tétel vár átvezetésre.", cap=("18 TÉTEL VÁR", "18"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Szállítólevélből számla, bevételezésből készlet.", cap=("SZÁLLÍTÓLEVÉLBŐL SZÁMLA", "SZÁMLA"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Tizenhat tétel kész. Kettőnél eltérést talált.", cap=("16 KÉSZ, 2 ELTÉRÉS", "2 ELTÉRÉS"),
                 show="D", box="D.afterHead", focus=["D.afterHead", "D.closing"], ding=True),
            dict(say="Ezeket nem javítja ki magától: ember nézi meg, vagy jóváhagyásra vár.", cap=("EMBER NÉZI MEG", "EMBER"),
                 show="D", box="D.picks"),
        ],
    ),
    3: dict(
        name="Kutatási monitor", kind="sim", key="3",
        line="Megmutatom, hogyan figyeli egy AI a konkurenciát helyetted.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Hat forrást figyel: árlistát, jogszabályt, közbeszerzést, híreket.", cap=("HAT FORRÁST FIGYEL", "HAT"),
                 show="I", box="I.grid"),
            dict(say="Elindítom a heti figyelést.", cap=("HETI FIGYELÉS", "HETI"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Egy dolog történt a héten: a fő versenytárs tizenkét százalékkal emelt árat.", cap=("+12% A VERSENYTÁRSNÁL", "+12%"),
                 show="D", box="D.afterHead", focus=["D.afterHead", "D.closing"], ding=True),
            dict(say="Megmutatja, hol látta: frissült az árlista.", cap=("MEGMUTATJA A FORRÁST", "FORRÁST"),
                 show="D", box="D.picks"),
            dict(say="A többi öt forráson nem történt semmi, ezért nem szólt.", cap=("CSAK AKKOR SZÓL, HA KELL", "HA KELL"),
                 show="D", box="D.closing"),
        ],
    ),
    4: dict(
        name="Ügyfélszolgálati agent", kind="sim", key="4",
        line="Megmutatom, hogyan válaszol egy AI az ügyfeleidnek.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="A tudásbázis: háromszáznegyven oldalnyi saját dokumentum.", cap=("340 OLDAL DOKUMENTUM", "340"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Az ügyfél kérdezi: meddig érvényes a garancia?", cap=("MEDDIG ÉRVÉNYES A GARANCIA?", "GARANCIA?"),
                 tap="I.start", run=True, box="R.chips[0]", focus="R.grid"),
            dict(say="Huszonnégy hónap, kiterjesztéssel harminchat.", cap=("24 HÓNAP, KITERJESZTVE 36", "24"),
                 show="D", box="D.afterHead", ding=True),
            dict(say="Ott a forrás is, oldalszámmal.", cap=("FORRÁS, OLDALSZÁMMAL", "OLDALSZÁMMAL"),
                 show="D", box="D.picks"),
            dict(say="Amire a dokumentumokban nincs válasz, azt átadja egy kollégának.", cap=("ÁTADJA EGY KOLLÉGÁNAK", "KOLLÉGÁNAK"),
                 show="D", box="D.bar"),
            dict(say="Amit nem tud, azt nem találja ki.", cap=("NEM TALÁL KI SEMMIT", "NEM"),
                 show="D", box="D.closing"),
        ],
    ),
    5: dict(
        name="Tartalom-agent", kind="sim", key="5", extra=("P",),
        line="Megmutatom, hogyan ír egy AI a te hangodon.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Megadod a briefet: tavaszi akció, mínusz húsz százalék.", cap=("A BRIEF: TAVASZI AKCIÓ", "BRIEF:"),
                 show="I", box="I.chips[0]", focus="I.grid"),
            dict(say="Mellé a korábbi szövegeidet: ebből tanulja a hangnemet.", cap=("TANULJA A HANGNEMED", "HANGNEMED"),
                 show="I", box="I.chips[1:4]", focus="I.grid"),
            dict(say="Megírja a hírlevelet.", cap=("MEGÍRJA A HÍRLEVELET", "HÍRLEVELET"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Kész, a te hangodon.", cap=("KÉSZ, A TE HANGODON", "TE"),
                 show="D", box="D.afterHead", ding=True),
            dict(say="De nem megy ki magától: jóváhagyásra vár.", cap=("JÓVÁHAGYÁSRA VÁR", "JÓVÁHAGYÁSRA"),
                 show="D", box="D.bar"),
            dict(say="Csak akkor megy ki, ha te jóváhagyod.", cap=("TE HAGYOD JÓVÁ", "TE"),
                 tap="D.approve", show="P", box="P.apprMsg", focus="P.approveBox"),
        ],
    ),
    8: dict(
        name="Pénzügyi asszisztens", kind="sim", key="8",
        line="Megmutatom, hogyan rendezi egy AI a költségeidet.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Kétszáznegyven banki tranzakció egy hónapból.", cap=("240 TRANZAKCIÓ", "240"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Kategóriába sorolja mindet.", cap=("KATEGÓRIÁBA SOROLJA", "KATEGÓRIÁBA"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Egy kategória kiugrik: a szoftver-előfizetések száznyolcvan százalékkal nőttek.", cap=("+180% SZOFTVERRE", "+180%"),
                 show="D", box="D.bar", focus=["D.afterHead", "D.picks"], ding=True),
            dict(say="Megmutatja, mi van mögötte. Az egyik tétel dupla számlázás, az gyanús.", cap=("DUPLA SZÁMLÁZÁS", "DUPLA"),
                 show="D", box="D.picks[2]", focus="D.picks"),
            dict(say="Minden szám mögött ott a forrássor.", cap=("OTT A FORRÁSSOR", "FORRÁSSOR"),
                 show="D", box="D.closing"),
        ],
    ),
    9: dict(
        name="Toborzási agent", kind="sim", key="9",
        line="Megmutatom, hogyan szűri egy AI a jelentkezőket.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Hatvan önéletrajz egy pozícióra.", cap=("60 ÖNÉLETRAJZ", "60"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Előre megadott szempontok szerint szűri őket.", cap=("MEGADOTT SZEMPONTOK SZERINT", "SZEMPONTOK"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Nyolc jelölt jutott tovább, mindegyik mellett az indoklás.", cap=("8 JELÖLT, INDOKLÁSSAL", "8"),
                 show="D", box="D.picks", focus=["D.afterHead", "D.picks"], ding=True),
            dict(say="De senkit nem utasít el: mind a hatvan megnézhető, a döntést ember hozza.", cap=("A DÖNTÉST EMBER HOZZA", "EMBER"),
                 show="D", box="D.bar"),
            dict(say="Minden döntésről audit-napló készül.", cap=("AUDIT-NAPLÓ", "AUDIT-NAPLÓ"),
                 show="D", box="D.closing"),
        ],
    ),
    10: dict(
        name="IT-üzemeltető agent", kind="sim", key="10",
        line="Megmutatom, hogyan figyeli egy AI a rendszereidet.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Kétezer-négyszáz log sor egyetlen éjszaka alatt.", cap=("2400 LOG SOR", "2400"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Osztályozza a riasztásokat.", cap=("OSZTÁLYOZZA A RIASZTÁSOKAT", "RIASZTÁSOKAT"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Két ismert hibát magától javított: újraindította a szolgáltatást.", cap=("2 HIBÁT MAGA JAVÍTOTT", "JAVÍTOTT"),
                 show="D", box="D.picks[0:2]", focus=["D.afterHead", "D.picks"], ding=True),
            dict(say="Egy ismeretlen adatbázis-hibánál viszont felébresztett.", cap=("ISMERETLENNÉL SZÓL", "SZÓL"),
                 show="D", box="D.picks[2]"),
            dict(say="Reggel kétezer-négyszáz sor helyett három mondat.", cap=("3 MONDAT 2400 SOR HELYETT", "3 MONDAT"),
                 show="D", box="D.closing", focus=["D.afterHead", "D.closing"]),
        ],
    ),
    11: dict(
        name="Multi-agent rendszer", kind="sim", key="11",
        line="Megmutatom, hogyan dolgozik együtt több AI agent.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Egy ajánlatkérés, nyolc lépés, több agent.", cap=("8 LÉPÉS, TÖBB AGENT", "TÖBB AGENT"),
                 show="I", box="I.grid"),
            dict(say="Dokumentum-elemző, pénzügyi ellenőrzés, ajánlatíró.", cap=("ÁTADJÁK EGYMÁSNAK", "ÁTADJÁK"),
                 tap="I.start", run="R1:R4", focus="R.grid"),
            dict(say="A független ellenőr hibát talál: rossz ÁFA-kulcs. Visszaküldi.", cap=("HIBA: ROSSZ ÁFA-KULCS", "HIBA:"),
                 run="R5:R5", box="R.chips[4]", focus="R.grid"),
            dict(say="Javítás után ember hagyja jóvá.", cap=("EMBER HAGYJA JÓVÁ", "EMBER"),
                 run="R6:", box="R.chips[5:7]", focus="R.grid"),
            dict(say="Minden lépés naplózva, másodpercre.", cap=("MINDEN LÉPÉS NAPLÓZVA", "NAPLÓZVA"),
                 show="D", box="D.audit", ding=True),
            dict(say="Az ellenőrzést nem az végzi, aki írta.", cap=("MÁS ELLENŐRIZ, MINT AKI ÍRTA", "MÁS"),
                 show="D", box="D.closing"),
        ],
    ),
    12: dict(
        name="NIS2-megfelelési agent", kind="sim", key="12",
        line="Megmutatom, hogyan gyűjti egy AI a NIS2-bizonyítékokat.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Negyvenhat követelmény, amit egy NIS2-audit kér.", cap=("46 KÖVETELMÉNY", "46"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Havonta végignézi mindet.", cap=("HAVONTA VÉGIGNÉZI", "HAVONTA"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Három hiányosság, ami auditon elbukna.", cap=("3 HIÁNYOSSÁG", "3"),
                 show="D", box="D.afterHead", focus=["D.afterHead", "D.closing"], ding=True),
            dict(say="Például egy távozott kolléga, akinek még él a rendszergazdai joga.", cap=("TÁVOZOTT KOLLÉGA JOGA", "JOGA"),
                 show="D", box="D.picks[0]"),
            dict(say="A többi negyvenhárom követelményhez megvan a bizonyíték, dátummal.", cap=("BIZONYÍTÉK, DÁTUMMAL", "BIZONYÍTÉK"),
                 show="D", box="D.closing"),
            dict(say="Nem véd: bizonyít.", cap=("NEM VÉD — BIZONYÍT", "BIZONYÍT"),
                 show="D", box="D.desc", focus="D.desc"),
        ],
    ),
    13: dict(
        name="Értékesítő agent", kind="sim", key="13",
        line="Megmutatom, hogyan keres egy AI új ügyfeleket.",
        hook_hi={"AI", "NÉZD!"},
        beats=[
            dict(say="Hatvan cég a célpiacodon.", cap=("60 CÉG A CÉLPIACODON", "60"),
                 show="I", box="I.head", focus="I.grid"),
            dict(say="Elolvassa az oldalukat, és megnézi, hol akad el náluk az ügyfél.", cap=("ELOLVASSA AZ OLDALUKAT", "OLDALUKAT"),
                 tap="I.start", run=True, focus="R.grid"),
            dict(say="Három levél vár a jóváhagyásodra.", cap=("3 LEVÉL JÓVÁHAGYÁSRA", "JÓVÁHAGYÁSRA"),
                 show="D", box="D.afterHead", focus=["D.afterHead", "D.closing"], ding=True),
            dict(say="Mindegyik egy valódi megfigyelésre épül.", cap=("VALÓDI MEGFIGYELÉS", "VALÓDI"),
                 show="D", box="D.picks[0]"),
            dict(say="Aki nemet mond, annak többet nem ír. Semmi nem megy ki jóváhagyás nélkül.", cap=("JÓVÁHAGYÁS NÉLKÜL SEMMI", "SEMMI"),
                 show="D", box="D.closing"),
        ],
    ),
}

for _k, _a in AGENTS.items():
    if _a["kind"] == "sim":
        _a.setdefault("src", "sims")
        _a.setdefault("first", "I")
        _a.setdefault("cta", SIM_CTA)
        _a.setdefault("end_sub", ("Nézd meg működés közben", "az agent kártyáján"))
        _a.setdefault("note", SIM_NOTE)

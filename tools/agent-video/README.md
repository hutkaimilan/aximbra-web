# AXIMBRA agentvideók: átadás

Egy agent, egy videó, 9:16, magyarul, Instagram Reelsre és LinkedInre. Felépítés:

1. **Horog:** Axi (Veo-klip a Geminiből) kimondja az agent nevét és azt, amit bemutat. A telefonja zöld kijelzőjén az aximbra.hu agentkártyája látszik.
2. **Bemutató:** az aximbra.hu valódi képernyője teljes képen, narrációval, felirattal, kiemelő kerettel és koppintással.
3. **Zárókép:** AXIMBRA, aximbra.hu és a felhívás.

Két rész következik:

- **A rész:** a Gemini-promptok. Ezeket a tulajdonos másolja be a Geminibe.
- **B rész:** mit csináljon Claude a kész klipekkel.

---

## A rész: Gemini (Veo) promptok

**Hogyan generáld:**
- Mindegyiket KÜLÖN generáld, **Álló (9:16)** formátumban.
- **Töltsd fel kiinduló képnek** a mappában lévő `axi_referencia.png`-t. Enélkül a Veo minden klipben más arcú Axit rajzol.
- A kész klipet töltsd fel a Claude-beszélgetésbe, vagy küldd el magadnak e-mailben.

Minden prompt ugyanaz; csak az idézőjelbe tett magyar mondat változik, ezt a `{MONDAT}` helyére kell beírni:

```
Vertical 9:16, 8 seconds, 3D animated feature-film style (Pixar-like), cinematic. Use the uploaded reference image as the exact character: same face, glasses, beard, hair, blazer and headset. Character: Axi, a friendly man in his mid-30s, soft rounded face, warm brown eyes, short neat dark-brown hair, short well-groomed dark beard, thin dark metal-frame rectangular glasses, navy blue unstructured blazer over a plain light-grey t-shirt, small wireless headset with a glowing cyan light on his right ear. Setting: a real small-business office, wooden desk, beige coffee mug with the word "AXIMBRA" visible, warm light with cyan accent light. Action: Axi holds a modern smartphone in his right hand up next to his face with the screen facing the camera, and looks straight into the lens with a relaxed, confident smile, natural eyebrows, calm head, no nodding. The phone screen is a flat, solid, bright chroma-key green (#00FF00), evenly lit, no reflections, no icons, no text, fully visible and not covered by his fingers. He holds the phone very still. He speaks Hungarian in a calm, warm, friendly conversational voice, at an even volume from the first word to the last: no shouting, no exclamation, no dramatic pause, no emphasis on any single word, clear lip movement: "{MONDAT}" Light upbeat background music. Static camera. No subtitles, no on-screen text except the mug.
```

A `{MONDAT}` helyére, agentenként:

| # | Agent | {MONDAT} |
|---|---|---|
| 00 | E-mail rendező | Ez az Aximbra e-mail rendező agentje. Megmutatom, hogyan válogatja szét a leveleidet. |
| 01 | Érdeklődő-minősítő | Ez az Aximbra érdeklődő-minősítő agentje. Megmutatom, hogyan rangsorolja az érdeklődőidet. |
| 02 | Belső admin agent | Ez az Aximbra belső admin agentje. Megmutatom, hogyan viszi át az adatot a rendszereid között. |
| 03 | Kutatási monitor | Ez az Aximbra kutatási monitora. Megmutatom, hogyan figyeli helyetted a konkurenciát. |
| 04 | Ügyfélszolgálati agent | Ez az Aximbra ügyfélszolgálati agentje. Megmutatom, hogyan válaszol az ügyfeleidnek. |
| 05 | Tartalom-agent | Ez az Aximbra tartalom-agentje. Megmutatom, hogyan ír a te hangodon. |
| 06 | Webshop-asszisztens | Ez az Aximbra webshop-asszisztense. Megmutatom, hogyan válaszol a vásárlóidnak. |
| 07 | Dokumentum-elemző | Ez az Aximbra dokumentum-elemzője. Megmutatom, hogyan olvas át egy szerződést. |
| 08 | Pénzügyi asszisztens | Ez az Aximbra pénzügyi asszisztense. Megmutatom, hogyan rendezi a költségeidet. |
| 09 | Toborzási agent | Ez az Aximbra toborzási agentje. Megmutatom, hogyan szűri a jelentkezőket. |
| 10 | IT-üzemeltető agent | Ez az Aximbra IT-üzemeltető agentje. Megmutatom, hogyan figyeli a rendszereidet. |
| 11 | Multi-agent rendszer | Ez az Aximbra multi-agent rendszere. Megmutatom, hogyan dolgozik együtt több agent. |
| 12 | NIS2-megfelelési agent | Ez az Aximbra NISZ kettő megfelelési agentje. Megmutatom, hogyan gyűjti a bizonyítékot az auditra. |
| 13 | Értékesítő agent | Ez az Aximbra értékesítő agentje. Megmutatom, hogyan keres neked új ügyfeleket. |

Az „Egyedi agent”-nek nincs demója, ahhoz nem készül videó.

---

## B rész: utasítás Claude-nak

> Másold be ezt a részt az új beszélgetés elejére, a klipekkel együtt.

### Feladat

Minden agenthez egy **45–60 másodperces**, részletes bemutatóvideó készül, magyarul. Egyszerre **csak egyet** csinálj:
1. Elkészíted a videót.
2. Ellenőrzöd.
3. Elküldöd a tulajdonosnak.
4. Megvárod, hogy azt írja, jó. Csak utána kezded a következőt, sorszám szerint (00, 01, 02, …).

### Az eszközök

Minden ebben a mappában van: `tools/agent-video/` az `aximbra-web` repóban, a `claude/funny-bell-rihxq2` ágon. Ha nincs meg: `git fetch origin claude/funny-bell-rihxq2 && git checkout claude/funny-bell-rihxq2`.

| Fájl | Mire való |
|---|---|
| `capture/sims_cap.js` | Rögzíti a szimulációs agentek kártyáját az aximbra.hu-ról (mobil nézet, 2x felbontás): induló állapot, futás lépésenként, kész, jóváhagyva. Kimenet: `s{k}_*.png`, `sims.json` (elemkeretek, szövegek). |
| `capture/live_cap.js` | Lefuttatja és rögzíti az élő demókat. Agentek: 1 érdeklődő-minősítő, 6 webshop, 7 dokumentum-elemző. Kimenet: `l{k}_*.png`, `live.json`, benne a valódi futás eredménye. |
| `capture/states.js` | Az e-mail agent élő demójának rögzítése (`aximbra.hu/demo/email-agent`). |
| `cfg.py` | Agentenkénti forgatókönyv: ütemek (narráció, felirat, állapot, kiemelés, koppintás), zárómondat, lábjegyzet. **Ezt kell bővíteni.** |
| `tts_all.py`, `tts.py` | Narráció edge-tts-sel, `hu-HU-TamasNeural` hangon, `+8%` tempóval. |
| `identify.py` | Eldönti, melyik klip melyik agenthez tartozik, a klip hangja alapján (faster-whisper). |
| `agentvid.py` | A videóépítő: `python3 agentvid.py <agent> <klip.mp4> [kimenet.mp4] [--preview]` |
| `email_ad_build.py` | A régi, jóváhagyott e-mail-reklám építője. Mintának jó a 00-ás agenthez. |

Futtatás a mappában:

```bash
python3 capture/... vagy node capture/...
python3 identify.py klip.mp4
python3 tts_all.py <k>
python3 agentvid.py <k> klip.mp4 kimenet.mp4
```

Ezek kellenek hozzá: Python 3 (numpy, pillow, edge-tts, faster-whisper), node + playwright (chromium), ffmpeg, Inter és DejaVu betűk (`/usr/share/fonts/...`).

### Ami az építőben már kész és bevált (ne rontsd el)

- **Telefonkép:** a zöld kijelzőt a négy szélére illesztett egyenesek követik. Ez az ujjakra és a lekerekített sarkokra is pontos; a kép kitölti a kijelzőt.
- **Horog:**
  - Axi a klip **saját hangján** beszél, így a száj szótagra pontos. TTS-t soha ne tegyél Axi szájába, ezt a tulajdonos elutasította.
  - A beszéd határa a felismert első és utolsó szó, mert a hangerő szerinti becslés a háttérzenét is beszédnek venné.
  - A szintkiegyenlítő lehalkítja a kiabált szótagokat.
  - Az **„élőben” szó SOHA nem kerülhet a videóba**: se hangban, se feliratban, se narrációban. Az építő automatikusan kivágja a horog végéről.
- **Feliratok:** InterDisplay Black, a kép 61,5%-ánál, a kiemelt szó cián. A felirat kikerüli az épp kiemelt keretet.
- **Kamera:** a kártya belsejét tölti ki (1,20× nagyítás, a webshopnál 1,02×), betű sehol nem vágódik le, és nem marad üres sáv.
- **Töltés:** a gépi várakozást gyorsítja, és ezt egy „GYORSÍTVA ›››” jel mutatja.
- **Zárókép:** agentnév, AXIMBRA, aximbra.hu, felhívás, lábjegyzet és „A videó AI-val készült”. A sarokban végig „AI-GENERÁLT” felirat.

### Amit most bővíteni kell: hosszabb, részletesebb videó

A `cfg.py` ütemeit agentenként erre a szerkezetre bővítsd. Az időzítést az építő a felolvasás hosszából magától számolja.

1. **Horog** (Veo-klip, kb. 5 másodperc): Axi kimondja az agent nevét.
2. **Bemutatkozás** (a kártya teteje):
   - az agent neve, kiemelve a `title` keret;
   - mit csinál, a kártya leírásával (`desc`), egy-két mondatban;
   - kinek szól;
   - ár és átfutás a kártyáról (`meta`), például „Négyszázezer és 1,2 millió forint között, 2–3 hét alatt kész.” Csak azt mondd, ami a kártyán áll.
3. **Működés közben:**
   - **Élő agentek** (00 e-mail, 01 érdeklődő, 06 webshop, 07 dokumentum): a valódi demó futása lépésről lépésre. Minden számot a rögzített futás eredményéből olvass ki, mert futásonként változnak.
   - **Szimulációk** (02–05, 08–13): az oldal szimulációja lépésenként; a lábjegyzetben „Illusztráció magyar mintaadatokkal”.
4. **Korlátok és emberi döntés:** mit nem csinál magától, mit kell jóváhagyni, mit ad át embernek. Csak az oldal saját szövegeiből.
5. **Zárás:**
   - élő agenteknél: „Próbáld ki regisztráció nélkül: aximbra pont hu.”;
   - szimulációknál: „Nézd meg működés közben: aximbra pont hu.”.

A 00-ás e-mail agenthez a `cfg.py`-ban még nincs bejegyzés. A `capture/states.js` és az `email_ad_build.py` alapján vedd fel. Ennél a jóváhagyott reklám tartalma a minta: az e-mail kinyitása, miért sürgős, mi a következő lépés, választervezet hangnemválasztással, Gmail-vázlat vagy küldés jóváhagyással.

### Szabályok (a tulajdonos kérései, kötelezők)

- **Nincs kitalált szám vagy állítás.** Csak az mondható el, ami az oldalon vagy a rögzített futásban látszik.
- A szimuláció illusztráció; ezt kimondani nem kell, de a lábjegyzetben ott kell lennie.
- A NIS2 agentről soha ne mondd, hogy véd: „Nem véd, bizonyít.”
- Ne használd a „Beszéljünk 20 percet” felhívást.
- Az „élőben” szó semmilyen formában nem szerepelhet.
- A narráció tegez, mert az oldal is tegez.
- Ha a Veo-klipben Axi bólogat, kiabál vagy rossz a zöld kijelző, szólj, és ne renderelj belőle.
- A klip párosítása: `python3 identify.py klip.mp4`. Ha bizonytalan, kérdezd meg, melyik agenté.
- Személyes adat (e-mail-cím, telefonszám) nem kerülhet a videóba.

### Ellenőrzés minden videó előtt

1. Készíts kontaktlapot másodpercenként egy képkockával, és nézd végig: levágott szöveg, rossz keret, üres sáv, telefonkép elcsúszása.
2. Írasd le a hangot faster-whisperrel: a narráció hibátlan, és nincs benne „élőben”.
3. Csak utána küldd el a tulajdonosnak.

### Ismert buktató

A dokumentum-elemző élő demója, amikor a Gemini túlterhelt (503-as hibát ad), a mezőkre azt írja, hogy „nem található a dokumentumban”. Ilyen futást ne rögzíts: a `live_cap.js` addig ismétli, amíg minden mező megvan.

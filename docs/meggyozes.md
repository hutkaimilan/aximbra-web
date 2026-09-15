# Meggyőzéstechnika az AXIMBRA oldalán — mi került be, mi nem, és miért

Ez nem stílusdokumentum. Az oldalon minden meggyőzéstechnikai döntés mögött egy
konkrét kutatási megállapítás áll, és mindegyikhez tartozik egy indok arra is,
amit **nem** csináltunk. Aki a következő körben hozzányúl a laphoz, itt találja
meg, hogy egy-egy szakasz miért ott van, ahol.

## A vezérelv

> Ha egy szálloda azt írja, hogy már csak egy szoba van, és ez **igaz**, az
> meggyőzés. Ha nem igaz, az manipuláció.
>
> — Újszászi Bogár László, meggyőzéstechnika-kutató (ELTE PhD, Corvinus)

Ez a szabály nem etikai díszítés, hanem működési korlát. Az oldal kiírja
magáról, hogy nincs rajta visszaszámláló, kitalált referencia és csak ma
érvényes ár (`NoTricks`). Ettől a pillanattól kezdve **egyetlen hamis állítás
az összes igazat is értékteleníti** — a látogatónak nincs módja szétválogatni,
melyiknek higgyen.

Gyakorlati következmény: ha egy technika alkalmazásához ki kellene találni egy
számot, egy referenciát vagy egy határidőt, a technika nem alkalmazható. Nem
azért, mert csúnya, hanem mert a lap egy másik szakasza már ígéretet tett az
ellenkezőjére.

## Ami be van építve

### 1. Beoltás (prolépszisz) — `Objections.jsx`

**A megállapítás.** A retorika legrégebbi ismert fogása: az ellenérvet te hozod
fel, mielőtt a másik megtenné. Két hatása van: az érv a te megfogalmazásodban
hangzik el, és aki kimondja a saját gyenge pontját, arról a másik azt
feltételezi, hogy a többit sem titkolja.

**Amit csinál a lapon.** Hét kérdés a vevő szavaival, közvetlenül a bizonyíték
után — ott fogalmazódnak meg. A negyedik („mi van, ha egy év múlva
abbahagyod?”) szándékosan bent van: egy húszéves, egyszemélyes műhelynél ez a
legnagyobb ki nem mondott ellenvetés. Kihagyni nem azt jelenti, hogy nem merül
fel, csak azt, hogy a döntés pillanatában merül fel, ahol már nincs rá válasz.

**Amit ne csinálj vele.** Egyik válasz sem tagad. Ha valaki „erősebbre” írja
őket úgy, hogy a kifogás már nem hangzik el őszintén, a szakasz hatása az
ellenkezőjére fordul.

### 2. Pratfall-hatás — `Founder.jsx`, `Objections.jsx`

**A megállapítás.** Aronson (1966): egy már kompetensnek látott szereplő egy
apró, látható hibától **rokonszenvesebb** lesz. A feltétel kötelező: a
kompetenciának előbb meg kell lennie, különben a hiba csak hiba.

**Amit csinál a lapon.** A bemutatkozás kiírja az életkort és azt, hogy ez egy
éve megy. Ezért áll a bemutatkozás a négy ellenőrizhető állítás **után**: előbb
a kompetencia, utána a gyenge pont. Fordított sorrendben ez a technika nem
működik.

### 3. Sorrend: bizonyíték az ár előtt — `App.js`

**A megállapítás.** Az árazás eddig az esettanulmány és a referenciák előtt
állt. Egy szám, amihez a nézőnek nincs mihez viszonyítania, mindig drágának
tűnik.

**A jelenlegi sorrend, és miért ez:**

| # | Szakasz | Mit csinál |
|---|---------|------------|
| 1 | `Proof` | Amit a látogató **ellenőrizni** tud — előbb figyelem, rögtön utána bizalom |
| 2 | `Agents` | Mit építünk |
| 3 | `CaseStudy` | Hogy működik élesben |
| 4 | `References` | Milyen munka néz ki |
| 5 | `Objections` | Az ellenvetések, ahol megfogalmazódnak |
| 6 | `Process` | Hogyan dolgozunk — az emberi kapu itt válasz a 3. kifogásra |
| 7 | `Founder` | Ki csinálja |
| 8 | `Pricing` | Az ár, amikor már van mihez viszonyítani |
| 9 | `NoTricks` | Amit nem csinálunk — a nyomásgyakorlás szokásos helyén |
| 10 | `FirstStep` | A legkisebb következő lépés |
| 11 | `Contact` | Kapcsolat |

Teszt őrzi (`test_the_evidence_comes_before_the_price`).

### 4. Kontroll a folyamat végén — 07. lépés

**A megállapítás.** Az orvosi mintát követő modell három pillére: anamnézis,
terápia, **kontrollvizsgálat**. A harmadik nélkül a második nem ellenőrizhető.

**Amit csinál a lapon.** Az első lépés felméri, hova megy el az idő; a hetedik
ugyanazt méri vissza. Ez **üzleti vállalás**, nem szövegezés: minden projektnél
meg kell csinálni.

### 5. Döntési költség csökkentése — `FirstStep.jsx`

**A megállapítás.** Egy döntésnek ára van azon felül is, amit a számla mutat:
ki kell találni, meg kell védeni mások előtt, és vissza kell csinálni, ha rossz
volt. Aki elsőre ajánlatot kér, mindhármat megelőlegezi.

**Amit csinál a lapon.** Húszperces felmérés prezentáció és csomagajánlat
nélkül, azzal a kimondott vállalással, hogy ha nem térül meg, azt megmondjuk.
Szintén vállalás, nem szöveg.

### 6. Hitelesség a láblécben — `Contact.jsx`

**A megállapítás.** A Stanford háromévnyi, több mint 4500 emberrel végzett
vizsgálata: a hitelesség megítélése elsősorban azon múlik, **hogy néz ki** az
oldal, utána azon, hogy ellenőrizhető-e, ki áll mögötte. Az irányelvekből négy
pont a láblécre szól: látszódjon, hogy valódi szervezet áll mögötte; legyen
könnyű kapcsolatba lépni; legyen nevesített felelős; legyen könnyű ellenőrizni
az állításokat.

**Amit csinál a lapon.** A lábléc eddig ennyi volt: „AXIMBRA · Budapest ·
aximbra.hu”. Most név, jogi státusz, teljes postai cím, e-mail, telefon és a
jogi oldalak. Az adatok a `legal.js`-ből és a `contact.js`-ből jönnek, nem ide
írva — ugyanaz áll itt, mint az impresszumban.

**Amit szándékosan NEM ír ki.** Az adószám sora **eltűnik**, amíg nincs
adószám. A „bejegyzés alatt” is állítás lenne, és nem tudjuk, igaz-e.

### 7. Érvsűrűség a magasan érintett vevőnek

**A megállapítás.** Az Elaboration Likelihood Model szerint a magasan érintett
döntéshozó a **központi utat** járja: az érvek minőségén és mennyiségén múlik a
meggyőzés, nem a felületi jeleken (logófal, jelvények, díjak). Egy több
milliós B2B döntés magas érintettség.

**Következmény.** Ezen a lapon a hosszabb, konkrétabb szöveg **jobb**, nem
rosszabb. Aki „letisztultabbra” rövidíti az ellenvetéseket vagy a folyamatot,
az a fő meggyőző erőt veszi ki belőle.

## Ami szándékosan kimaradt

| Technika | Miért nem |
|---|---|
| Visszaszámláló, „már csak 2 hely” | Nincs annyi hely, és nem ma éjfélkor fogyna el. A `NoTricks` ki is írja, hogy ilyen itt nincs. |
| Logófal, ügyféllogók | Nincs ügyfél. Kitalált logó a legkönnyebben leleplezhető hazugság. |
| Álértékelések, csillagok | Ugyanaz. |
| Kilépési felugró ablak | Nyomás. A tukmálás pont az a hibamód, amitől a vevő elmenekül. |
| Konkrét számok a szakirodalomból az oldalon | Az elsődleges forrásokat (ELTE-tézis, *Economica*-tanulmány) nem sikerült elolvasni, tehát nem ellenőrzött szám lenne. |
| A kutatók nevének kiírása az oldalra | „X kutatására építünk” olyan jóváhagyást sugallna, ami nincs meg. Az elveket alkalmazzuk, a nevüket nem használjuk fel. |

## Ami hiányzik, és nem kód kérdése

Ezek nélkül a meglévő technikák csak a **meglévő** bizalmat tudják
maximalizálni — újat nem tudnak teremteni.

1. **Egy valódi ügyféleredmény.** A leghiányzóbb elem. Egy mondat kellene:
   *egy cégnél X feladatra hetente Y óra ment el, a bevezetés után Z.* A
   társadalmi bizonyíték a legerősebb meggyőző elv, és jelenleg **nulla** van
   belőle. Kitalálni nem lehet.
2. **Fotó.** Nevesített, arccal vállalt felelős — a Stanford-irányelvek közt is
   szerepel, egyszemélyes műhelynél pedig a bizalom legolcsóbb forrása.
3. **Adószám.** Amíg nincs, a lábléc és az impresszum hallgat róla. Magyar
   oldalon ez hosszú távon nem tartható.
4. **Magyar telefonszám.** A láblécben most az amerikai Twilio-tesztvonal áll,
   kiírva, hogy az az agent demószáma. Egy budapesti vállalkozásnál egy elérhető
   magyar szám érdemi hitelességi nyereség lenne.
5. **Valódi kapacitásszám.** „Egyszerre kevés projekt fér be” igaz, de
   homályos. Ha a szám konkrét (*egyszerre kettő*), az valódi, ellenőrizhető
   korlát — és a hiteles szűkösség az egyetlen szűkösség, ami használható.

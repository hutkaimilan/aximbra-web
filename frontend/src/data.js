export const AGENTS = [
  { title: "E-mail rendező", badge: "Élő", live: true, demo: "email", desc: "Beolvassa a beérkező leveleket, kategóriába sorolja, sürgősséget állapít meg, és megmondja, kihez tartozik.", price: "150–400 eFt", lead: "2–4 hét" },
  { title: "Érdeklődő-minősítő", badge: "Élő", live: true, demo: "lead", desc: "Végignézi a beérkező érdeklődést, pontozza, és megmondja, mit érdemes vele kezdeni — ma vagy három hónap múlva.", price: "400 eFt – 1,2 MFt", lead: "3–5 hét" },
  { title: "Belső admin agent", badge: "Bemutató", live: false, desc: "Adatot visz át rendszerek között, jelentést állít össze, űrlapot tölt ki. A láthatatlan munka, ami senkinek nem hiányzik.", price: "150–400 eFt", lead: "2–4 hét" },
  { title: "Kutatási monitor", badge: "Bemutató", live: false, desc: "Figyeli a versenytársakat, a jogszabályt vagy a piacot, és csak akkor szól, ha valóban történt valami.", price: "150–400 eFt", lead: "2–4 hét" },
  { title: "Ügyfélszolgálati agent", badge: "Bemutató", live: false, desc: "A saját dokumentumaidból válaszol, forrásmegjelöléssel. Amit nem tud, azt átadja embernek — nem talál ki.", price: "1,5–4 MFt", lead: "6–10 hét" },
  { title: "Tartalom-agent", badge: "Bemutató", live: false, desc: "Egy hangnemre betanítva ír: hírlevél, termékleírás, közösségi poszt. A jóváhagyás marad nálad.", price: "400 eFt – 1,2 MFt", lead: "2–3 hét" },
  { title: "Webshop-asszisztens", badge: "Bemutató", live: false, desc: "Terméket ajánl, készletet néz, rendelést követ. A kosárelhagyás ellen dolgozik, nem a látogató ellen.", price: "600 eFt – 1,5 MFt", lead: "3–5 hét" },
  { title: "Dokumentum-elemző", badge: "Bemutató", live: false, desc: "Szerződést, számlát, ajánlatot olvas, és kiszedi belőle azt a hét mezőt, ami miatt valaki eddig végigolvasta.", price: "2–4 MFt", lead: "6–8 hét" },
  { title: "Pénzügyi asszisztens", badge: "Bemutató", live: false, desc: "Költséget kategorizál, eltérést jelez, riportot állít össze. Minden állítás mögött ott a forrássor.", price: "2–4 MFt", lead: "6–8 hét" },
  { title: "Toborzási agent", badge: "Bemutató", live: false, desc: "Önéletrajzot előszűr strukturált szempontok szerint. Az EU AI Act miatt audit-napló és emberi felülbírálat is benne van.", price: "1,7–3,9 MFt", lead: "3–4 hét + jogi" },
  { title: "IT-üzemeltető agent", badge: "Bemutató", live: false, desc: "Logot néz, riasztást osztályoz, ismert hibára lefuttatja a javítást. Amit nem ismer, azzal felébreszt téged.", price: "600 eFt – 2 MFt", lead: "3–6 hét" },
  { title: "Multi-agent rendszer", badge: "Bemutató", live: false, desc: "Több agent egy folyamaton, átadásokkal és ellenőrzési pontokkal. Akkor van értelme, ha a folyamat tényleg összetett.", price: "6–15 MFt", lead: "10–16 hét" },
];

export const STEPS = [
  { n: "01", title: "Munkafolyamat feltérképezés", desc: "Megnézzük, hova megy el az idő. Nem azt kérdezzük, mit szeretnél automatizálni, hanem hogy melyik feladat ismétlődik hetente ötvenszer." },
  { n: "02", title: "Specifikáció, sémával", desc: "A megállapodás gépi olvasható formában rögzül: mi a bemenet, mi a kimenet, mi számít hibának. Ez a dokumentum később a teszt alapja." },
  { n: "03", title: "Építés izolált környezetben", desc: "Minden projekt saját, elzárt futtatókörnyezetet kap. Egy hiba nem tud átgyűrűzni más ügyfél rendszerére." },
  { n: "04", title: "Független ellenőrzés", desc: "Az elkészült munkát nem az ellenőrzi, aki írta. Külön ellenőrző fut rá, üres kontextussal, csak olvasási joggal — így nem tudja megvédeni a saját döntéseit." },
  { n: "05", title: "Emberi jóváhagyás", desc: "Semmi nem megy ki jóváhagyás nélkül. A kapu nem formalitás: itt derül ki, ha valami technikailag helyes, de üzletileg rossz.", amber: "◆ Ember dönt, nem AI" },
  { n: "06", title: "Átadás és üzemeltetés", desc: "Az agent a te infrastruktúrádon fut, a te kulcsaiddal. A havidíj a felügyeletet és a javítást fedezi, nem a hozzáférést." },
];

export const PRICING = [
  { cat: "Belső admin / kutatás", intro: "150–400 eFt", monthly: "10–30 eFt", lead: "2–4 hét" },
  { cat: "Sales-minősítő", intro: "400 eFt – 1,2 MFt", monthly: "30–85 eFt", lead: "3–5 hét" },
  { cat: "Marketing / tartalom", intro: "400 eFt – 1,2 MFt", monthly: "30–85 eFt", lead: "2–3 hét" },
  { cat: "E-commerce", intro: "600 eFt – 1,5 MFt", monthly: "30–100 eFt", lead: "3–5 hét" },
  { cat: "IT / DevOps", intro: "600 eFt – 2 MFt", monthly: "30–100 eFt", lead: "3–6 hét" },
  { cat: "Ügyfélszolgálat (RAG)", intro: "1,5–4 MFt", monthly: "20–250 eFt", lead: "6–10 hét" },
  { cat: "Dokumentum / pénzügy", intro: "2–4 MFt", monthly: "50–150 eFt", lead: "6–8 hét" },
  { cat: "Multi-agent rendszer", intro: "6–15 MFt", monthly: "80–150 eFt", lead: "10–16 hét" },
];

export const EMAIL_SAMPLES = [
  "Tisztelt Ügyfélszolgálat! A múlt héten rendelt terméket sérülten kaptam meg, a doboz be volt szakadva. Kérem, mielőbb intézkedjenek a cseréről, mert nagyon csalódott vagyok. Válaszukat sürgősen várom.",
  "Jó napot! Szeretnék árajánlatot kérni 200 db egyedi feliratozott pólóra, céges rendezvényre. A szállítást júniusra terveznénk. Milyen árakkal és határidővel tudnak dolgozni?",
  "Üdv! A számlámon szereplő összeg nem egyezik a megrendeléssel, dupla tételt látok. Meg tudnátok nézni és korrigálni? Nem sürgős, de a hónap végéig jó lenne rendezni.",
];

export const LEAD_SAMPLES = [
  "Egy 40 fős budapesti könyvelőiroda ügyvezetője keresett meg. Havonta több száz beérkező számlát dolgoznak fel kézzel, ezt szeretnék automatizálni. Van rá keret, idén szeretnék elindulni, ő dönt a beszerzésről.",
  "Egy egyetemista írt, hogy szakdolgozathoz szeretne AI agentet, ingyen. Nincs cége, nincs költségvetése, csak kíváncsi hogyan működik a technológia.",
  "Egy közepes webshop marketingese érdeklődik ügyfélszolgálati agent iránt. Még nem tudja pontosan mit szeretne, a döntést a tulajdonos hozza meg, időpont bizonytalan, de a probléma valós.",
];

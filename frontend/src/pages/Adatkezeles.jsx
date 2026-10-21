import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER, CONTROLLER_ADDRESS, LEGAL_UPDATED, PROCESSORS } from "../legal";
import { useDocumentMeta } from "../seo";
import { useLang } from "../i18n";
import PrivacyEn from "./PrivacyEn";
import PrivacyDe from "./PrivacyDe";

/**
 * Adatkezelési tájékoztató.
 *
 * Minden állítása a tényleges kódból származik — a 30 perces munkamenet, az 50
 * levél, a scope-ok, a hívás-összefoglaló e-mail —, nem egy sablonból. Ha a
 * rendszer változik, ennek is változnia kell: egy tájékoztató, ami mást ígér,
 * mint amit a kód csinál, rosszabb, mint a semmi.
 *
 * A Google korlátozott felhasználásra (Limited Use) vonatkozó nyilatkozata
 * külön szakasz, mert a restricted scope-ok verifikációjához kötelező.
 *
 * Az angol lapon (/en/adatkezeles) a fordítás jelenik meg (PrivacyEn.jsx): a
 * Google OAuth-verifikáció ellenőrei angolul olvassák. A többi nyelven marad a
 * magyar szöveg. Külön komponens, nem feltétel a hookok előtt — különben a
 * nyelvváltás a hookok számát változtatná meg.
 */
export default function Adatkezeles() {
  const { lang } = useLang();
  if (lang === "de") return <PrivacyDe lang={lang} />;
  return lang === "en" ? <PrivacyEn lang={lang} /> : <AdatkezelesHu lang={lang} />;
}

function AdatkezelesHu({ lang }) {
  useDocumentMeta({
    title: "Adatkezelési tájékoztató | AXIMBRA",
    description:
      "Milyen adatokat kezelünk a weboldalon és a bemutató agentekben, mennyi ideig, " +
      "kinek adjuk tovább, és hogyan kérheted a törlésüket.",
    path: "/adatkezeles",
    lang,
    // A magyar szöveg az irányadó; angolul csak fordítás van (PrivacyEn.jsx).
    translated: false,
  });
  // A Google-ellenőrzés közvetlen linket kap a védelmi részre (#…): akkor oda
  // görgetünk, különben a lap tetejére.
  useEffect(() => {
    const el = window.location.hash && document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (el) el.scrollIntoView(); else window.scrollTo(0, 0);
  }, []);

  return (
    <div className="legal-page">
      <header className="legal-top">
        <Link to="/" className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main">
        <h1>Adatkezelési tájékoztató</h1>
        <p className="legal-lead">
          Ez a tájékoztató azt írja le, mit csinál a rendszer <i>ténylegesen</i> — nem
          általánosságban. Ahol szám szerepel benne, az a kódban is ugyanaz a szám.
        </p>
        <p className="legal-note"><a href="#adatvedelmi-intezkedesek">→ Az érzékeny adatok védelme</a></p>

        <section>
          <h2>1. Ki kezeli az adataidat</h2>
          <dl className="legal-dl">
            <div><dt>Adatkezelő</dt><dd>{CONTROLLER.name}</dd></div>
            <div><dt>Cím</dt><dd>{CONTROLLER_ADDRESS}</dd></div>
            <div><dt>E-mail</dt><dd><a href={mailto()}>{CONTACT.email}</a></dd></div>
          </dl>
          <p className="legal-note">
            Az AXIMBRA márkanév, nem bejegyzett gazdasági társaság. Adatvédelmi
            tisztviselő kijelölése nem kötelező, és nem történt meg.
          </p>
        </section>

        <section>
          <h2>2. A weboldal használata</h2>
          <p>
            <b>Nincs analitika és nincs követő süti.</b> Nem használunk Google
            Analyticsot, hirdetési pixelt vagy más követőt.
          </p>
          <p>
            A böngésződ tárolója négy apróságot őriz, kizárólag a te gépeden, és
            ezek nem jutnak el hozzánk:
          </p>
          <p>
            <b>Látogatottság.</b> Minden oldalmegtekintésnél feljegyezzük, melyik
            aloldalt nyitották meg, milyen nyelven, és melyik webhelyről érkezett a
            látogató — ez utóbbiból csak a domaint (például <code>google.com</code>),
            a keresőkifejezést és a teljes címet nem. <b>Nem tároljuk az IP-címet</b>,
            nem helyezünk el sütit hozzá, és nem képzünk azonosítót, amivel a
            látogató követhető lenne. Az adat összesítve, saját kiszolgálón marad;
            külső elemzőszolgáltatót nem használunk. Ezért ehhez nem kérünk
            hozzájárulást: a fenti adatkör nem személyes adat.
          </p>
          <ul>
            <li>a kiválasztott nyelv (<code>aximbra_lang</code>),</li>
            <li>hol tartottál a lapon, amikor egy demóra léptél — hogy visszatérve
              ugyanoda kerülj (<code>aximbra:return</code>, a fül bezárásáig él),</li>
            <li>az e-mail agent munkamenet-azonosítója, ha csatlakoztattad a fiókodat
              (<code>aximbra:agent</code>, szintén a fül bezárásáig).</li>
          </ul>
          <p>
            A kiszolgáló a visszaélések megelőzése érdekében a bemutató rendszerek
            hívásainál <b>egy órán át</b> a memóriájában tartja a kérés IP-címét és
            időpontját, hogy az óránkénti korlátot érvényesíteni tudja. Ez adatbázisba
            nem kerül, és egy óra után nyom nélkül elévül.
          </p>
          <p>
            Ettől függetlenül a <b>tárhelyszolgáltatók</b> (a weboldalnál a Cloudflare,
            az API-nál és az agenteknél a Railway) minden kéréshez saját üzemeltetési
            naplót vezetnek: ebben szerepel a kérés ideje, a hívott cím, a válasz
            kódja, a böngésző azonosítója és a kérés IP-címe. Ezt a naplót a
            szolgáltatók kezelik a saját megőrzési idejük szerint; mi olvasni tudjuk
            hibakereséskor, törölni nem.
            Jogalap: jogos érdek (GDPR 6. cikk (1) f) — a szolgáltatás működőképesen
            tartása és a visszaélés megakadályozása.
          </p>
        </section>

        <section>
          <h2>3. Kapcsolatfelvétel</h2>
          <p>
            Kétféleképpen lehet elérni minket, és a kettő nem ugyanazt csinálja.
          </p>
          <ul>
            <li>
              <b>E-mail- és telefongomb:</b> a saját levelezőprogramodat, illetve a
              telefonodat nyitja meg. Ilyenkor a weboldal semmit nem lát abból, amit írsz.
            </li>
            <li>
              <b>Ajánlatkérő űrlap:</b> a beírt név, e-mail-cím, opcionálisan a cégnév és
              az üzenet a kiszolgálónkon és egy levélküldő szolgáltatón (Resend) keresztül
              egyetlen e-mailben jut el az adatkezelőhöz. Adatbázisba nem kerül, a kiszolgálón nem tárolódik; a naplóban
              csak annyi marad, hogy érkezett egy üzenet — a tartalma nem. Az űrlap egy
              rejtett mezővel és a kitöltés idejével szűri a robotokat; ez nem kerül a
              levélbe.
            </li>
          </ul>
          <p>
            Amit így elküldesz, addig őrizzük, amíg az ügy indokolja, legfeljebb{" "}
            <b>2 évig</b>. Jogalap: az űrlapnál a hozzájárulásod (GDPR 6. cikk (1) a)),
            a levelezésnél szerződéskötést megelőző lépések, illetve jogos érdek
            (GDPR 6. cikk (1) b) és f)).
          </p>
        </section>

        <section>
          <h2>4. Érdeklődő-minősítő és dokumentum-elemző bemutató</h2>
          <p>
            Amit az érdeklődő-minősítő mezőjébe beírsz (legfeljebb 4000 karakter), egyetlen
            hívásban elküldjük a Google Gemini API-jának, és az eredményt visszaadjuk a lapnak.
          </p>
          <p>
            A dokumentum-elemzőbe feltöltött fájlt (PDF, Word vagy sima szöveg, legfeljebb
            5 MB) a kiszolgáló memóriájában olvassuk ki. A kiolvasott szöveg legfeljebb
            30 000 karakterét két hívásban elküldjük a Google Gemini API-jának, az eredményt
            visszaadjuk a lapnak, a fájlt és a szöveget pedig eldobjuk.
          </p>
          <p>
            <b>Egyik bemutatónál sem tároljuk sem a beküldött szöveget vagy fájlt, sem az
            eredményt</b> — nincs mögöttük adatbázis. A Google a Gemini API-n kapott adatot a{" "}
            6. pontban leírt feltételekkel kezeli. Jogalap: hozzájárulás (GDPR 6. cikk (1) a)),
            amit azzal adsz meg, hogy elindítod a bemutatót.
          </p>
          <p className="legal-note">
            Kérünk, ne másolj be és ne tölts fel valódi személyes adatot — a bemutatóhoz nem
            szükséges. Bizalmas iratnál előtte takard ki a neveket és a számokat.
          </p>
        </section>

        <section>
          <h2>5. E-mail rendező agent</h2>
          <p>
            Ez a rendszer kétféleképpen használható, és a kettő között nagy a különbség.
          </p>

          <h3>Példa postafiókkal</h3>
          <p>
            Ez az alapértelmezett út. A levelek általunk összeállított, kitalált
            levelek. <b>Nem kérünk Google-hozzáférést, és semmilyen adatod nem kerül
            hozzánk.</b>
          </p>

          <h3>A saját Gmail-fiókoddal</h3>
          <p>Ha te magad úgy döntesz, hogy csatlakoztatod a fiókodat:</p>
          <ul>
            <li>
              <b>Mit olvasunk:</b> az elmúlt <b>30 nap</b> legfeljebb <b>50</b> levelének
              feladóját, tárgyát, dátumát és szövegét.
            </li>
            <li>
              <b>Csatolmányok:</b> csak akkor nyitunk meg csatolmányt, ha a levél
              szövege önmagában kevés — ilyenkor levelenként legfeljebb <b>két</b>{" "}
              fájlból, fájlonként legfeljebb <b>5 MB</b>-ig olvassuk ki a szöveget
              (Word, Excel, PowerPoint, PDF, sima szöveg és CSV). Képet, videót és
              egyéb formátumot nem nyitunk meg, és <b>OCR-t nem végzünk</b>: egy
              szkennelt dokumentumból nem nyerünk ki szöveget. A fájl maga nem kerül
              sehova; a kiolvasott szöveg a levél szövegével együtt jut el a Google
              Gemini API-jához, és a futással együtt megszűnik.
            </li>
            <li>
              <b>Milyen jogot kérünk:</b> alapesetben csak olvasásit
              (<code>gmail.readonly</code>). Ha külön bepipálod a vázlatírást, akkor
              ezen felül a <code>gmail.compose</code> jogot is. A Google-nak nincs „csak
              vázlat” jogosultsága, ezért ez a jog önmagában küldést is lehetővé tenne —
              a rendszer viszont soha nem küld magától: küldeni csak akkor küld, ha egy
              adott levélnél te külön megerősíted. Ha a takarítást pipálod be, a{" "}
              <code>gmail.modify</code> jogot is kérjük: egy meglévő levél áthelyezéséhez
              az olvasás nem elég.
            </li>
            <li>
              <b>Mit írunk:</b> pipa nélkül semmit. Vázlatírással levelenként, mindig a te
              külön megerősítésed után: egy válaszvázlatot a Gmail Vázlatok közé, és ha azt
              is megerősíted, ennek a vázlatnak az elküldését.
            </li>
            <li>
              <b>Mit mozgatunk:</b> pipa nélkül semmit. A takarítással is csak azokat a
              leveleket, amelyeket az agent hírlevélnek vagy kéretlen levélnek sorolt be —
              hogy melyik ilyen, azt a kiszolgáló dönti el a most futó elemzés alapján,
              tehát más levél a gombbal nem érhető el. Az áthelyezés mindig a te
              kattintásodra történik, tömeges törlésnél külön megerősítéssel. A levelek a
              Gmail Kukájába kerülnek (<code>users.messages.trash</code>), ahonnan a Gmail
              30 napig visszaállítja őket — véglegesen (<code>delete</code>,{" "}
              <code>batchDelete</code>) semmit nem törlünk. Címkét nem adunk és nem
              csillagozunk.
            </li>
            <li>
              <b>Hová kerül:</b> a levelek szövegét osztályozásonként egy-egy hívásban
              elküldjük a Google Gemini API-jának. Adatbázisba semmi nem kerül.
            </li>
            <li>
              <b>Meddig él:</b> a futás a kiszolgáló memóriájában él, és{" "}
              <b>30 perc</b> után magától lejár. A „Kilépés” gomb azonnal törli. A lap
              bezárásakor a böngésző jelez a kiszolgálónak, és a futás ekkor is azonnal
              törlődik — ha ez a jelzés nem ér célba (megszakadt hálózat, lelőtt
              böngésző), a 30 perces határidő zárja le.
            </li>
            <li>
              <b>Hogyan vonod vissza:</b> bármikor, nálunk a Kilépés gombbal, a
              Google-nál pedig itt:{" "}
              <a href="https://myaccount.google.com/permissions"
                target="_blank" rel="noopener noreferrer">
                myaccount.google.com/permissions
              </a>
            </li>
          </ul>
          <p>
            Jogalap: hozzájárulás (GDPR 6. cikk (1) a)), amit a Google beleegyező
            képernyőjén adsz meg, és bármikor visszavonhatsz.
          </p>
        </section>

        <section>
          <h2>6. Google-adatok korlátozott felhasználása</h2>
          {/* A Google restricted scope-jainak verifikációjához ez a nyilatkozat
              kötelező, és szó szerint erre a tartalomra kérdez rá. */}
          <p>
            Az AXIMBRA a Google API-król kapott adatok kezelése és továbbadása során a{" "}
            <a href="https://developers.google.com/terms/api-services-user-data-policy"
              target="_blank" rel="noopener noreferrer">
              Google API Services User Data Policy
            </a>{" "}
            előírásait, ezen belül a korlátozott felhasználásra (Limited Use)
            vonatkozó követelményeket követi.
          </p>
          <p>A Gmailből olvasott adatokat kizárólag arra használjuk, hogy:</p>
          <ul>
            <li>a leveleidet a felületen kategorizáljuk és rangsoroljuk,</li>
            <li>és — ha kéred — válaszfogalmazványt készítsünk hozzájuk.</li>
          </ul>
          <p>
            Ezeket az adatokat <b>nem használjuk</b> hirdetéshez, nem adjuk el, nem adjuk
            át harmadik félnek a fenti funkciók biztosításán kívül, és{" "}
            <b>nem használjuk fel semmilyen mesterséges intelligencia modell
            tanítására</b>. A levelek tartalmát a Google Gemini modellje dolgozza fel, a Gemini
            API-n keresztül, hogy elkészüljön a neked megjelenő besorolás és vázlat. Az Európai
            Gazdasági Térségből használt Gemini API-ra a Google fizetős szolgáltatásokra vonatkozó
            adatkezelési feltételei érvényesek (
            <a href="https://ai.google.dev/gemini-api/terms" target="_blank" rel="noopener noreferrer">
              Gemini API Additional Terms of Service
            </a>): a Google a beküldött szöveget és a választ <b>nem használja a termékei
            fejlesztésére</b>, adatfeldolgozóként kezeli, és csak korlátozott ideig naplózza,
            kizárólag a visszaélések felderítése és jogszabályi kötelezettség miatt.
            Ember nem olvassa őket, kivéve ha ahhoz külön hozzájárulsz, az biztonsági okból
            vagy jogszabály miatt szükséges.
          </p>
        </section>

        <section>
          <h2 id="adatvedelmi-intezkedesek">7. Az érzékeny adatok védelme: technikai és szervezési intézkedések</h2>
          <p>Ez a rész minden érzékeny adatra vonatkozik, amelyet a szolgáltatás kezel: a Gmail-levelek és mellékletek tartalmára, a Google-hozzáférési (OAuth) tokenekre és a bennük lévő személyes adatokra.</p>
          <p>Így védjük a Gmail-adatokat és a nekünk adott Google-hozzáférést:</p>
          <ul>
            <li>
              <b>Titkosítás átvitel közben:</b> minden kapcsolat — a böngésződ és a szerverünk,
              a szerverünk és a Google API-k, valamint a szerverünk és a modellszolgáltató
              között — HTTPS-en (TLS) megy. Titkosítatlanul semmi nem utazik.
            </li>
            <li>
              <b>Nincs tartós tárolás:</b> a Google-hozzáférési token és a beolvasott levelek
              csak a szerver munkamemóriájában (RAM) vannak, adatbázisba, fájlba vagy mentésbe
              soha nem kerülnek. Törlődnek kilépéskor, a lap bezárásakor, legkésőbb{" "}
              <b>30 perc</b> után, és a szerver minden újraindulásakor is.
            </li>
            <li>
              <b>A hozzáférési token nem hagyja el a szervert:</b> a böngésződ csak egy
              titkosított és aláírt munkamenet-hivatkozást kap (Fernet: AES-128 titkosítás
              HMAC-SHA256 aláírással), ami 30 perc után lejár, és másnak használhatatlan. A
              bejelentkezés PKCE-vel és titkosított, aláírt, 15 perc után lejáró
              állapotparaméterrel megy, így nem hamisítható és nem játszható vissza.
            </li>
            <li>
              <b>Legkisebb jogosultság:</b> alapból csak olvasási jogot kérünk. Írási jogot
              (vázlat, Kukába helyezés) csak akkor, ha bepipálod, és csak a külön
              megerősítésed után használjuk. A küldést a kód mindenhol tiltja, kivéve azt az
              egy lépést, ahol egy konkrét vázlat elküldését megerősíted.
            </li>
            <li>
              <b>Adattakarékosság:</b> legfeljebb 50 levél az elmúlt 30 napból; levelenként
              legfeljebb két csatolmány, csak szövegként, OCR nélkül. Profilt nem készítünk
              rólad.
            </li>
            <li>
              <b>Napló tartalom nélkül:</b> a szervernapló csak technikai eseményeket és
              hibatípusokat rögzít — levélszöveget, tárgyat, feladót, címet vagy tokent soha.
            </li>
            <li>
              <b>Hozzáférés-kezelés:</b> a szolgáltatás felügyelt felhőplatformon fut; a
              tárhelyfiókhoz és a titkokhoz (API-kulcsok, a munkamenet titkosítókulcsa) csak az
              adatkezelő fér hozzá. Ezek titkosított környezeti változóként vannak tárolva, nem
              a forráskódban. Alkalmazott vagy alvállalkozó nem fér hozzá a felhasználói
              adatokhoz.
            </li>
            <li>
              <b>Incidens esetén:</b> adatvédelmi incidensről 72 órán belül értesítjük a
              felügyeleti hatóságot (NAIH), az érintetteket pedig indokolatlan késedelem
              nélkül, ahogy a GDPR előírja.
            </li>
          </ul>
        </section>

        <section>
          <h2>8. Telefonhívás</h2>
          <p>
            Az oldalon szereplő telefonszámon a hívószámod dönti el, ki veszi fel:
          </p>
          <ul>
            <li>
              <b>magyar (+36-os) számról</b> a hívás az adatkezelő mobiljára kapcsolódik.
              Ilyenkor nem készül átirat és összefoglaló; a hívószámod és a hívás
              időpontja a Twilio hívásnaplójába és a szerver naplójába kerül;
            </li>
            <li>
              <b>más ország számáról</b>, rejtett számról, vagy ha az adatkezelő nem veszi
              fel, a hívást egy AI agent fogadja.
            </li>
          </ul>
          <p>Ha az AI agent fogadja a hívást, kezeljük:</p>
          <ul>
            <li>a hívószámodat, a hívás időpontját és hosszát,</li>
            <li>a beszélgetés szöveges átiratát,</li>
            <li>és az ebből készült rövid összefoglalót.</li>
          </ul>
          <p>
            <b>Hangfelvétel nem készül.</b> Az átirat és az összefoglaló e-mailben
            eljut az adatkezelőhöz, hogy vissza tudjunk hívni. Legfeljebb <b>2 évig</b>{" "}
            őrizzük.
            Jogalap: hozzájárulás — a hívás elején az agent tájékoztat róla, és a hívás
            bontásával bármikor megszakíthatod.
          </p>
        </section>

        <section>
          <h2>9. Kinek adjuk tovább</h2>
          <p>Adatfeldolgozóink, és hogy mihez:</p>
          <div className="legal-table-wrap">
            <table className="legal-table">
              <thead>
                <tr><th>Szolgáltató</th><th>Mire</th><th>Hol</th></tr>
              </thead>
              <tbody>
                {PROCESSORS.map((p) => (
                  <tr key={p.name}>
                    <td>{p.name}</td><td>{p.role}</td><td>{p.where}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="legal-note">
            Az Egyesült Államokban működő szolgáltatók esetében az adattovábbítás az
            adott szolgáltató saját adatfeldolgozási feltételeiben vállalt garanciákon
            alapul (általános szerződési feltételek, illetve az EU–USA adatvédelmi
            keretrendszer, ahol alkalmazandó). Ezen kívül az adataidat nem adjuk át
            senkinek, és nem adjuk el.
          </p>
        </section>

        <section>
          <h2>10. A te jogaid</h2>
          <p>A GDPR alapján kérheted:</p>
          <ul>
            <li>a rólad kezelt adatok másolatát (hozzáférés),</li>
            <li>a pontatlan adatok helyesbítését,</li>
            <li>az adataid törlését,</li>
            <li>a kezelés korlátozását,</li>
            <li>az adataid hordozható formában való kiadását,</li>
            <li>és tiltakozhatsz a jogos érdeken alapuló kezelés ellen.</li>
          </ul>
          <p>
            Írj az <a href={mailto("Adatkezelési kérés")}>{CONTACT.email}</a> címre, és{" "}
            <b>30 napon belül</b> válaszolunk. A demók többségénél a válasz az lesz,
            hogy nincs mit törölni, mert nem tárolunk semmit — de a kérésre akkor is
            érdemben válaszolunk.
          </p>
        </section>

        <section>
          <h2>11. Panasz</h2>
          <p>
            Ha úgy érzed, hogy az adataidat jogszerűtlenül kezeljük, fordulhatsz a
            felügyeleti hatósághoz:
          </p>
          <dl className="legal-dl">
            <div><dt>Hatóság</dt><dd>Nemzeti Adatvédelmi és Információszabadság Hatóság (NAIH)</dd></div>
            <div><dt>Cím</dt><dd>1055 Budapest, Falk Miksa utca 9-11.</dd></div>
            <div><dt>Weboldal</dt><dd>
              <a href="https://naih.hu" target="_blank" rel="noopener noreferrer">naih.hu</a>
            </dd></div>
          </dl>
          <p>Bírósághoz is fordulhatsz a lakóhelyed szerinti törvényszéken.</p>
        </section>

        <section>
          <h2>12. Változtatás</h2>
          <p>
            Ha a rendszer változik, ez a tájékoztató is változik. A lap alján mindig
            látszik, mikor frissült utoljára.
          </p>
        </section>

        <p className="legal-updated">Hatályos: {LEGAL_UPDATED}</p>
      </main>
    </div>
  );
}

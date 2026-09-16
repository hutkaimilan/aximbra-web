import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER, CONTROLLER_ADDRESS, LEGAL_UPDATED, PROCESSORS } from "../legal";
import { useDocumentMeta } from "../seo";
import { useLang } from "../i18n";

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
 */
export default function Adatkezeles() {
  const { lang } = useLang();
  useDocumentMeta({
    title: "Adatkezelési tájékoztató | AXIMBRA",
    description:
      "Milyen adatokat kezelünk a weboldalon és a bemutató agentekben, mennyi ideig, " +
      "kinek adjuk tovább, és hogyan kérheted a törlésüket.",
    path: "/adatkezeles",
    lang,
    // A jogi szöveg csak magyarul létezik.
    translated: false,
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

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
          <ul>
            <li>a kiválasztott nyelv (<code>aximbra_lang</code>),</li>
            <li>hogy láttad-e már a nyitóanimációt (<code>aximbra:intro-seen</code>),</li>
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
            Ettől függetlenül a <b>tárhelyszolgáltató</b> (Railway) minden kéréshez
            saját üzemeltetési naplót vezet: ebben szerepel a kérés ideje, a hívott
            cím, a válasz kódja, a böngésző azonosítója és a kérés IP-címe. Ezt a
            naplót a szolgáltató kezeli a saját megőrzési ideje szerint; mi olvasni
            tudjuk hibakereséskor, törölni nem.
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
              az üzenet a kiszolgálónkon keresztül egyetlen e-mailben jut el az
              adatkezelőhöz. Adatbázisba nem kerül, a kiszolgálón nem tárolódik; a naplóban
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
          <h2>4. Érdeklődő-minősítő bemutató</h2>
          <p>
            Amit a mezőbe beírsz (legfeljebb 4000 karakter), egyetlen hívásban
            elküldjük az OpenAI API-jának, és az eredményt visszaadjuk a lapnak.{" "}
            <b>Sem a beírt szöveget, sem az eredményt nem tároljuk</b> — nincs mögötte
            adatbázis. Jogalap: hozzájárulás (GDPR 6. cikk (1) a)), amit azzal adsz meg,
            hogy elindítod a bemutatót.
          </p>
          <p className="legal-note">
            Kérünk, ne másolj be valódi személyes adatot — a bemutatóhoz nem szükséges.
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
              sehova; a kiolvasott szöveg a levél szövegével együtt jut el az OpenAI
              API-jához, és a futással együtt megszűnik.
            </li>
            <li>
              <b>Milyen jogot kérünk:</b> alapesetben csak olvasásit
              (<code>gmail.readonly</code>). Ha külön bepipálod a vázlatírást, akkor
              ezen felül a <code>gmail.compose</code> jogot is. A Google-nak nincs „csak
              vázlat” jogosultsága, ezért ez a jog önmagában küldést is lehetővé tenne —
              a rendszer viszont soha nem küld magától: küldeni csak akkor küld, ha egy
              adott levélnél te külön megerősíted.
            </li>
            <li>
              <b>Mit írunk:</b> pipa nélkül semmit. Vázlatírással is csak egyetlen
              dolgot: egy válaszvázlatot a Gmail Vázlatok közé, levelenként a te
              megerősítésed után. Meglévő leveleidhez soha nem nyúlunk — nem címkézünk,
              nem csillagozunk, nem törlünk.
            </li>
            <li>
              <b>Hová kerül:</b> a levelek szövegét osztályozásonként egy-egy hívásban
              elküldjük az OpenAI API-jának. Adatbázisba semmi nem kerül.
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
            tanítására</b>. Ember nem olvassa őket, kivéve ha ahhoz külön hozzájárulsz,
            az biztonsági okból vagy jogszabály miatt szükséges.
          </p>
        </section>

        <section>
          <h2>7. Telefonhívás</h2>
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
          <h2>8. Kinek adjuk tovább</h2>
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
          <h2>9. A te jogaid</h2>
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
          <h2>10. Panasz</h2>
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
          <h2>11. Változtatás</h2>
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

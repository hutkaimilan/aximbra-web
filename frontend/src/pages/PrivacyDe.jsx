import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER, CONTROLLER_ADDRESS_DE, LEGAL_UPDATED_DE, PROCESSORS } from "../legal";
import { useDocumentMeta } from "../seo";
import { pathFor } from "../i18n";

/**
 * Az adatkezelesi tajekoztato nemetul (Datenschutzerklärung).
 *
 * Fejezetrol fejezetre ugyanaz, mint a magyar (iranyado) es az angol szoveg:
 * ha az egyik valtozik, mind a harmat at kell irni, kulonben mast igernek.
 * Egy kulonbseg: a panaszjognal kimondjuk, hogy a nemet latogato a sajat
 * orszaganak felugyeleti hatosagahoz is fordulhat (GDPR 77. cikk).
 */
export default function PrivacyDe({ lang }) {
  useDocumentMeta({
    title: "Datenschutzerklärung | AXIMBRA",
    description:
      "Welche Daten die Website und die Demo-Agenten verarbeiten, wie lange, wer sie erhält " +
      "und wie Sie die Löschung verlangen können.",
    path: "/adatkezeles",
    lang,
    translated: false,
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="legal-page">
      <header className="legal-top">
        <Link to={pathFor(lang, "/")} className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main">
        <h1>Datenschutzerklärung</h1>
        <p className="legal-lead">
          Diese Erklärung beschreibt, was das System <i>tatsächlich</i> tut — nicht in
          allgemeinen Worten. Wo hier eine Zahl steht, verwendet der Code dieselbe Zahl.
        </p>
        <p className="legal-note">
          Dies ist eine deutsche Übersetzung. Maßgeblich ist die{" "}
          <Link to="/adatkezeles">ungarische Fassung</Link>.
        </p>

        <section>
          <h2>1. Wer Ihre Daten verarbeitet</h2>
          <dl className="legal-dl">
            <div><dt>Verantwortlicher</dt><dd>{CONTROLLER.name}</dd></div>
            <div><dt>Anschrift</dt><dd>{CONTROLLER_ADDRESS_DE}</dd></div>
            <div><dt>E-Mail</dt><dd><a href={mailto()}>{CONTACT.email}</a></dd></div>
          </dl>
          <p className="legal-note">
            AXIMBRA ist ein Markenname, kein eingetragenes Unternehmen. Ein
            Datenschutzbeauftragter ist nicht vorgeschrieben und wurde nicht benannt.
          </p>
        </section>

        <section>
          <h2>2. Nutzung der Website</h2>
          <p>
            <b>Keine Analyse-Tools und keine Tracking-Cookies.</b> Wir verwenden weder
            Google Analytics noch Werbepixel oder andere Tracker.
          </p>
          <p>
            <b>Zugriffe.</b> Für jeden Seitenaufruf speichern wir, welche Seite in welcher
            Sprache geöffnet wurde und von welcher Website der Besucher kam — davon nur die
            Domain (zum Beispiel <code>google.com</code>), nie den Suchbegriff oder die
            vollständige Adresse. <b>IP-Adressen speichern wir nicht</b>, wir setzen dafür
            kein Cookie und bilden keine Kennung, mit der sich ein Besucher verfolgen ließe.
            Die Daten bleiben zusammengefasst auf unserem eigenen Server; ein externer
            Analysedienst wird nicht eingesetzt. Deshalb fragen wir dafür keine Einwilligung
            ab: Dieser Datensatz ist kein personenbezogenes Datum.
          </p>
          <p>Der Speicher Ihres Browsers enthält nur auf Ihrem Gerät, ohne dass es uns erreicht:</p>
          <ul>
            <li>die gewählte Sprache (<code>aximbra_lang</code>),</li>
            <li>die Stelle auf der Seite, an der Sie eine Demo geöffnet haben, damit Sie dorthin
              zurückkehren (<code>aximbra:return</code>, bis der Tab geschlossen wird),</li>
            <li>die Sitzungskennung des E-Mail-Agenten, falls Sie Ihr Konto verbunden haben
              (<code>aximbra:agent</code>, ebenfalls bis der Tab geschlossen wird).</li>
          </ul>
          <p>
            Zum Schutz vor Missbrauch hält der Server bei Aufrufen der Demo-Systeme die
            IP-Adresse und die Uhrzeit der Anfrage <b>eine Stunde</b> lang im Arbeitsspeicher,
            um das stündliche Limit durchzusetzen. Das wird nicht in eine Datenbank
            geschrieben und verfällt nach einer Stunde spurlos.
          </p>
          <p>
            Unabhängig davon führt der <b>Hosting-Anbieter</b> (Railway) ein eigenes
            Betriebsprotokoll jeder Anfrage: Zeitpunkt, aufgerufene Adresse, Antwortcode,
            Browserkennung und IP-Adresse. Der Anbieter bewahrt dieses Protokoll nach seiner
            eigenen Frist auf; wir können es bei der Fehlersuche lesen, aber nicht löschen.
            Rechtsgrundlage: berechtigtes Interesse (Art. 6 Abs. 1 lit. f DSGVO) — Betrieb des
            Dienstes und Schutz vor Missbrauch.
          </p>
        </section>

        <section>
          <h2>3. Kontaktaufnahme</h2>
          <p>Es gibt zwei Wege, uns zu erreichen, und sie tun nicht dasselbe.</p>
          <ul>
            <li>
              <b>E-Mail- und Telefon-Schaltflächen:</b> Sie öffnen Ihr eigenes E-Mail-Programm
              oder Ihr Telefon. Die Website sieht nichts von dem, was Sie schreiben.
            </li>
            <li>
              <b>Anfrageformular:</b> Name, E-Mail-Adresse, optional der Firmenname und Ihre
              Nachricht erreichen den Verantwortlichen in einer einzigen E-Mail, über unseren
              Server und einen E-Mail-Versanddienst (Resend). Sie werden nicht in eine Datenbank
              geschrieben und nicht auf dem Server gespeichert; das Protokoll vermerkt nur, dass
              eine Nachricht eingegangen ist — nicht ihren Inhalt. Das Formular erkennt Bots an
              einem versteckten Feld und an der Ausfülldauer; beides ist nicht Teil der E-Mail.
            </li>
          </ul>
          <p>
            Was Sie uns so senden, bewahren wir auf, solange die Angelegenheit es erfordert,
            höchstens <b>2 Jahre</b>. Rechtsgrundlage: beim Formular Ihre Einwilligung
            (Art. 6 Abs. 1 lit. a DSGVO); bei der Korrespondenz vorvertragliche Maßnahmen und
            berechtigtes Interesse (Art. 6 Abs. 1 lit. b und f DSGVO).
          </p>
        </section>

        <section>
          <h2>4. Demo „Anfragen-Qualifizierer“</h2>
          <p>
            Was Sie in das Feld eingeben (bis zu 4 000 Zeichen), wird in einem einzigen Aufruf an
            die OpenAI-API gesendet, das Ergebnis geht an die Seite zurück.{" "}
            <b>Weder der Text noch das Ergebnis werden gespeichert</b> — dahinter steht keine
            Datenbank. Rechtsgrundlage: Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die Sie mit dem
            Start der Demo erteilen.
          </p>
          <p className="legal-note">
            Bitte geben Sie keine echten personenbezogenen Daten ein — die Demo braucht sie nicht.
          </p>
        </section>

        <section>
          <h2>5. E-Mail-Agent</h2>
          <p>Dieses System lässt sich auf zwei Arten nutzen, und der Unterschied ist groß.</p>

          <h3>Mit dem Beispielpostfach</h3>
          <p>
            Das ist die Voreinstellung. Die E-Mails haben wir erfunden.{" "}
            <b>Wir fragen keinen Google-Zugriff an, und keine Ihrer Daten erreichen uns.</b>
          </p>

          <h3>Mit Ihrem eigenen Gmail-Konto</h3>
          <p>Wenn Sie Ihr Konto verbinden:</p>
          <ul>
            <li>
              <b>Was wir lesen:</b> Absender, Betreff, Datum und Text von höchstens{" "}
              <b>50</b> E-Mails der letzten <b>30 Tage</b>.
            </li>
            <li>
              <b>Anhänge:</b> Einen Anhang öffnen wir nur, wenn der Text der E-Mail allein nicht
              ausreicht — dann extrahieren wir den Text von höchstens <b>zwei</b> Dateien pro
              E-Mail, bis <b>5 MB</b> je Datei (Word, Excel, PowerPoint, PDF, Text und CSV). Bilder,
              Videos und andere Formate öffnen wir nicht, und <b>wir führen keine
              Texterkennung (OCR) durch</b>: Aus einem gescannten Dokument wird kein Text gewonnen.
              Die Datei selbst geht nirgendwohin; der extrahierte Text erreicht zusammen mit dem
              Text der E-Mail die OpenAI-API und ist nach dem Durchlauf weg.
            </li>
            <li>
              <b>Welchen Zugriff wir anfragen:</b> standardmäßig nur Lesen
              (<code>gmail.readonly</code>). Wenn Sie zusätzlich das Schreiben von Entwürfen
              ankreuzen, auch <code>gmail.compose</code>. Google kennt keine Berechtigung „nur
              Entwürfe“, diese Berechtigung würde also auch das Senden erlauben — das System sendet
              aber nie von selbst, sondern nur, wenn Sie es für eine bestimmte E-Mail gesondert
              bestätigen. Kreuzen Sie das Aufräumen an, fragen wir zusätzlich{" "}
              <code>gmail.modify</code> an: Lesen reicht nicht, um eine Nachricht zu verschieben.
            </li>
            <li>
              <b>Was wir schreiben:</b> ohne Häkchen nichts. Mit Entwürfen jeweils für eine E-Mail
              und immer nach Ihrer gesonderten Bestätigung: einen Antwortentwurf in Ihren
              Gmail-Entwürfen und — wenn Sie auch das bestätigen — den Versand dieses Entwurfs.
            </li>
            <li>
              <b>Was wir verschieben:</b> ohne Häkchen nichts. Auch beim Aufräumen nur die
              Nachrichten, die der Agent als Newsletter oder unerwünschte Post eingestuft hat —
              welche das sind, entscheidet der Server aus der gerade geöffneten Analyse, sodass die
              Schaltfläche keine andere Nachricht erreichen kann. Verschoben wird immer auf Ihren
              Klick, beim Massenlöschen mit gesonderter Bestätigung. Die Nachrichten gehen in Ihren
              Gmail-Papierkorb (<code>users.messages.trash</code>), wo Gmail sie etwa 30 Tage
              wiederherstellbar hält — endgültig löschen wir nie (<code>delete</code>,{" "}
              <code>batchDelete</code>). Wir vergeben keine Labels und keine Sterne.
            </li>
            <li>
              <b>Wohin es geht:</b> Der Text der E-Mails wird an die OpenAI-API gesendet, ein
              Aufruf pro Einstufung. Nichts wird in eine Datenbank geschrieben.
            </li>
            <li>
              <b>Wie lange es existiert:</b> Der Durchlauf lebt im Arbeitsspeicher des Servers und
              verfällt nach <b>30 Minuten</b> von selbst. Die Schaltfläche „Abmelden und trennen“
              löscht ihn sofort. Schließen Sie die Seite, meldet der Browser das dem Server, und der
              Durchlauf wird ebenfalls sofort gelöscht — kommt dieses Signal nicht an (Netzausfall,
              abgestürzter Browser), beendet ihn die 30-Minuten-Grenze.
            </li>
            <li>
              <b>Zugriff widerrufen:</b> jederzeit — bei uns mit der Abmelde-Schaltfläche und bei
              Google hier:{" "}
              <a href="https://myaccount.google.com/permissions"
                target="_blank" rel="noopener noreferrer">
                myaccount.google.com/permissions
              </a>
            </li>
          </ul>
          <p>
            Rechtsgrundlage: Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die Sie auf dem
            Zustimmungsbildschirm von Google erteilen und jederzeit widerrufen können.
          </p>
        </section>

        <section>
          <h2>6. Eingeschränkte Nutzung von Google-Nutzerdaten</h2>
          <p>
            Die Nutzung und Weitergabe von Informationen aus Google-APIs durch AXIMBRA hält sich
            an die{" "}
            <a href="https://developers.google.com/terms/api-services-user-data-policy"
              target="_blank" rel="noopener noreferrer">
              Google API Services User Data Policy
            </a>, einschließlich der Anforderungen zur eingeschränkten Nutzung (Limited Use).
          </p>
          <p>Aus Gmail gelesene Daten verwenden wir nur, um:</p>
          <ul>
            <li>Ihre E-Mails auf der Seite einzuordnen und zu priorisieren,</li>
            <li>und — wenn Sie es wünschen — Antwortentwürfe dazu zu schreiben.</li>
          </ul>
          <p>
            Wir <b>verwenden diese Daten nicht</b> für Werbung, verkaufen sie nicht, geben sie
            nicht über das für die genannten Funktionen Nötige hinaus an Dritte weiter und{" "}
            <b>trainieren damit kein KI-Modell</b>. Der einzige Dritte, der E-Mail-Inhalte erhält,
            ist OpenAI über seine API, um die Ihnen angezeigte Einordnung und die Entwürfe zu
            erzeugen; nach den API-Bedingungen von OpenAI werden über die API gesendete Daten nicht
            zum Training seiner Modelle verwendet. Kein Mensch liest die Daten, es sei denn, Sie
            stimmen dem gesondert zu, oder es ist aus Sicherheitsgründen oder gesetzlich
            erforderlich.
          </p>
        </section>

        <section>
          <h2>7. Telefonanrufe</h2>
          <p>Bei der auf der Website angegebenen Nummer entscheidet Ihre Rufnummer, wer abnimmt:</p>
          <ul>
            <li>
              <b>von einer ungarischen (+36) Nummer</b> wird der Anruf an das Mobiltelefon des
              Verantwortlichen weitergeleitet. Es entsteht kein Transkript und keine
              Zusammenfassung; Ihre Nummer und der Zeitpunkt werden im Anrufprotokoll von Twilio und
              im Serverprotokoll erfasst;
            </li>
            <li>
              <b>aus jedem anderen Land</b>, mit unterdrückter Nummer oder wenn der Verantwortliche
              nicht abnimmt, nimmt ein KI-Agent den Anruf an.
            </li>
          </ul>
          <p>Nimmt der KI-Agent den Anruf an, verarbeiten wir:</p>
          <ul>
            <li>Ihre Telefonnummer sowie Zeitpunkt und Dauer des Anrufs,</li>
            <li>ein Texttranskript des Gesprächs,</li>
            <li>und eine daraus erstellte kurze Zusammenfassung.</li>
          </ul>
          <p>
            <b>Es wird kein Ton aufgezeichnet.</b> Transkript und Zusammenfassung erreichen den
            Verantwortlichen per E-Mail, damit wir Sie zurückrufen können. Wir bewahren sie
            höchstens <b>2 Jahre</b> auf. Rechtsgrundlage: Einwilligung — der Agent weist zu Beginn
            des Anrufs darauf hin, und Sie können jederzeit durch Auflegen beenden.
          </p>
        </section>

        <section>
          <h2>8. Wer die Daten erhält</h2>
          <p>Unsere Auftragsverarbeiter und wofür:</p>
          <div className="legal-table-wrap">
            <table className="legal-table">
              <thead>
                <tr><th>Anbieter</th><th>Zweck</th><th>Standort</th></tr>
              </thead>
              <tbody>
                {PROCESSORS.map((p) => (
                  <tr key={p.name}>
                    <td>{p.name}</td><td>{p.roleDe}</td><td>{p.whereDe}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="legal-note">
            Bei Anbietern in den Vereinigten Staaten stützt sich die Übermittlung auf die
            Garantien, zu denen sich der jeweilige Anbieter in seinen Datenverarbeitungsbedingungen
            verpflichtet (Standardvertragsklauseln und, wo anwendbar, das EU-US Data Privacy
            Framework). Darüber hinaus geben wir Ihre Daten an niemanden weiter und verkaufen sie
            nicht.
          </p>
        </section>

        <section>
          <h2>9. Ihre Rechte</h2>
          <p>Nach der DSGVO können Sie verlangen:</p>
          <ul>
            <li>eine Kopie der Daten, die wir über Sie haben (Auskunft),</li>
            <li>die Berichtigung unrichtiger Daten,</li>
            <li>die Löschung Ihrer Daten,</li>
            <li>die Einschränkung der Verarbeitung,</li>
            <li>Ihre Daten in einem übertragbaren Format,</li>
            <li>und Sie können der Verarbeitung auf Grundlage berechtigten Interesses widersprechen.</li>
          </ul>
          <p>
            Schreiben Sie an <a href={mailto("Datenschutzanfrage")}>{CONTACT.email}</a>; wir
            antworten <b>innerhalb von 30 Tagen</b>. Bei den meisten Demos lautet die Antwort, dass
            es nichts zu löschen gibt, weil wir nichts speichern — die Anfrage beantworten wir
            trotzdem ordentlich.
          </p>
        </section>

        <section>
          <h2>10. Beschwerde</h2>
          <p>
            Wenn Sie meinen, dass Ihre Daten rechtswidrig verarbeitet werden, können Sie sich an
            die zuständige Aufsichtsbehörde wenden:
          </p>
          <dl className="legal-dl">
            <div><dt>Behörde</dt><dd>Ungarische Nationale Behörde für Datenschutz und Informationsfreiheit (NAIH)</dd></div>
            <div><dt>Anschrift</dt><dd>Falk Miksa utca 9-11, 1055 Budapest, Ungarn</dd></div>
            <div><dt>Website</dt><dd>
              <a href="https://naih.hu" target="_blank" rel="noopener noreferrer">naih.hu</a>
            </dd></div>
          </dl>
          <p>
            Nach Art. 77 DSGVO können Sie sich auch an die Aufsichtsbehörde Ihres gewöhnlichen
            Aufenthalts oder Arbeitsplatzes wenden, in Deutschland also an die
            Datenschutzbehörde Ihres Bundeslandes.
          </p>
        </section>

        <section>
          <h2>11. Änderungen</h2>
          <p>
            Ändert sich das System, ändert sich auch diese Erklärung. Unten auf der Seite steht
            immer, wann sie zuletzt aktualisiert wurde.
          </p>
        </section>

        <p className="legal-updated">Stand: {LEGAL_UPDATED_DE}</p>
      </main>
    </div>
  );
}

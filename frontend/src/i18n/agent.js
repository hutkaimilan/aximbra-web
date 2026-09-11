// Az e-mail agent lapjának szövegei. Külön fájlban, mert ez a lap egymaga
// annyi szöveget tartalmaz, mint a főoldal fele, és mert nyolc nyelven kell.
// A kategóriakulcsok (customer_question, …) a kiszolgálótól jönnek: a modell
// kulcsot ad vissza, a feliratot itt kapja meg.
const agent = {
  hu: {
    seo: {
      title: "E-mail rendező agent — élő demó | AXIMBRA",
      description:
        "Élő demó: az agent átfutja a postafiókod elmúlt 30 napját, rangsorolja a " +
        "leveleket és megírja a válaszokat. Alapból csak olvas — küldeni nem tud.",
    },
    title: "E-mail rendező agent",
    notConnected: "Nincs csatlakozva",
    err: {
      access_denied: "A Google-hozzáférést elutasítottad, vagy megszakadt a folyamat.",
      invalid_state: "Lejárt a folyamat. Indítsd újra a csatlakozást.",
      token_exchange: "A Google-lel való egyeztetés nem sikerült. Próbáld újra.",
      no_email: "A Google nem adta vissza a fiók e-mail címét.",
      busy: "Most túl sokan próbálják egyszerre. Gyere vissza pár perc múlva.",
      generic: "Hiba",
      unknown: "Ismeretlen hiba.",
    },
    urgency: { u5: "Azonnali", u4: "Sürgős", u3: "Közepes", u1: "Ráér" },
    cat: {
      customer_question: "Ügyfél – kérdés",
      customer_complaint: "Ügyfél – panasz",
      opportunity: "Üzleti lehetőség",
      invoice: "Számla / pénzügy",
      authority: "Hatóság / hivatalos",
      provider_notice: "Szolgáltatói értesítés",
      newsletter: "Hírlevél / marketing",
      spam: "Spam / kéretlen",
      other: "Egyéb",
    },
    tone: { group: "Hangnem", hivatalos: "Hivatalos", kozvetlen: "Közvetlen" },
    draft: {
      write: "Megfogalmazom a választ",
      rewrite: "Újrafogalmazás",
      writing: "Fogalmazás…",
      subject: "Tárgy",
      copy: "Másolás",
      copied: "Kimásolva",
      clipboardError: "A vágólap nem elérhető — jelöld ki a szöveget és másold ki kézzel.",
      save: "Mentés a Gmail vázlatok közé",
      send: "E-mail elküldése",
      noteWrite: "Küldés előtt még egyszer rákérdezünk — elküldeni csak te tudod.",
      noteRead: "Fogalmazvány — az agent nem küldi el, és a fiókodba sem írja be.",
      saveText: "Vázlatot írok a Gmail-fiókodba {sender} levelére, a saját levelezőszálára.",
      saveNotSend: "Nem küldöm el",
      saveNotSendRest: "— a Vázlatok közt találod, és te döntöd el, elküldöd-e.",
      saveYes: "Megerősítem, mentsd vázlatként",
      saving: "Mentés…",
      cancel: "Mégsem",
      sendTitle: "Most tényleg elküldöm ezt a levelet.",
      to: "Címzett",
      from: "Feladó",
      fromValue: "a te Gmail-fiókod",
      sendWarn:
        "Ez nem vonható vissza. Olvasd át a fenti szöveget — a szögletes zárójeles " +
        "részeket ([így]) neked kell kitöltened, mielőtt elküldöd.",
      sendYes: "Igen, küldd el most",
      sending: "Küldés…",
      sent: "Elküldve.",
      savedNew: "Vázlat elmentve.",
      savedUpdated: "Vázlat frissítve.",
      openGmail: "Megnyitom a Gmailben",
    },
    intro: {
      lead:
        "Csatlakoztasd a Gmail-fiókod, és az agent végigmegy az elmúlt 30 nap levelein: " +
        "kategóriába sorolja, sürgősséget állapít meg, és megmondja, melyikre kell " +
        "válaszolnod. Amelyikre kéred, a választ is megfogalmazza.",
      guarantees: [
        { t: "Alapból csak olvas.", d: "A lenti pipa nélkül semmit nem ír a fiókodba, és a küldési jogot sem kéri." },
        { t: "A meglévő leveleidhez soha nem nyúl.", d: "Nem címkéz, nem csillagoz, nem töröl — akkor sem, ha megadod az írási jogot." },
        { t: "Írni és küldeni csak a te engedélyeddel.", d: "Ha bepipálod, akkor is levelenként külön rákérdezünk, mielőtt vázlatot írna vagy elküldene bármit." },
        { t: "Semmit nem tárolunk.", d: "A futás 30 perc után magától lejár. A lap bezárásakor a böngésző jelez, és azonnal törlődik — ha a jelzés nem ér célba, marad a 30 perces határidő." },
      ],
    },
    disclosure: {
      summary: "Mit kérünk pontosan, és mi történik az adataiddal?",
      scopesTitle: "A kért Google-jogosultságok",
      scopeRead: "a leveleid olvasása. Ez mindig kell, és alapesetben ez az egyetlen jog, amit kérünk.",
      scopeIdentity: "hogy tudjuk, melyik fiókot nézzük.",
      scopeComposeLead: "csak ha bepipálod a vázlatírást.",
      scopeCompose:
        "Ettől tud vázlatot tenni a fiókodba. A Google-nak nincs „csak vázlat” jogosultsága, " +
        "ezért ez küldést is engedne — ez a kód viszont soha nem küld, a küldés kódszinten " +
        "tiltott. Pipa nélkül ezt a jogot nem is kérjük.",
      readTitle: "Mit olvasunk",
      read30: "Az elmúlt 30 nap legfeljebb 50 levele. Semmi régebbi, semmi több.",
      readFields: "Feladó, tárgy, dátum és a levél szövege.",
      readAttachLead: "Csatolmány csak akkor, ha a levél szövege önmagában kevés",
      readAttach:
        "— egy „küldöm az anyagot, részletek csatolva” típusú levélnél a lényeg a " +
        "dokumentumban van. Ilyenkor levelenként legfeljebb két fájlból olvassuk ki a " +
        "szöveget (Word, Excel, PowerPoint, PDF, sima szöveg; képekből és videókból nem). " +
        "A fájlt nem tároljuk, csak a kiolvasott szöveg megy tovább az osztályozáshoz.",
      writeTitle: "Mit írunk",
      writeNoneLead: "Pipa nélkül:",
      writeNone: "semmit. A fogalmazvány a lapon marad, te másolod ki.",
      writeDraft:
        "Vázlatírással: egyetlen dolgot, levelenként, a te külön megerősítésed után — egy " +
        "válaszvázlatot a Gmail Vázlatok közé. Meglévő levelet nem módosítunk: nem címkézünk, " +
        "nem csillagozunk, nem törlünk, és nem küldünk el semmit.",
      whereTitle: "Hová kerül",
      whereLlm:
        "A levél szövegét egyetlen osztályozó hívásban elküldjük az OpenAI API-jának. Az API-n " +
        "beküldött adatot a szolgáltató alapbeállítás szerint nem használja modelltanításra.",
      whereNoDb: "Adatbázisba semmi nem kerül. A futás a szerver memóriájában él.",
      lifeTitle: "Meddig él, és hogyan törlöd",
      life30: "A munkamenet 30 perc után magától lejár.",
      lifeExit: "A „Kilépés” azonnal törli a futást és a hozzáférést. A lap bezárása is ezt teszi, ha a böngésző jelzése megérkezik; egyébként a 30 perces határidő zárja le.",
      lifeRevoke: "A jogosultságot a Google-nál bármikor visszavonhatod:",
      whoTitle: "Ki kéri",
      whoText: "— kérdés vagy törlési kérés esetén írj, és válaszolunk.",
    },
    closed: {
      title: "Az agent jelenleg nem nyilvános.",
      body:
        "A Gmail-hozzáférés kérése előtt közzétesszük az adatkezelési tájékoztatót és a " +
        "céges adatokat — addig nem kérünk senkitől postafiók-hozzáférést.",
      live: "Élőben szívesen megmutatjuk a saját fiókunkon:",
      liveSubject: "Megnézném az e-mail agentet élőben",
    },
    start: {
      cta: "Nézd meg egy példa postafiókon",
      starting: "Indítás…",
      running: "Feldolgozás folyamatban…",
      fetching: "Levelek lekérése…",
      done: "Kész",
      empty: "Nincs feldolgozható levél az elmúlt 30 napban.",
      interrupted: "Az elemzés megszakadt. Próbáld újra.",
      budget: "Az agent mára elérte a napi keretét.",
      noSubject: "(nincs tárgy)",
      note:
        "10 valósághű magyar levél, azonnal, belépés nélkül. Ugyanaz az agent fut rajtuk, " +
        "mint egy éles postafiókon — a válaszokat is megírja.",
      alt: "Inkább a saját Gmail-fiókomon nézném meg →",
    },
    connect: {
      notConfigured: "Az agent Google-hozzáférése még nincs beállítva.",
      googleTitle: "Amit a Google mutatni fog.",
      googleBody:
        "Mielőtt beenged, egy piros „A Google nem ellenőrizte ezt az alkalmazást” képernyő jön. " +
        "Ez minden olyan alkalmazásnál megjelenik, amelyik postafiók-hozzáférést kér és még nem " +
        "esett át a Google biztonsági átvilágításán — nem a fiókod állapotáról szól.",
      googleHow:
        "Továbblépni a Speciális → Tovább… linken lehet. Ha ez most kényelmetlen, a példa " +
        "postafiók mindent megmutat belépés nélkül.",
      back: "← Vissza a példa postafiókhoz",
      optinTitle: "Írhat vázlatot a postafiókomba.",
      optinBody:
        "Ha bepipálod, az agent a megírt választ — a te külön megerősítésed után, levelenként — " +
        "beteszi a Gmail Vázlatok közé, a saját levelezőszálára. Elküldeni akkor is csak te tudod.",
      optinWarn:
        "Fontos: a Google-nak nincs „csak vázlat” jogosultsága, ezért a beleegyező képernyő " +
        "küldési jogot is említeni fog. Ez a kód soha nem küld levelet — a küldés kódszinten " +
        "tiltott —, de a jogosultság, amit megadsz, ennél szélesebb. Ha ez nem kényelmes, hagyd " +
        "üresen: a fogalmazás pipa nélkül is működik, csak kimásolni kell.",
      ctaRead: "Csatlakozás a Google-fiókhoz",
      ctaWrite: "Csatlakozás — olvasás és vázlatírás",
      redirecting: "Átirányítás…",
    },
    run: {
      sampleNoteTitle: "Példa postafiók.",
      sampleNote:
        "A levelek kitaláltak — az osztályozás és a válaszok viszont most készültek, " +
        "ugyanazzal az agenttel, ami egy éles fiókon futna.",
      starting: "Indulás…",
      processed: "Feldolgozott levél",
      needsReply: "Válasz szükséges",
      showThese: "Mutasd ezeket",
      showAllShort: "Mind a levél mutatása",
      mostUrgent: "Legsürgősebb",
      categories: "Kategória-megoszlás",
      filterNote: "Csak a válaszra váró levelek látszanak.",
      showAllN: "Mutasd mind a {n} levelet",
      whyUrgent: "Miért ez a sürgősség",
      nextStep: "Javasolt következő lépés",
      theEmail: "A levél",
      empty: "(üres)",
      noEmails: "Nem találtunk levelet az elmúlt 30 napból.",
      logout: "Kilépés és lecsatlakozás",
      foot: "A kilépéssel a fiókod azonnal lecsatlakozik, és az elemzés törlődik a szerverről.",
    },
    unreachable: {
      title: "Az agent most nem érhető el.",
      body: "Nem tudtuk elérni a kiszolgálót — ez általában néhány másodperces frissítés, amíg új verzió indul.",
      retry: "Próbáld újra",
    },
  },

  en: {
    seo: {
      title: "Email triage agent — live demo | AXIMBRA",
      description:
        "Live demo: the agent goes through the last 30 days of your mailbox, ranks the " +
        "messages and writes the replies. Read-only by default — it cannot send.",
    },
    title: "Email triage agent",
    notConnected: "Not connected",
    err: {
      access_denied: "You declined Google access, or the process was interrupted.",
      invalid_state: "The process has expired. Start connecting again.",
      token_exchange: "The exchange with Google failed. Please try again.",
      no_email: "Google did not return the account's email address.",
      busy: "Too many people are trying at once. Come back in a few minutes.",
      generic: "Error",
      unknown: "Unknown error.",
    },
    urgency: { u5: "Immediate", u4: "Urgent", u3: "Medium", u1: "Can wait" },
    cat: {
      customer_question: "Customer – question",
      customer_complaint: "Customer – complaint",
      opportunity: "Business opportunity",
      invoice: "Invoice / finance",
      authority: "Authority / official",
      provider_notice: "Provider notice",
      newsletter: "Newsletter / marketing",
      spam: "Spam / unsolicited",
      other: "Other",
    },
    tone: { group: "Tone", hivatalos: "Formal", kozvetlen: "Direct" },
    draft: {
      write: "Write the reply",
      rewrite: "Rewrite",
      writing: "Writing…",
      subject: "Subject",
      copy: "Copy",
      copied: "Copied",
      clipboardError: "The clipboard is unavailable — select the text and copy it manually.",
      save: "Save to Gmail drafts",
      send: "Send the email",
      noteWrite: "We ask once more before sending — only you can send it.",
      noteRead: "A draft — the agent does not send it, and does not write it into your account.",
      saveText: "I'll write a draft into your Gmail account in reply to {sender}, on its own thread.",
      saveNotSend: "I will not send it",
      saveNotSendRest: "— you'll find it in Drafts, and you decide whether it goes out.",
      saveYes: "Confirm, save as a draft",
      saving: "Saving…",
      cancel: "Cancel",
      sendTitle: "This really will send the email now.",
      to: "To",
      from: "From",
      fromValue: "your Gmail account",
      sendWarn:
        "This cannot be undone. Read the text above — the square-bracketed parts ([like this]) " +
        "are yours to fill in before you send it.",
      sendYes: "Yes, send it now",
      sending: "Sending…",
      sent: "Sent.",
      savedNew: "Draft saved.",
      savedUpdated: "Draft updated.",
      openGmail: "Open it in Gmail",
    },
    intro: {
      lead:
        "Connect your Gmail account and the agent goes through the last 30 days of mail: it " +
        "sorts messages into categories, judges urgency, and tells you which ones need an " +
        "answer. For the ones you pick, it writes the reply too.",
      guarantees: [
        { t: "Read-only by default.", d: "Without the checkbox below it writes nothing into your account and does not ask for send access." },
        { t: "It never touches your existing mail.", d: "No labels, no stars, no deleting — not even with write access granted." },
        { t: "Writing and sending only with your permission.", d: "Even with the box ticked, we ask separately for each email before it writes a draft or sends anything." },
        { t: "We store nothing.", d: "The run expires by itself after 30 minutes. Closing the page signals the server and deletes it at once — and if that signal does not arrive, the 30-minute limit still ends it." },
      ],
    },
    disclosure: {
      summary: "What exactly do we ask for, and what happens to your data?",
      scopesTitle: "The Google permissions requested",
      scopeRead: "reading your mail. This is always needed, and by default it is the only permission we ask for.",
      scopeIdentity: "so we know which account we're looking at.",
      scopeComposeLead: "only if you tick draft writing.",
      scopeCompose:
        "This is what lets it place a draft in your account. Google has no draft-only permission, " +
        "so it would also allow sending — but this code never sends, and sending is blocked at " +
        "code level. Without the tick we do not request this permission at all.",
      readTitle: "What we read",
      read30: "At most 50 messages from the last 30 days. Nothing older, nothing more.",
      readFields: "Sender, subject, date and the message body.",
      readAttachLead: "An attachment only when the message body alone is too thin",
      readAttach:
        "— in a \"sending the material, details attached\" kind of email the substance is in the " +
        "document. In that case we extract the text from at most two files per email (Word, Excel, " +
        "PowerPoint, PDF, plain text; not from images or video). The file is not stored; only the " +
        "extracted text goes on to the classifier.",
      writeTitle: "What we write",
      writeNoneLead: "Without the tick:",
      writeNone: "nothing. The draft stays on the page and you copy it out.",
      writeDraft:
        "With draft writing: one single thing, per email, after your separate confirmation — a " +
        "reply draft in Gmail Drafts. We do not modify existing mail: no labelling, no starring, " +
        "no deleting, and we send nothing.",
      whereTitle: "Where it goes",
      whereLlm:
        "The message text is sent to OpenAI's API in a single classification call. By default the " +
        "provider does not use data submitted through the API for model training.",
      whereNoDb: "Nothing goes into a database. The run lives in the server's memory.",
      lifeTitle: "How long it lives, and how you delete it",
      life30: "The session expires by itself after 30 minutes.",
      lifeExit: "\"Log out\" deletes the run and the access immediately. Closing the page does the same when the browser's signal arrives; otherwise the 30-minute limit closes it.",
      lifeRevoke: "You can revoke the permission at Google at any time:",
      whoTitle: "Who is asking",
      whoText: "— write to us with any question or deletion request and we'll answer.",
    },
    closed: {
      title: "The agent is not public yet.",
      body:
        "Before asking anyone for Gmail access we publish the privacy notice and the company " +
        "details — until then we ask no one for mailbox access.",
      live: "We'll gladly show it live on our own account:",
      liveSubject: "I'd like to see the email agent live",
    },
    start: {
      cta: "See it on an example mailbox",
      starting: "Starting…",
      running: "Processing…",
      fetching: "Fetching the emails…",
      done: "Done",
      empty: "No emails to process from the last 30 days.",
      interrupted: "The analysis stopped. Please try again.",
      budget: "The agent has reached its daily budget.",
      noSubject: "(no subject)",
      note:
        "10 realistic Hungarian emails, right away, with no sign-in. The same agent runs on them " +
        "as on a live mailbox — it writes the replies too.",
      alt: "I'd rather try it on my own Gmail account →",
    },
    connect: {
      notConfigured: "The agent's Google access is not configured yet.",
      googleTitle: "What Google will show you.",
      googleBody:
        "Before it lets you through, a red \"Google hasn't verified this app\" screen appears. It " +
        "shows up for every app that asks for mailbox access and has not yet been through Google's " +
        "security assessment — it says nothing about the state of your account.",
      googleHow:
        "You get past it via Advanced → Go to… If that is uncomfortable right now, the example " +
        "mailbox shows everything with no sign-in.",
      back: "← Back to the example mailbox",
      optinTitle: "It may write drafts into my mailbox.",
      optinBody:
        "If you tick this, the agent puts the reply it wrote — after your separate confirmation, " +
        "per email — into Gmail Drafts, on its own thread. Sending is still only yours to do.",
      optinWarn:
        "Important: Google has no draft-only permission, so the consent screen will mention send " +
        "access as well. This code never sends an email — sending is blocked at code level — but " +
        "the permission you grant is broader than that. If that is uncomfortable, leave it " +
        "unticked: drafting works without it, you just copy the text out.",
      ctaRead: "Connect the Google account",
      ctaWrite: "Connect — read and write drafts",
      redirecting: "Redirecting…",
    },
    run: {
      sampleNoteTitle: "Example mailbox.",
      sampleNote:
        "The emails are invented — but the classification and the replies were produced just now, " +
        "by the same agent that would run on a live account.",
      starting: "Starting…",
      processed: "Messages processed",
      needsReply: "Needs a reply",
      showThese: "Show these",
      showAllShort: "Show every message",
      mostUrgent: "Most urgent",
      categories: "Category split",
      filterNote: "Only the messages awaiting a reply are shown.",
      showAllN: "Show all {n} messages",
      whyUrgent: "Why this urgency",
      nextStep: "Suggested next step",
      theEmail: "The message",
      empty: "(empty)",
      noEmails: "We found no messages from the last 30 days.",
      logout: "Log out and disconnect",
      foot: "Logging out disconnects your account immediately and deletes the analysis from the server.",
    },
    unreachable: {
      title: "The agent is unavailable right now.",
      body: "We could not reach the server — this is usually a few seconds while a new version starts.",
      retry: "Try again",
    },
  },

  de: {
    seo: {
      title: "E-Mail-Sortier-Agent — Live-Demo | AXIMBRA",
      description:
        "Live-Demo: Der Agent geht die letzten 30 Tage Ihres Postfachs durch, priorisiert die " +
        "Nachrichten und schreibt die Antworten. Standardmäßig nur lesend — senden kann er nicht.",
    },
    title: "E-Mail-Sortier-Agent",
    notConnected: "Nicht verbunden",
    err: {
      access_denied: "Sie haben den Google-Zugriff abgelehnt, oder der Vorgang wurde unterbrochen.",
      invalid_state: "Der Vorgang ist abgelaufen. Starten Sie die Verbindung neu.",
      token_exchange: "Der Austausch mit Google ist fehlgeschlagen. Bitte erneut versuchen.",
      no_email: "Google hat die E-Mail-Adresse des Kontos nicht zurückgegeben.",
      busy: "Gerade versuchen es zu viele gleichzeitig. Kommen Sie in ein paar Minuten wieder.",
      generic: "Fehler",
      unknown: "Unbekannter Fehler.",
    },
    urgency: { u5: "Sofort", u4: "Dringend", u3: "Mittel", u1: "Hat Zeit" },
    cat: {
      customer_question: "Kunde – Frage",
      customer_complaint: "Kunde – Beschwerde",
      opportunity: "Geschäftschance",
      invoice: "Rechnung / Finanzen",
      authority: "Behörde / amtlich",
      provider_notice: "Anbieter-Mitteilung",
      newsletter: "Newsletter / Marketing",
      spam: "Spam / unerwünscht",
      other: "Sonstiges",
    },
    tone: { group: "Tonfall", hivatalos: "Förmlich", kozvetlen: "Direkt" },
    draft: {
      write: "Antwort formulieren",
      rewrite: "Neu formulieren",
      writing: "Wird formuliert…",
      subject: "Betreff",
      copy: "Kopieren",
      copied: "Kopiert",
      clipboardError: "Die Zwischenablage ist nicht verfügbar — markieren Sie den Text und kopieren Sie ihn manuell.",
      save: "In Gmail-Entwürfe speichern",
      send: "E-Mail senden",
      noteWrite: "Vor dem Senden fragen wir noch einmal nach — senden können nur Sie.",
      noteRead: "Entwurf — der Agent sendet ihn nicht und schreibt ihn nicht in Ihr Konto.",
      saveText: "Ich schreibe einen Entwurf in Ihr Gmail-Konto als Antwort auf {sender}, im eigenen Verlauf.",
      saveNotSend: "Ich sende ihn nicht",
      saveNotSendRest: "— Sie finden ihn in den Entwürfen und entscheiden selbst, ob er rausgeht.",
      saveYes: "Bestätigen, als Entwurf speichern",
      saving: "Wird gespeichert…",
      cancel: "Abbrechen",
      sendTitle: "Jetzt wird diese E-Mail wirklich gesendet.",
      to: "Empfänger",
      from: "Absender",
      fromValue: "Ihr Gmail-Konto",
      sendWarn:
        "Das lässt sich nicht rückgängig machen. Lesen Sie den Text oben durch — die Stellen in " +
        "eckigen Klammern ([so]) müssen Sie vor dem Senden ausfüllen.",
      sendYes: "Ja, jetzt senden",
      sending: "Wird gesendet…",
      sent: "Gesendet.",
      savedNew: "Entwurf gespeichert.",
      savedUpdated: "Entwurf aktualisiert.",
      openGmail: "In Gmail öffnen",
    },
    intro: {
      lead:
        "Verbinden Sie Ihr Gmail-Konto, und der Agent geht die Mails der letzten 30 Tage durch: " +
        "Er ordnet sie Kategorien zu, bewertet die Dringlichkeit und sagt Ihnen, welche eine " +
        "Antwort brauchen. Für die von Ihnen gewählten formuliert er die Antwort gleich mit.",
      guarantees: [
        { t: "Standardmäßig nur lesend.", d: "Ohne das Häkchen unten schreibt er nichts in Ihr Konto und fragt auch kein Senderecht an." },
        { t: "Ihre vorhandenen Mails rührt er nie an.", d: "Kein Labeln, kein Markieren, kein Löschen — auch nicht mit Schreibrecht." },
        { t: "Schreiben und Senden nur mit Ihrer Erlaubnis.", d: "Auch mit Häkchen fragen wir pro E-Mail einzeln nach, bevor ein Entwurf entsteht oder etwas rausgeht." },
        { t: "Wir speichern nichts.", d: "Der Lauf verfällt nach 30 Minuten von selbst. Beim Schließen der Seite meldet der Browser das und er wird sofort gelöscht — kommt die Meldung nicht an, bleibt die 30-Minuten-Frist." },
      ],
    },
    disclosure: {
      summary: "Was genau fragen wir an, und was passiert mit Ihren Daten?",
      scopesTitle: "Die angefragten Google-Berechtigungen",
      scopeRead: "das Lesen Ihrer Mails. Das wird immer gebraucht und ist standardmäßig die einzige Berechtigung, die wir anfragen.",
      scopeIdentity: "damit wir wissen, welches Konto wir ansehen.",
      scopeComposeLead: "nur wenn Sie das Entwurfsschreiben ankreuzen.",
      scopeCompose:
        "Damit kann er einen Entwurf in Ihrem Konto ablegen. Google hat keine Nur-Entwurf-" +
        "Berechtigung, daher würde sie auch das Senden erlauben — dieser Code sendet jedoch nie, " +
        "das Senden ist auf Code-Ebene gesperrt. Ohne Häkchen fragen wir diese Berechtigung gar nicht an.",
      readTitle: "Was wir lesen",
      read30: "Höchstens 50 Nachrichten aus den letzten 30 Tagen. Nichts Älteres, nichts darüber hinaus.",
      readFields: "Absender, Betreff, Datum und den Text der Nachricht.",
      readAttachLead: "Einen Anhang nur dann, wenn der Nachrichtentext allein zu dünn ist",
      readAttach:
        "— bei einer Mail vom Typ „anbei die Unterlagen, Details im Anhang\" steckt der Kern im " +
        "Dokument. Dann lesen wir den Text aus höchstens zwei Dateien pro Mail aus (Word, Excel, " +
        "PowerPoint, PDF, einfacher Text; nicht aus Bildern oder Videos). Die Datei wird nicht " +
        "gespeichert, nur der ausgelesene Text geht weiter an die Klassifizierung.",
      writeTitle: "Was wir schreiben",
      writeNoneLead: "Ohne Häkchen:",
      writeNone: "nichts. Der Entwurf bleibt auf der Seite, Sie kopieren ihn heraus.",
      writeDraft:
        "Mit Entwurfsschreiben: genau eine Sache, pro E-Mail, nach Ihrer gesonderten Bestätigung — " +
        "einen Antwortentwurf in den Gmail-Entwürfen. Vorhandene Mails ändern wir nicht: kein " +
        "Labeln, kein Markieren, kein Löschen, und wir senden nichts.",
      whereTitle: "Wohin es geht",
      whereLlm:
        "Den Text der Nachricht senden wir in einem einzigen Klassifizierungsaufruf an die API von " +
        "OpenAI. Über die API eingereichte Daten nutzt der Anbieter standardmäßig nicht zum Training.",
      whereNoDb: "In eine Datenbank kommt nichts. Der Lauf lebt im Arbeitsspeicher des Servers.",
      lifeTitle: "Wie lange es lebt und wie Sie es löschen",
      life30: "Die Sitzung verfällt nach 30 Minuten von selbst.",
      lifeExit: "„Abmelden\" löscht Lauf und Zugriff sofort. Das Schließen der Seite ebenso, sofern die Meldung des Browsers ankommt; andernfalls beendet die 30-Minuten-Frist alles.",
      lifeRevoke: "Die Berechtigung können Sie bei Google jederzeit widerrufen:",
      whoTitle: "Wer fragt an",
      whoText: "— bei Fragen oder einem Löschwunsch schreiben Sie uns, wir antworten.",
    },
    closed: {
      title: "Der Agent ist derzeit nicht öffentlich.",
      body:
        "Bevor wir jemanden um Gmail-Zugriff bitten, veröffentlichen wir die Datenschutzerklärung " +
        "und die Unternehmensdaten — bis dahin fragen wir bei niemandem Postfachzugriff an.",
      live: "Live zeigen wir es gern an unserem eigenen Konto:",
      liveSubject: "Ich würde den E-Mail-Agenten live sehen",
    },
    start: {
      cta: "An einem Beispiel-Postfach ansehen",
      starting: "Wird gestartet…",
      running: "Wird verarbeitet…",
      fetching: "Mails werden abgerufen…",
      done: "Fertig",
      empty: "Keine verarbeitbaren Mails aus den letzten 30 Tagen.",
      interrupted: "Die Analyse wurde abgebrochen. Bitte erneut versuchen.",
      budget: "Der Agent hat sein Tagesbudget erreicht.",
      noSubject: "(kein Betreff)",
      note:
        "10 realitätsnahe ungarische Mails, sofort, ohne Anmeldung. Auf ihnen läuft derselbe Agent " +
        "wie auf einem echten Postfach — er schreibt auch die Antworten.",
      alt: "Lieber an meinem eigenen Gmail-Konto ansehen →",
    },
    connect: {
      notConfigured: "Der Google-Zugriff des Agenten ist noch nicht eingerichtet.",
      googleTitle: "Was Google Ihnen zeigen wird.",
      googleBody:
        "Bevor Google Sie durchlässt, erscheint ein roter Bildschirm „Google hat diese App nicht " +
        "überprüft\". Der erscheint bei jeder App, die Postfachzugriff anfragt und die " +
        "Sicherheitsprüfung von Google noch nicht durchlaufen hat — er sagt nichts über den " +
        "Zustand Ihres Kontos aus.",
      googleHow:
        "Weiter geht es über Erweitert → Weiter zu… Wenn Ihnen das gerade unangenehm ist: Das " +
        "Beispiel-Postfach zeigt alles ganz ohne Anmeldung.",
      back: "← Zurück zum Beispiel-Postfach",
      optinTitle: "Er darf Entwürfe in mein Postfach schreiben.",
      optinBody:
        "Wenn Sie das ankreuzen, legt der Agent die geschriebene Antwort — nach Ihrer gesonderten " +
        "Bestätigung, pro E-Mail — in den Gmail-Entwürfen ab, im eigenen Verlauf. Senden können " +
        "weiterhin nur Sie.",
      optinWarn:
        "Wichtig: Google hat keine Nur-Entwurf-Berechtigung, daher wird der Zustimmungsbildschirm " +
        "auch das Senderecht erwähnen. Dieser Code sendet nie eine E-Mail — das Senden ist auf " +
        "Code-Ebene gesperrt —, aber die Berechtigung, die Sie erteilen, ist breiter. Wenn Ihnen " +
        "das unangenehm ist, lassen Sie es leer: Das Formulieren funktioniert auch ohne Häkchen, " +
        "Sie müssen den Text nur herauskopieren.",
      ctaRead: "Mit dem Google-Konto verbinden",
      ctaWrite: "Verbinden — lesen und Entwürfe schreiben",
      redirecting: "Weiterleitung…",
    },
    run: {
      sampleNoteTitle: "Beispiel-Postfach.",
      sampleNote:
        "Die Mails sind erfunden — die Klassifizierung und die Antworten sind jedoch gerade eben " +
        "entstanden, mit demselben Agenten, der auf einem echten Konto laufen würde.",
      starting: "Startet…",
      processed: "Verarbeitete Mails",
      needsReply: "Antwort nötig",
      showThese: "Diese anzeigen",
      showAllShort: "Alle Mails anzeigen",
      mostUrgent: "Am dringendsten",
      categories: "Kategorienverteilung",
      filterNote: "Es werden nur die Mails angezeigt, die auf eine Antwort warten.",
      showAllN: "Alle {n} Mails anzeigen",
      whyUrgent: "Warum diese Dringlichkeit",
      nextStep: "Vorgeschlagener nächster Schritt",
      theEmail: "Die Nachricht",
      empty: "(leer)",
      noEmails: "Wir haben keine Mails aus den letzten 30 Tagen gefunden.",
      logout: "Abmelden und trennen",
      foot: "Mit dem Abmelden wird Ihr Konto sofort getrennt und die Analyse vom Server gelöscht.",
    },
    unreachable: {
      title: "Der Agent ist gerade nicht erreichbar.",
      body: "Wir konnten den Server nicht erreichen — meist sind das ein paar Sekunden, während eine neue Version startet.",
      retry: "Erneut versuchen",
    },
  },

  es: {
    seo: {
      title: "Agente clasificador de correo — demo en vivo | AXIMBRA",
      description:
        "Demo en vivo: el agente repasa los últimos 30 días de tu buzón, ordena los mensajes por " +
        "prioridad y escribe las respuestas. Por defecto solo lee — no puede enviar.",
    },
    title: "Agente clasificador de correo",
    notConnected: "Sin conectar",
    err: {
      access_denied: "Has rechazado el acceso de Google, o el proceso se ha interrumpido.",
      invalid_state: "El proceso ha caducado. Vuelve a iniciar la conexión.",
      token_exchange: "El intercambio con Google ha fallado. Inténtalo de nuevo.",
      no_email: "Google no ha devuelto la dirección de correo de la cuenta.",
      busy: "Ahora mismo hay demasiadas personas a la vez. Vuelve en unos minutos.",
      generic: "Error",
      unknown: "Error desconocido.",
    },
    urgency: { u5: "Inmediato", u4: "Urgente", u3: "Medio", u1: "Puede esperar" },
    cat: {
      customer_question: "Cliente – consulta",
      customer_complaint: "Cliente – reclamación",
      opportunity: "Oportunidad de negocio",
      invoice: "Factura / finanzas",
      authority: "Administración / oficial",
      provider_notice: "Aviso de proveedor",
      newsletter: "Boletín / marketing",
      spam: "Spam / no solicitado",
      other: "Otros",
    },
    tone: { group: "Tono", hivatalos: "Formal", kozvetlen: "Directo" },
    draft: {
      write: "Redactar la respuesta",
      rewrite: "Reformular",
      writing: "Redactando…",
      subject: "Asunto",
      copy: "Copiar",
      copied: "Copiado",
      clipboardError: "El portapapeles no está disponible — selecciona el texto y cópialo a mano.",
      save: "Guardar en borradores de Gmail",
      send: "Enviar el correo",
      noteWrite: "Antes de enviar volvemos a preguntar — enviarlo solo puedes tú.",
      noteRead: "Borrador — el agente no lo envía ni lo escribe en tu cuenta.",
      saveText: "Escribiré un borrador en tu cuenta de Gmail en respuesta a {sender}, en su propio hilo.",
      saveNotSend: "No lo enviaré",
      saveNotSendRest: "— lo encontrarás en Borradores y tú decides si sale.",
      saveYes: "Confirmo, guárdalo como borrador",
      saving: "Guardando…",
      cancel: "Cancelar",
      sendTitle: "Esto enviará el correo de verdad, ahora.",
      to: "Destinatario",
      from: "Remitente",
      fromValue: "tu cuenta de Gmail",
      sendWarn:
        "Esto no se puede deshacer. Lee el texto de arriba — las partes entre corchetes ([así]) " +
        "tienes que rellenarlas tú antes de enviarlo.",
      sendYes: "Sí, envíalo ahora",
      sending: "Enviando…",
      sent: "Enviado.",
      savedNew: "Borrador guardado.",
      savedUpdated: "Borrador actualizado.",
      openGmail: "Abrir en Gmail",
    },
    intro: {
      lead:
        "Conecta tu cuenta de Gmail y el agente repasará el correo de los últimos 30 días: lo " +
        "clasifica por categorías, valora la urgencia y te dice a cuáles hay que responder. Para " +
        "los que elijas, redacta también la respuesta.",
      guarantees: [
        { t: "Por defecto solo lee.", d: "Sin la casilla de abajo no escribe nada en tu cuenta ni pide permiso de envío." },
        { t: "Nunca toca tus correos existentes.", d: "No etiqueta, no destaca, no borra — ni siquiera con permiso de escritura." },
        { t: "Escribir y enviar solo con tu permiso.", d: "Incluso con la casilla marcada preguntamos por separado en cada correo antes de escribir un borrador o enviar nada." },
        { t: "No almacenamos nada.", d: "La ejecución caduca sola a los 30 minutos. Al cerrar la página el navegador avisa y se borra al instante — y si ese aviso no llega, queda el límite de 30 minutos." },
      ],
    },
    disclosure: {
      summary: "¿Qué pedimos exactamente y qué pasa con tus datos?",
      scopesTitle: "Los permisos de Google solicitados",
      scopeRead: "leer tu correo. Siempre hace falta y, por defecto, es el único permiso que pedimos.",
      scopeIdentity: "para saber qué cuenta estamos mirando.",
      scopeComposeLead: "solo si marcas la escritura de borradores.",
      scopeCompose:
        "Es lo que le permite dejar un borrador en tu cuenta. Google no tiene un permiso de " +
        "«solo borrador», así que también permitiría enviar — pero este código nunca envía: el " +
        "envío está bloqueado a nivel de código. Sin la marca ni siquiera pedimos este permiso.",
      readTitle: "Qué leemos",
      read30: "Como mucho 50 mensajes de los últimos 30 días. Nada más antiguo, nada más.",
      readFields: "Remitente, asunto, fecha y el cuerpo del mensaje.",
      readAttachLead: "Un adjunto solo cuando el cuerpo del mensaje se queda corto",
      readAttach:
        "— en un correo del tipo «te envío el material, detalles adjuntos» lo importante está en " +
        "el documento. En ese caso extraemos el texto de como mucho dos archivos por correo " +
        "(Word, Excel, PowerPoint, PDF, texto plano; de imágenes y vídeos no). El archivo no se " +
        "guarda; solo el texto extraído pasa al clasificador.",
      writeTitle: "Qué escribimos",
      writeNoneLead: "Sin la marca:",
      writeNone: "nada. El borrador se queda en la página y lo copias tú.",
      writeDraft:
        "Con escritura de borradores: una sola cosa, por correo, tras tu confirmación aparte — un " +
        "borrador de respuesta en Borradores de Gmail. No modificamos correos existentes: no " +
        "etiquetamos, no destacamos, no borramos, y no enviamos nada.",
      whereTitle: "Adónde va",
      whereLlm:
        "El texto del mensaje se envía a la API de OpenAI en una única llamada de clasificación. " +
        "Por defecto, el proveedor no usa los datos enviados por la API para entrenar modelos.",
      whereNoDb: "No va nada a ninguna base de datos. La ejecución vive en la memoria del servidor.",
      lifeTitle: "Cuánto dura y cómo lo borras",
      life30: "La sesión caduca sola a los 30 minutos.",
      lifeExit: "«Salir» borra la ejecución y el acceso al instante. Cerrar la página hace lo mismo si llega el aviso del navegador; si no, lo cierra el límite de 30 minutos.",
      lifeRevoke: "Puedes revocar el permiso en Google en cualquier momento:",
      whoTitle: "Quién lo pide",
      whoText: "— escríbenos con cualquier duda o solicitud de borrado y te respondemos.",
    },
    closed: {
      title: "El agente todavía no es público.",
      body:
        "Antes de pedirle acceso a Gmail a nadie publicamos la política de privacidad y los datos " +
        "de la empresa — hasta entonces no pedimos acceso al buzón de nadie.",
      live: "Con gusto te lo enseñamos en vivo en nuestra propia cuenta:",
      liveSubject: "Me gustaría ver el agente de correo en vivo",
    },
    start: {
      cta: "Verlo en un buzón de ejemplo",
      starting: "Iniciando…",
      running: "Procesando…",
      fetching: "Descargando los correos…",
      done: "Listo",
      empty: "No hay correos que procesar de los últimos 30 días.",
      interrupted: "El análisis se ha interrumpido. Inténtalo de nuevo.",
      budget: "El agente ha alcanzado su presupuesto diario.",
      noSubject: "(sin asunto)",
      note:
        "10 correos húngaros realistas, al instante, sin registrarse. Sobre ellos corre el mismo " +
        "agente que en un buzón real — también escribe las respuestas.",
      alt: "Prefiero probarlo en mi propia cuenta de Gmail →",
    },
    connect: {
      notConfigured: "El acceso de Google del agente aún no está configurado.",
      googleTitle: "Lo que te va a mostrar Google.",
      googleBody:
        "Antes de dejarte pasar aparece una pantalla roja: «Google no ha verificado esta " +
        "aplicación». Sale en toda aplicación que pide acceso al buzón y aún no ha pasado la " +
        "evaluación de seguridad de Google — no dice nada del estado de tu cuenta.",
      googleHow:
        "Se continúa por Configuración avanzada → Ir a… Si ahora mismo te resulta incómodo, el " +
        "buzón de ejemplo lo enseña todo sin registrarse.",
      back: "← Volver al buzón de ejemplo",
      optinTitle: "Puede escribir borradores en mi buzón.",
      optinBody:
        "Si lo marcas, el agente deja la respuesta redactada — tras tu confirmación aparte, correo " +
        "a correo — en Borradores de Gmail, en su propio hilo. Enviarlo sigue siendo cosa tuya.",
      optinWarn:
        "Importante: Google no tiene un permiso de «solo borrador», así que la pantalla de " +
        "consentimiento mencionará también el permiso de envío. Este código nunca envía un correo " +
        "— el envío está bloqueado a nivel de código —, pero el permiso que concedes es más " +
        "amplio. Si eso te incomoda, déjalo sin marcar: la redacción funciona igual, solo hay que " +
        "copiar el texto.",
      ctaRead: "Conectar la cuenta de Google",
      ctaWrite: "Conectar — leer y escribir borradores",
      redirecting: "Redirigiendo…",
    },
    run: {
      sampleNoteTitle: "Buzón de ejemplo.",
      sampleNote:
        "Los correos son inventados — pero la clasificación y las respuestas se han generado ahora " +
        "mismo, con el mismo agente que correría en una cuenta real.",
      starting: "Arrancando…",
      processed: "Correos procesados",
      needsReply: "Necesita respuesta",
      showThese: "Mostrar estos",
      showAllShort: "Mostrar todos los correos",
      mostUrgent: "Más urgente",
      categories: "Reparto por categorías",
      filterNote: "Solo se ven los correos que esperan respuesta.",
      showAllN: "Mostrar los {n} correos",
      whyUrgent: "Por qué esta urgencia",
      nextStep: "Siguiente paso sugerido",
      theEmail: "El mensaje",
      empty: "(vacío)",
      noEmails: "No hemos encontrado correos de los últimos 30 días.",
      logout: "Salir y desconectar",
      foot: "Al salir, tu cuenta se desconecta al instante y el análisis se borra del servidor.",
    },
    unreachable: {
      title: "El agente no está disponible ahora mismo.",
      body: "No hemos podido alcanzar el servidor — suelen ser unos segundos mientras arranca una versión nueva.",
      retry: "Inténtalo de nuevo",
    },
  },

  fr: {
    seo: {
      title: "Agent de tri des e-mails — démo en direct | AXIMBRA",
      description:
        "Démo en direct : l'agent parcourt les 30 derniers jours de votre boîte, classe les " +
        "messages par priorité et rédige les réponses. En lecture seule par défaut — il ne peut pas envoyer.",
    },
    title: "Agent de tri des e-mails",
    notConnected: "Non connecté",
    err: {
      access_denied: "Vous avez refusé l'accès Google, ou la procédure a été interrompue.",
      invalid_state: "La procédure a expiré. Relancez la connexion.",
      token_exchange: "L'échange avec Google a échoué. Réessayez.",
      no_email: "Google n'a pas renvoyé l'adresse e-mail du compte.",
      busy: "Trop de monde essaie en même temps. Revenez dans quelques minutes.",
      generic: "Erreur",
      unknown: "Erreur inconnue.",
    },
    urgency: { u5: "Immédiat", u4: "Urgent", u3: "Moyen", u1: "Peut attendre" },
    cat: {
      customer_question: "Client – question",
      customer_complaint: "Client – réclamation",
      opportunity: "Opportunité commerciale",
      invoice: "Facture / finances",
      authority: "Administration / officiel",
      provider_notice: "Avis de prestataire",
      newsletter: "Newsletter / marketing",
      spam: "Spam / non sollicité",
      other: "Autre",
    },
    tone: { group: "Ton", hivatalos: "Formel", kozvetlen: "Direct" },
    draft: {
      write: "Rédiger la réponse",
      rewrite: "Reformuler",
      writing: "Rédaction…",
      subject: "Objet",
      copy: "Copier",
      copied: "Copié",
      clipboardError: "Le presse-papiers n'est pas accessible — sélectionnez le texte et copiez-le à la main.",
      save: "Enregistrer dans les brouillons Gmail",
      send: "Envoyer l'e-mail",
      noteWrite: "Nous redemandons avant l'envoi — vous seul pouvez l'envoyer.",
      noteRead: "Brouillon — l'agent ne l'envoie pas et ne l'écrit pas dans votre compte.",
      saveText: "J'écris un brouillon dans votre compte Gmail en réponse à {sender}, dans son propre fil.",
      saveNotSend: "Je ne l'envoie pas",
      saveNotSendRest: "— vous le trouverez dans les Brouillons et c'est vous qui décidez.",
      saveYes: "Je confirme, enregistre-le en brouillon",
      saving: "Enregistrement…",
      cancel: "Annuler",
      sendTitle: "Cet e-mail va vraiment partir, maintenant.",
      to: "Destinataire",
      from: "Expéditeur",
      fromValue: "votre compte Gmail",
      sendWarn:
        "C'est irréversible. Relisez le texte ci-dessus — les passages entre crochets ([comme " +
        "ceci]) sont à compléter par vous avant l'envoi.",
      sendYes: "Oui, envoyer maintenant",
      sending: "Envoi…",
      sent: "Envoyé.",
      savedNew: "Brouillon enregistré.",
      savedUpdated: "Brouillon mis à jour.",
      openGmail: "Ouvrir dans Gmail",
    },
    intro: {
      lead:
        "Connectez votre compte Gmail et l'agent parcourt les messages des 30 derniers jours : il " +
        "les classe par catégorie, évalue l'urgence et vous dit lesquels attendent une réponse. " +
        "Pour ceux que vous choisissez, il rédige aussi la réponse.",
      guarantees: [
        { t: "En lecture seule par défaut.", d: "Sans la case ci-dessous, il n'écrit rien dans votre compte et ne demande pas le droit d'envoi." },
        { t: "Il ne touche jamais à vos messages existants.", d: "Pas de libellé, pas d'étoile, pas de suppression — même avec le droit d'écriture." },
        { t: "Écrire et envoyer seulement avec votre accord.", d: "Même la case cochée, nous redemandons message par message avant d'écrire un brouillon ou d'envoyer quoi que ce soit." },
        { t: "Nous ne stockons rien.", d: "L'exécution expire d'elle-même au bout de 30 minutes. À la fermeture de la page, le navigateur prévient et elle est supprimée aussitôt — si ce signal n'arrive pas, la limite de 30 minutes s'applique." },
      ],
    },
    disclosure: {
      summary: "Que demandons-nous exactement, et qu'advient-il de vos données ?",
      scopesTitle: "Les autorisations Google demandées",
      scopeRead: "la lecture de vos messages. Toujours nécessaire, et par défaut c'est la seule autorisation demandée.",
      scopeIdentity: "pour savoir quel compte nous consultons.",
      scopeComposeLead: "uniquement si vous cochez l'écriture de brouillons.",
      scopeCompose:
        "C'est ce qui lui permet de déposer un brouillon dans votre compte. Google n'a pas " +
        "d'autorisation « brouillon seul », elle permettrait donc aussi l'envoi — mais ce code " +
        "n'envoie jamais : l'envoi est bloqué au niveau du code. Sans la case, cette autorisation " +
        "n'est même pas demandée.",
      readTitle: "Ce que nous lisons",
      read30: "Au plus 50 messages des 30 derniers jours. Rien de plus ancien, rien de plus.",
      readFields: "Expéditeur, objet, date et le corps du message.",
      readAttachLead: "Une pièce jointe seulement si le corps du message ne suffit pas",
      readAttach:
        "— dans un e-mail du type « je vous envoie le dossier, détails en pièce jointe », " +
        "l'essentiel est dans le document. Nous extrayons alors le texte de deux fichiers au plus " +
        "par message (Word, Excel, PowerPoint, PDF, texte brut ; pas depuis les images ni les " +
        "vidéos). Le fichier n'est pas conservé ; seul le texte extrait passe au classement.",
      writeTitle: "Ce que nous écrivons",
      writeNoneLead: "Sans la case :",
      writeNone: "rien. Le brouillon reste sur la page, c'est vous qui le copiez.",
      writeDraft:
        "Avec l'écriture de brouillons : une seule chose, message par message, après votre " +
        "confirmation distincte — un brouillon de réponse dans les Brouillons Gmail. Nous ne " +
        "modifions pas les messages existants : pas de libellé, pas d'étoile, pas de suppression, " +
        "et nous n'envoyons rien.",
      whereTitle: "Où cela va",
      whereLlm:
        "Le texte du message est envoyé à l'API d'OpenAI en un seul appel de classement. Par " +
        "défaut, le fournisseur n'utilise pas les données soumises via l'API pour entraîner ses modèles.",
      whereNoDb: "Rien ne va en base de données. L'exécution vit dans la mémoire du serveur.",
      lifeTitle: "Combien de temps cela vit, et comment l'effacer",
      life30: "La session expire d'elle-même au bout de 30 minutes.",
      lifeExit: "« Se déconnecter » supprime immédiatement l'exécution et l'accès. Fermer la page fait de même si le signal du navigateur arrive ; sinon la limite de 30 minutes s'en charge.",
      lifeRevoke: "Vous pouvez révoquer l'autorisation chez Google à tout moment :",
      whoTitle: "Qui demande",
      whoText: "— écrivez-nous pour toute question ou demande de suppression, nous répondons.",
    },
    closed: {
      title: "L'agent n'est pas encore public.",
      body:
        "Avant de demander un accès Gmail à qui que ce soit, nous publions la politique de " +
        "confidentialité et les mentions légales — d'ici là, nous ne demandons l'accès à aucune boîte.",
      live: "Nous vous le montrons volontiers en direct sur notre propre compte :",
      liveSubject: "Je voudrais voir l'agent e-mail en direct",
    },
    start: {
      cta: "Le voir sur une boîte d'exemple",
      starting: "Démarrage…",
      running: "Traitement en cours…",
      fetching: "Récupération des e-mails…",
      done: "Terminé",
      empty: "Aucun e-mail à traiter sur les 30 derniers jours.",
      interrupted: "L'analyse s'est interrompue. Réessayez.",
      budget: "L'agent a atteint son budget quotidien.",
      noSubject: "(sans objet)",
      note:
        "10 e-mails hongrois réalistes, tout de suite, sans connexion. Le même agent tourne " +
        "dessus que sur une vraie boîte — il rédige aussi les réponses.",
      alt: "Je préfère l'essayer sur mon propre compte Gmail →",
    },
    connect: {
      notConfigured: "L'accès Google de l'agent n'est pas encore configuré.",
      googleTitle: "Ce que Google va vous montrer.",
      googleBody:
        "Avant de vous laisser passer, un écran rouge « Google n'a pas validé cette application » " +
        "apparaît. Il apparaît pour toute application qui demande l'accès à une boîte et n'a pas " +
        "encore passé l'audit de sécurité de Google — il ne dit rien de l'état de votre compte.",
      googleHow:
        "On continue via Paramètres avancés → Accéder à… Si cela vous gêne pour l'instant, la " +
        "boîte d'exemple montre tout sans connexion.",
      back: "← Retour à la boîte d'exemple",
      optinTitle: "Il peut écrire des brouillons dans ma boîte.",
      optinBody:
        "Si vous cochez, l'agent dépose la réponse rédigée — après votre confirmation distincte, " +
        "message par message — dans les Brouillons Gmail, dans son propre fil. L'envoi reste à vous seul.",
      optinWarn:
        "Important : Google n'a pas d'autorisation « brouillon seul », l'écran de consentement " +
        "mentionnera donc aussi le droit d'envoi. Ce code n'envoie jamais d'e-mail — l'envoi est " +
        "bloqué au niveau du code —, mais l'autorisation que vous accordez est plus large. Si cela " +
        "vous gêne, laissez la case vide : la rédaction fonctionne sans, il suffit de copier le texte.",
      ctaRead: "Connecter le compte Google",
      ctaWrite: "Connecter — lecture et écriture de brouillons",
      redirecting: "Redirection…",
    },
    run: {
      sampleNoteTitle: "Boîte d'exemple.",
      sampleNote:
        "Les messages sont inventés — mais le classement et les réponses viennent d'être produits, " +
        "par le même agent qui tournerait sur un compte réel.",
      starting: "Démarrage…",
      processed: "Messages traités",
      needsReply: "Réponse attendue",
      showThese: "Afficher ceux-ci",
      showAllShort: "Afficher tous les messages",
      mostUrgent: "Le plus urgent",
      categories: "Répartition par catégorie",
      filterNote: "Seuls les messages en attente de réponse sont affichés.",
      showAllN: "Afficher les {n} messages",
      whyUrgent: "Pourquoi cette urgence",
      nextStep: "Prochaine étape suggérée",
      theEmail: "Le message",
      empty: "(vide)",
      noEmails: "Nous n'avons trouvé aucun message des 30 derniers jours.",
      logout: "Se déconnecter",
      foot: "La déconnexion coupe immédiatement l'accès à votre compte et efface l'analyse du serveur.",
    },
    unreachable: {
      title: "L'agent est indisponible pour le moment.",
      body: "Nous n'avons pas pu joindre le serveur — c'est en général quelques secondes, le temps qu'une nouvelle version démarre.",
      retry: "Réessayer",
    },
  },

  it: {
    seo: {
      title: "Agente di smistamento e-mail — demo dal vivo | AXIMBRA",
      description:
        "Demo dal vivo: l'agente ripercorre gli ultimi 30 giorni della tua casella, ordina i " +
        "messaggi per priorità e scrive le risposte. Di base legge soltanto — non può inviare.",
    },
    title: "Agente di smistamento e-mail",
    notConnected: "Non collegato",
    err: {
      access_denied: "Hai rifiutato l'accesso Google, oppure la procedura si è interrotta.",
      invalid_state: "La procedura è scaduta. Avvia di nuovo il collegamento.",
      token_exchange: "Lo scambio con Google non è riuscito. Riprova.",
      no_email: "Google non ha restituito l'indirizzo e-mail dell'account.",
      busy: "In questo momento ci stanno provando in troppi. Torna tra qualche minuto.",
      generic: "Errore",
      unknown: "Errore sconosciuto.",
    },
    urgency: { u5: "Immediato", u4: "Urgente", u3: "Medio", u1: "Può attendere" },
    cat: {
      customer_question: "Cliente – domanda",
      customer_complaint: "Cliente – reclamo",
      opportunity: "Opportunità commerciale",
      invoice: "Fattura / contabilità",
      authority: "Pubblica amministrazione",
      provider_notice: "Avviso del fornitore",
      newsletter: "Newsletter / marketing",
      spam: "Spam / non richiesto",
      other: "Altro",
    },
    tone: { group: "Tono", hivatalos: "Formale", kozvetlen: "Diretto" },
    draft: {
      write: "Scrivi la risposta",
      rewrite: "Riformula",
      writing: "Sto scrivendo…",
      subject: "Oggetto",
      copy: "Copia",
      copied: "Copiato",
      clipboardError: "Gli appunti non sono disponibili — seleziona il testo e copialo a mano.",
      save: "Salva nelle bozze di Gmail",
      send: "Invia l'e-mail",
      noteWrite: "Prima dell'invio chiediamo ancora conferma — inviarla puoi solo tu.",
      noteRead: "Bozza — l'agente non la invia e non la scrive nel tuo account.",
      saveText: "Scrivo una bozza nel tuo account Gmail in risposta a {sender}, nella sua conversazione.",
      saveNotSend: "Non la invio",
      saveNotSendRest: "— la trovi nelle Bozze e decidi tu se farla partire.",
      saveYes: "Confermo, salvala come bozza",
      saving: "Salvataggio…",
      cancel: "Annulla",
      sendTitle: "Questa e-mail partirà davvero, adesso.",
      to: "Destinatario",
      from: "Mittente",
      fromValue: "il tuo account Gmail",
      sendWarn:
        "Non è reversibile. Rileggi il testo qui sopra — le parti tra parentesi quadre ([così]) " +
        "devi compilarle tu prima di inviare.",
      sendYes: "Sì, invia adesso",
      sending: "Invio…",
      sent: "Inviata.",
      savedNew: "Bozza salvata.",
      savedUpdated: "Bozza aggiornata.",
      openGmail: "Apri in Gmail",
    },
    intro: {
      lead:
        "Collega il tuo account Gmail e l'agente ripercorre la posta degli ultimi 30 giorni: la " +
        "divide in categorie, valuta l'urgenza e ti dice a quali messaggi serve una risposta. Per " +
        "quelli che scegli, scrive anche la risposta.",
      guarantees: [
        { t: "Di base legge soltanto.", d: "Senza la casella qui sotto non scrive nulla nel tuo account e non chiede il permesso di invio." },
        { t: "Non tocca mai la posta esistente.", d: "Niente etichette, niente stelle, niente cancellazioni — nemmeno con il permesso di scrittura." },
        { t: "Scrive e invia solo con il tuo permesso.", d: "Anche con la casella spuntata chiediamo conferma per ogni singolo messaggio prima di scrivere una bozza o inviare qualcosa." },
        { t: "Non conserviamo nulla.", d: "L'esecuzione scade da sola dopo 30 minuti. Chiudendo la pagina il browser lo segnala e viene cancellata subito — se il segnale non arriva, resta il limite di 30 minuti." },
      ],
    },
    disclosure: {
      summary: "Che cosa chiediamo esattamente e che fine fanno i tuoi dati?",
      scopesTitle: "I permessi Google richiesti",
      scopeRead: "la lettura della tua posta. Serve sempre e, di base, è l'unico permesso che chiediamo.",
      scopeIdentity: "per sapere quale account stiamo guardando.",
      scopeComposeLead: "solo se spunti la scrittura delle bozze.",
      scopeCompose:
        "È ciò che gli permette di lasciare una bozza nel tuo account. Google non ha un permesso " +
        "di «sola bozza», quindi consentirebbe anche l'invio — ma questo codice non invia mai: " +
        "l'invio è bloccato a livello di codice. Senza la spunta questo permesso non viene nemmeno chiesto.",
      readTitle: "Che cosa leggiamo",
      read30: "Al massimo 50 messaggi degli ultimi 30 giorni. Niente di più vecchio, niente di più.",
      readFields: "Mittente, oggetto, data e il testo del messaggio.",
      readAttachLead: "Un allegato solo quando il testo del messaggio da solo non basta",
      readAttach:
        "— in un'e-mail del tipo «ti mando il materiale, dettagli in allegato» la sostanza sta nel " +
        "documento. In quel caso estraiamo il testo da al massimo due file per messaggio (Word, " +
        "Excel, PowerPoint, PDF, testo semplice; non da immagini e video). Il file non viene " +
        "conservato; solo il testo estratto passa alla classificazione.",
      writeTitle: "Che cosa scriviamo",
      writeNoneLead: "Senza la spunta:",
      writeNone: "nulla. La bozza resta sulla pagina e la copi tu.",
      writeDraft:
        "Con la scrittura delle bozze: una cosa sola, per ogni messaggio, dopo la tua conferma " +
        "separata — una bozza di risposta nelle Bozze di Gmail. Non modifichiamo la posta " +
        "esistente: niente etichette, niente stelle, niente cancellazioni, e non inviamo nulla.",
      whereTitle: "Dove finisce",
      whereLlm:
        "Il testo del messaggio viene inviato all'API di OpenAI in una sola chiamata di " +
        "classificazione. Per impostazione predefinita il fornitore non usa i dati inviati " +
        "tramite API per addestrare i modelli.",
      whereNoDb: "Nulla finisce in un database. L'esecuzione vive nella memoria del server.",
      lifeTitle: "Quanto dura e come si cancella",
      life30: "La sessione scade da sola dopo 30 minuti.",
      lifeExit: "«Esci» cancella subito l'esecuzione e l'accesso. Chiudere la pagina fa lo stesso se il segnale del browser arriva; altrimenti ci pensa il limite di 30 minuti.",
      lifeRevoke: "Puoi revocare il permesso presso Google in qualsiasi momento:",
      whoTitle: "Chi lo chiede",
      whoText: "— scrivici per qualsiasi domanda o richiesta di cancellazione e rispondiamo.",
    },
    closed: {
      title: "L'agente non è ancora pubblico.",
      body:
        "Prima di chiedere a qualcuno l'accesso a Gmail pubblichiamo l'informativa sulla privacy e " +
        "i dati dell'attività — fino ad allora non chiediamo a nessuno l'accesso alla casella.",
      live: "Volentieri te lo mostriamo dal vivo sul nostro account:",
      liveSubject: "Vorrei vedere l'agente e-mail dal vivo",
    },
    start: {
      cta: "Guardalo su una casella di esempio",
      starting: "Avvio…",
      running: "Elaborazione in corso…",
      fetching: "Recupero delle e-mail…",
      done: "Fatto",
      empty: "Nessuna e-mail da elaborare negli ultimi 30 giorni.",
      interrupted: "L'analisi si è interrotta. Riprova.",
      budget: "L'agente ha raggiunto il budget giornaliero.",
      noSubject: "(senza oggetto)",
      note:
        "10 e-mail ungheresi realistiche, subito, senza accesso. Su di esse gira lo stesso agente " +
        "che girerebbe su una casella vera — scrive anche le risposte.",
      alt: "Preferisco provarlo sul mio account Gmail →",
    },
    connect: {
      notConfigured: "L'accesso Google dell'agente non è ancora configurato.",
      googleTitle: "Che cosa ti mostrerà Google.",
      googleBody:
        "Prima di farti passare compare una schermata rossa: «Google non ha verificato questa " +
        "app». Compare per ogni applicazione che chiede l'accesso alla casella e non ha ancora " +
        "superato la verifica di sicurezza di Google — non dice nulla sullo stato del tuo account.",
      googleHow:
        "Si prosegue da Avanzate → Vai a… Se in questo momento ti mette a disagio, la casella di " +
        "esempio mostra tutto senza accesso.",
      back: "← Torna alla casella di esempio",
      optinTitle: "Può scrivere bozze nella mia casella.",
      optinBody:
        "Se lo spunti, l'agente mette la risposta scritta — dopo la tua conferma separata, " +
        "messaggio per messaggio — nelle Bozze di Gmail, nella sua conversazione. Inviarla resta " +
        "comunque solo tuo.",
      optinWarn:
        "Importante: Google non ha un permesso di «sola bozza», quindi la schermata di consenso " +
        "citerà anche il diritto di invio. Questo codice non invia mai un'e-mail — l'invio è " +
        "bloccato a livello di codice —, ma il permesso che concedi è più ampio. Se questo ti " +
        "mette a disagio, lascialo vuoto: la stesura funziona anche senza, basta copiare il testo.",
      ctaRead: "Collega l'account Google",
      ctaWrite: "Collega — lettura e scrittura di bozze",
      redirecting: "Reindirizzamento…",
    },
    run: {
      sampleNoteTitle: "Casella di esempio.",
      sampleNote:
        "Le e-mail sono inventate — ma la classificazione e le risposte sono state prodotte " +
        "adesso, dallo stesso agente che girerebbe su un account vero.",
      starting: "Avvio…",
      processed: "Messaggi elaborati",
      needsReply: "Serve una risposta",
      showThese: "Mostra questi",
      showAllShort: "Mostra tutti i messaggi",
      mostUrgent: "Più urgenti",
      categories: "Distribuzione per categoria",
      filterNote: "Sono visibili solo i messaggi in attesa di risposta.",
      showAllN: "Mostra tutti i {n} messaggi",
      whyUrgent: "Perché questa urgenza",
      nextStep: "Prossimo passo suggerito",
      theEmail: "Il messaggio",
      empty: "(vuoto)",
      noEmails: "Non abbiamo trovato messaggi degli ultimi 30 giorni.",
      logout: "Esci e scollega",
      foot: "Uscendo, il tuo account viene scollegato subito e l'analisi viene cancellata dal server.",
    },
    unreachable: {
      title: "L'agente non è raggiungibile in questo momento.",
      body: "Non siamo riusciti a raggiungere il server — di solito sono pochi secondi, il tempo che parta una nuova versione.",
      retry: "Riprova",
    },
  },

  ro: {
    seo: {
      title: "Agent de triere a e-mailurilor — demo live | AXIMBRA",
      description:
        "Demo live: agentul parcurge ultimele 30 de zile din căsuța ta, ordonează mesajele după " +
        "urgență și scrie răspunsurile. Implicit doar citește — nu poate trimite.",
    },
    title: "Agent de triere a e-mailurilor",
    notConnected: "Neconectat",
    err: {
      access_denied: "Ai refuzat accesul Google sau procesul a fost întrerupt.",
      invalid_state: "Procesul a expirat. Pornește din nou conectarea.",
      token_exchange: "Schimbul cu Google nu a reușit. Încearcă din nou.",
      no_email: "Google nu a returnat adresa de e-mail a contului.",
      busy: "Acum încearcă prea mulți deodată. Revino peste câteva minute.",
      generic: "Eroare",
      unknown: "Eroare necunoscută.",
    },
    urgency: { u5: "Imediat", u4: "Urgent", u3: "Mediu", u1: "Poate aștepta" },
    cat: {
      customer_question: "Client – întrebare",
      customer_complaint: "Client – reclamație",
      opportunity: "Oportunitate de afaceri",
      invoice: "Factură / finanțe",
      authority: "Autoritate / oficial",
      provider_notice: "Notificare de la furnizor",
      newsletter: "Newsletter / marketing",
      spam: "Spam / nesolicitat",
      other: "Altele",
    },
    tone: { group: "Ton", hivatalos: "Formal", kozvetlen: "Direct" },
    draft: {
      write: "Scrie răspunsul",
      rewrite: "Reformulează",
      writing: "Se scrie…",
      subject: "Subiect",
      copy: "Copiază",
      copied: "Copiat",
      clipboardError: "Clipboardul nu este disponibil — selectează textul și copiază-l manual.",
      save: "Salvează în ciornele Gmail",
      send: "Trimite e-mailul",
      noteWrite: "Înainte de trimitere mai întrebăm o dată — doar tu îl poți trimite.",
      noteRead: "Ciornă — agentul nu o trimite și nu o scrie în contul tău.",
      saveText: "Scriu o ciornă în contul tău Gmail ca răspuns la {sender}, pe firul ei.",
      saveNotSend: "Nu o trimit",
      saveNotSendRest: "— o găsești în Ciorne și tu decizi dacă pleacă.",
      saveYes: "Confirm, salveaz-o ca ciornă",
      saving: "Se salvează…",
      cancel: "Renunță",
      sendTitle: "Acest e-mail chiar va pleca acum.",
      to: "Destinatar",
      from: "Expeditor",
      fromValue: "contul tău Gmail",
      sendWarn:
        "Nu se poate anula. Citește textul de mai sus — părțile dintre paranteze drepte ([așa]) " +
        "trebuie completate de tine înainte de trimitere.",
      sendYes: "Da, trimite acum",
      sending: "Se trimite…",
      sent: "Trimis.",
      savedNew: "Ciornă salvată.",
      savedUpdated: "Ciornă actualizată.",
      openGmail: "Deschide în Gmail",
    },
    intro: {
      lead:
        "Conectează-ți contul Gmail și agentul parcurge mesajele din ultimele 30 de zile: le " +
        "împarte pe categorii, evaluează urgența și îți spune la care trebuie să răspunzi. Pentru " +
        "cele alese, scrie și răspunsul.",
      guarantees: [
        { t: "Implicit doar citește.", d: "Fără bifa de mai jos nu scrie nimic în contul tău și nu cere nici dreptul de trimitere." },
        { t: "Nu se atinge niciodată de mesajele existente.", d: "Fără etichete, fără stele, fără ștergeri — nici măcar cu drept de scriere." },
        { t: "Scrie și trimite doar cu permisiunea ta.", d: "Chiar și cu bifa pusă întrebăm separat la fiecare mesaj înainte să scrie o ciornă sau să trimită ceva." },
        { t: "Nu stocăm nimic.", d: "Rularea expiră singură după 30 de minute. La închiderea paginii browserul anunță serverul și se șterge imediat — dacă semnalul nu ajunge, rămâne limita de 30 de minute." },
      ],
    },
    disclosure: {
      summary: "Ce cerem mai exact și ce se întâmplă cu datele tale?",
      scopesTitle: "Permisiunile Google cerute",
      scopeRead: "citirea mesajelor tale. Este mereu necesară și, implicit, este singura permisiune pe care o cerem.",
      scopeIdentity: "ca să știm ce cont ne uităm.",
      scopeComposeLead: "doar dacă bifezi scrierea de ciorne.",
      scopeCompose:
        "Asta îi permite să lase o ciornă în contul tău. Google nu are o permisiune „doar ciornă\", " +
        "așa că aceasta ar permite și trimiterea — dar acest cod nu trimite niciodată: trimiterea " +
        "este blocată la nivel de cod. Fără bifă nici nu cerem această permisiune.",
      readTitle: "Ce citim",
      read30: "Cel mult 50 de mesaje din ultimele 30 de zile. Nimic mai vechi, nimic în plus.",
      readFields: "Expeditor, subiect, dată și textul mesajului.",
      readAttachLead: "Un atașament doar când textul mesajului nu este suficient",
      readAttach:
        "— într-un e-mail de tipul „îți trimit materialul, detalii în atașament\" esențialul este " +
        "în document. Atunci extragem textul din cel mult două fișiere per mesaj (Word, Excel, " +
        "PowerPoint, PDF, text simplu; nu din imagini și clipuri). Fișierul nu este păstrat; doar " +
        "textul extras merge mai departe la clasificare.",
      writeTitle: "Ce scriem",
      writeNoneLead: "Fără bifă:",
      writeNone: "nimic. Ciorna rămâne pe pagină și o copiezi tu.",
      writeDraft:
        "Cu scrierea de ciorne: un singur lucru, pentru fiecare mesaj, după confirmarea ta " +
        "separată — o ciornă de răspuns în Ciornele Gmail. Nu modificăm mesajele existente: fără " +
        "etichete, fără stele, fără ștergeri și nu trimitem nimic.",
      whereTitle: "Unde ajunge",
      whereLlm:
        "Textul mesajului este trimis către API-ul OpenAI într-un singur apel de clasificare. " +
        "Implicit, furnizorul nu folosește datele trimise prin API pentru antrenarea modelelor.",
      whereNoDb: "Nimic nu ajunge într-o bază de date. Rularea trăiește în memoria serverului.",
      lifeTitle: "Cât trăiește și cum o ștergi",
      life30: "Sesiunea expiră singură după 30 de minute.",
      lifeExit: "„Ieșire\" șterge imediat rularea și accesul. Închiderea paginii face la fel dacă semnalul browserului ajunge; altfel se închide la limita de 30 de minute.",
      lifeRevoke: "Poți retrage permisiunea de la Google oricând:",
      whoTitle: "Cine cere",
      whoText: "— scrie-ne pentru orice întrebare sau cerere de ștergere și îți răspundem.",
    },
    closed: {
      title: "Agentul nu este încă public.",
      body:
        "Înainte să cerem cuiva acces la Gmail publicăm informarea privind prelucrarea datelor și " +
        "datele firmei — până atunci nu cerem nimănui acces la căsuță.",
      live: "Cu plăcere ți-l arătăm live pe contul nostru:",
      liveSubject: "Aș vrea să văd live agentul de e-mail",
    },
    start: {
      cta: "Vezi-l pe o căsuță de exemplu",
      starting: "Pornire…",
      running: "Se procesează…",
      fetching: "Se descarcă e-mailurile…",
      done: "Gata",
      empty: "Niciun e-mail de procesat din ultimele 30 de zile.",
      interrupted: "Analiza s-a întrerupt. Încearcă din nou.",
      budget: "Agentul și-a atins bugetul zilnic.",
      noSubject: "(fără subiect)",
      note:
        "10 e-mailuri maghiare realiste, imediat, fără autentificare. Pe ele rulează același agent " +
        "ca pe o căsuță reală — scrie și răspunsurile.",
      alt: "Prefer să-l încerc pe contul meu Gmail →",
    },
    connect: {
      notConfigured: "Accesul Google al agentului nu este încă configurat.",
      googleTitle: "Ce îți va arăta Google.",
      googleBody:
        "Înainte să te lase, apare un ecran roșu: „Google nu a verificat această aplicație\". " +
        "Apare la orice aplicație care cere acces la căsuță și nu a trecut încă de evaluarea de " +
        "securitate a Google — nu spune nimic despre starea contului tău.",
      googleHow:
        "Se continuă prin Avansat → Accesați… Dacă acum îți este incomod, căsuța de exemplu arată " +
        "tot fără autentificare.",
      back: "← Înapoi la căsuța de exemplu",
      optinTitle: "Poate scrie ciorne în căsuța mea.",
      optinBody:
        "Dacă bifezi, agentul pune răspunsul scris — după confirmarea ta separată, mesaj cu mesaj " +
        "— în Ciornele Gmail, pe firul lui. Trimiterea rămâne tot la tine.",
      optinWarn:
        "Important: Google nu are o permisiune „doar ciornă\", așa că ecranul de consimțământ va " +
        "menționa și dreptul de trimitere. Acest cod nu trimite niciodată un e-mail — trimiterea " +
        "este blocată la nivel de cod —, dar permisiunea pe care o acorzi este mai largă. Dacă " +
        "asta nu îți convine, las-o nebifată: formularea funcționează și fără, doar trebuie să " +
        "copiezi textul.",
      ctaRead: "Conectează contul Google",
      ctaWrite: "Conectează — citire și scriere de ciorne",
      redirecting: "Redirecționare…",
    },
    run: {
      sampleNoteTitle: "Căsuță de exemplu.",
      sampleNote:
        "Mesajele sunt inventate — dar clasificarea și răspunsurile au fost produse chiar acum, de " +
        "același agent care ar rula pe un cont real.",
      starting: "Pornire…",
      processed: "Mesaje procesate",
      needsReply: "Necesită răspuns",
      showThese: "Arată-le pe acestea",
      showAllShort: "Arată toate mesajele",
      mostUrgent: "Cele mai urgente",
      categories: "Distribuția pe categorii",
      filterNote: "Se văd doar mesajele care așteaptă răspuns.",
      showAllN: "Arată toate cele {n} mesaje",
      whyUrgent: "De ce această urgență",
      nextStep: "Pasul următor sugerat",
      theEmail: "Mesajul",
      empty: "(gol)",
      noEmails: "Nu am găsit mesaje din ultimele 30 de zile.",
      logout: "Ieșire și deconectare",
      foot: "La ieșire contul tău se deconectează imediat, iar analiza se șterge de pe server.",
    },
    unreachable: {
      title: "Agentul nu este disponibil acum.",
      body: "Nu am putut ajunge la server — de obicei sunt câteva secunde, cât pornește o versiune nouă.",
      retry: "Încearcă din nou",
    },
  },

  sk: {
    seo: {
      title: "Agent na triedenie e-mailov — živé demo | AXIMBRA",
      description:
        "Živé demo: agent prejde posledných 30 dní vašej schránky, zoradí správy podľa naliehavosti " +
        "a napíše odpovede. Predvolene iba číta — odoslať nedokáže.",
    },
    title: "Agent na triedenie e-mailov",
    notConnected: "Nepripojené",
    err: {
      access_denied: "Odmietli ste prístup Google, alebo sa proces prerušil.",
      invalid_state: "Proces vypršal. Spustite pripojenie znova.",
      token_exchange: "Výmena s Googlom zlyhala. Skúste to znova.",
      no_email: "Google nevrátil e-mailovú adresu účtu.",
      busy: "Práve to skúša priveľa ľudí naraz. Vráťte sa o pár minút.",
      generic: "Chyba",
      unknown: "Neznáma chyba.",
    },
    urgency: { u5: "Okamžité", u4: "Naliehavé", u3: "Stredné", u1: "Počká" },
    cat: {
      customer_question: "Zákazník – otázka",
      customer_complaint: "Zákazník – sťažnosť",
      opportunity: "Obchodná príležitosť",
      invoice: "Faktúra / financie",
      authority: "Úrad / úradné",
      provider_notice: "Oznámenie poskytovateľa",
      newsletter: "Newsletter / marketing",
      spam: "Spam / nevyžiadané",
      other: "Iné",
    },
    tone: { group: "Tón", hivatalos: "Formálny", kozvetlen: "Priamy" },
    draft: {
      write: "Napísať odpoveď",
      rewrite: "Preformulovať",
      writing: "Píše sa…",
      subject: "Predmet",
      copy: "Kopírovať",
      copied: "Skopírované",
      clipboardError: "Schránka nie je dostupná — označte text a skopírujte ho ručne.",
      save: "Uložiť medzi koncepty Gmailu",
      send: "Odoslať e-mail",
      noteWrite: "Pred odoslaním sa ešte raz opýtame — odoslať ho môžete iba vy.",
      noteRead: "Koncept — agent ho neodošle a ani ho nezapíše do vášho účtu.",
      saveText: "Zapíšem koncept do vášho účtu Gmail ako odpoveď na {sender}, do jeho vlastného vlákna.",
      saveNotSend: "Neodošlem ho",
      saveNotSendRest: "— nájdete ho v Konceptoch a sami rozhodnete, či pôjde von.",
      saveYes: "Potvrdzujem, ulož ako koncept",
      saving: "Ukladá sa…",
      cancel: "Zrušiť",
      sendTitle: "Tento e-mail sa teraz naozaj odošle.",
      to: "Príjemca",
      from: "Odosielateľ",
      fromValue: "váš účet Gmail",
      sendWarn:
        "Toto sa nedá vrátiť späť. Prečítajte si text vyššie — časti v hranatých zátvorkách " +
        "([takto]) musíte pred odoslaním doplniť vy.",
      sendYes: "Áno, odoslať teraz",
      sending: "Odosiela sa…",
      sent: "Odoslané.",
      savedNew: "Koncept uložený.",
      savedUpdated: "Koncept aktualizovaný.",
      openGmail: "Otvoriť v Gmaile",
    },
    intro: {
      lead:
        "Pripojte svoj účet Gmail a agent prejde poštu za posledných 30 dní: rozdelí ju do " +
        "kategórií, posúdi naliehavosť a povie vám, na ktoré správy treba odpovedať. Pri tých, " +
        "ktoré vyberiete, napíše aj odpoveď.",
      guarantees: [
        { t: "Predvolene iba číta.", d: "Bez zaškrtnutia nižšie nezapíše do vášho účtu nič a nežiada ani právo na odosielanie." },
        { t: "Existujúcej pošty sa nikdy nedotkne.", d: "Žiadne štítky, žiadne hviezdičky, žiadne mazanie — ani s právom na zápis." },
        { t: "Písať a odosielať len s vaším súhlasom.", d: "Aj so zaškrtnutím sa pri každej správe pýtame zvlášť, kým napíše koncept alebo niečo odošle." },
        { t: "Nič neukladáme.", d: "Beh sám vyprší po 30 minútach. Pri zatvorení stránky to prehliadač ohlási a beh sa hneď zmaže — ak sa hlásenie nedoručí, platí 30-minútový limit." },
      ],
    },
    disclosure: {
      summary: "Čo presne žiadame a čo sa stane s vašimi údajmi?",
      scopesTitle: "Požadované povolenia Google",
      scopeRead: "čítanie vašej pošty. Je vždy potrebné a predvolene je to jediné povolenie, ktoré žiadame.",
      scopeIdentity: "aby sme vedeli, na ktorý účet sa pozeráme.",
      scopeComposeLead: "iba ak zaškrtnete písanie konceptov.",
      scopeCompose:
        "Vďaka nemu môže vo vašom účte nechať koncept. Google nemá povolenie „iba koncept\", takže " +
        "by umožnilo aj odosielanie — tento kód však nikdy neodosiela, odoslanie je zablokované na " +
        "úrovni kódu. Bez zaškrtnutia toto povolenie ani nežiadame.",
      readTitle: "Čo čítame",
      read30: "Najviac 50 správ za posledných 30 dní. Nič staršie, nič navyše.",
      readFields: "Odosielateľ, predmet, dátum a text správy.",
      readAttachLead: "Prílohu len vtedy, keď samotný text správy nestačí",
      readAttach:
        "— pri e-maile typu „posielam podklady, detaily v prílohe\" je podstata v dokumente. Vtedy " +
        "z najviac dvoch súborov na správu vytiahneme text (Word, Excel, PowerPoint, PDF, čistý " +
        "text; z obrázkov a videí nie). Súbor neukladáme, ďalej ide len vytiahnutý text.",
      writeTitle: "Čo píšeme",
      writeNoneLead: "Bez zaškrtnutia:",
      writeNone: "nič. Koncept zostane na stránke a skopírujete si ho vy.",
      writeDraft:
        "S písaním konceptov: jedinú vec, pri každej správe, po vašom samostatnom potvrdení — " +
        "koncept odpovede medzi koncepty Gmailu. Existujúcu poštu neupravujeme: žiadne štítky, " +
        "hviezdičky ani mazanie, a nič neodosielame.",
      whereTitle: "Kam to ide",
      whereLlm:
        "Text správy pošleme v jedinom klasifikačnom volaní do API OpenAI. Údaje odoslané cez API " +
        "poskytovateľ predvolene nepoužíva na trénovanie modelov.",
      whereNoDb: "Do databázy sa nedostane nič. Beh žije v pamäti servera.",
      lifeTitle: "Ako dlho to žije a ako to zmažete",
      life30: "Relácia sama vyprší po 30 minútach.",
      lifeExit: "„Odhlásenie\" okamžite zmaže beh aj prístup. Zatvorenie stránky urobí to isté, ak sa hlásenie prehliadača doručí; inak to ukončí 30-minútový limit.",
      lifeRevoke: "Povolenie môžete v Google kedykoľvek odvolať:",
      whoTitle: "Kto žiada",
      whoText: "— s otázkou alebo žiadosťou o vymazanie nám napíšte a odpovieme.",
    },
    closed: {
      title: "Agent zatiaľ nie je verejný.",
      body:
        "Skôr než niekoho požiadame o prístup ku Gmailu, zverejníme informácie o spracúvaní údajov " +
        "a firemné údaje — dovtedy o prístup do schránky nežiadame nikoho.",
      live: "Radi vám ho ukážeme naživo na vlastnom účte:",
      liveSubject: "Rád by som videl e-mailového agenta naživo",
    },
    start: {
      cta: "Pozrite si to na ukážkovej schránke",
      starting: "Spúšťa sa…",
      running: "Prebieha spracovanie…",
      fetching: "Načítavajú sa e-maily…",
      done: "Hotovo",
      empty: "Za posledných 30 dní nie sú žiadne spracovateľné e-maily.",
      interrupted: "Analýza sa prerušila. Skúste to znova.",
      budget: "Agent dosiahol svoj denný rozpočet.",
      noSubject: "(bez predmetu)",
      note:
        "10 realistických maďarských e-mailov, hneď, bez prihlásenia. Beží na nich ten istý agent " +
        "ako na ostrej schránke — napíše aj odpovede.",
      alt: "Radšej si to pozriem na vlastnom účte Gmail →",
    },
    connect: {
      notConfigured: "Prístup agenta ku Google zatiaľ nie je nastavený.",
      googleTitle: "Čo vám Google ukáže.",
      googleBody:
        "Skôr než vás pustí ďalej, objaví sa červená obrazovka „Google túto aplikáciu neoveril\". " +
        "Objaví sa pri každej aplikácii, ktorá žiada prístup do schránky a zatiaľ neprešla " +
        "bezpečnostným posúdením Googlu — o stave vášho účtu nehovorí nič.",
      googleHow:
        "Ďalej sa pokračuje cez Rozšírené → Prejsť na… Ak je to teraz nepríjemné, ukážková " +
        "schránka ukáže všetko bez prihlásenia.",
      back: "← Späť na ukážkovú schránku",
      optinTitle: "Môže písať koncepty do mojej schránky.",
      optinBody:
        "Ak to zaškrtnete, agent vloží napísanú odpoveď — po vašom samostatnom potvrdení, správu " +
        "po správe — medzi koncepty Gmailu, do jej vlastného vlákna. Odoslať ju aj tak môžete len vy.",
      optinWarn:
        "Dôležité: Google nemá povolenie „iba koncept\", preto obrazovka so súhlasom spomenie aj " +
        "právo na odosielanie. Tento kód nikdy neodošle e-mail — odoslanie je zablokované na " +
        "úrovni kódu —, ale povolenie, ktoré udelíte, je širšie. Ak vám to nevyhovuje, nechajte to " +
        "prázdne: formulovanie funguje aj bez toho, text si len skopírujete.",
      ctaRead: "Pripojiť účet Google",
      ctaWrite: "Pripojiť — čítanie a písanie konceptov",
      redirecting: "Presmerovanie…",
    },
    run: {
      sampleNoteTitle: "Ukážková schránka.",
      sampleNote:
        "E-maily sú vymyslené — klasifikácia a odpovede však vznikli práve teraz, tým istým " +
        "agentom, ktorý by bežal na ostrom účte.",
      starting: "Štartuje sa…",
      processed: "Spracované správy",
      needsReply: "Vyžaduje odpoveď",
      showThese: "Zobraziť tieto",
      showAllShort: "Zobraziť všetky správy",
      mostUrgent: "Najnaliehavejšie",
      categories: "Rozdelenie podľa kategórií",
      filterNote: "Zobrazujú sa len správy čakajúce na odpoveď.",
      showAllN: "Zobraziť všetkých {n} správ",
      whyUrgent: "Prečo táto naliehavosť",
      nextStep: "Navrhovaný ďalší krok",
      theEmail: "Správa",
      empty: "(prázdne)",
      noEmails: "Za posledných 30 dní sme nenašli žiadne správy.",
      logout: "Odhlásiť sa a odpojiť",
      foot: "Odhlásením sa váš účet okamžite odpojí a analýza sa zo servera zmaže.",
    },
    unreachable: {
      title: "Agent je momentálne nedostupný.",
      body: "Nepodarilo sa nám dosiahnuť server — zvyčajne ide o pár sekúnd, kým nabehne nová verzia.",
      retry: "Skúsiť znova",
    },
  },
};

export default agent;

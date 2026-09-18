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
      search_too_short: "Írj be legalább két karaktert.",
      search_limit: "Ebben a munkamenetben elérted a keresések számát.",
      search_failed: "A keresés most nem sikerült. Próbáld újra.",
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
    search: {
      label: "Keresés a postafiókban",
      placeholder: "Kulcsszó — pl. neptun, számla, szerződés",
      button: "Keresés",
      searching: "Keresés…",
      back: "← Vissza a futás eredményéhez",
      results: "{n} találat erre: „{q}”",
      results1: "1 találat erre: „{q}”",
      none: "Nincs találat erre: „{q}”",
      note: "A keresés a teljes postafiókban fut, nem csak az elemzett 30 napban. A találatokat nem osztályozzuk — ahhoz levelenként külön modellhívás kellene.",
      openInGmail: "Megnyitom a Gmailben →",
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
        { t: "A meglévő leveleidhez csak a te kattintásodra nyúl.", d: "Külön pipa után a hírleveleket és a kéretlen leveleket a Kukába teheted egy gombbal — mást soha, és mindig te kattintasz. A Gmail a Kukából 30 napig visszaállítja őket; véglegesen semmit nem törlünk." },
        { t: "Írni és küldeni csak a te engedélyeddel.", d: "Ha bepipálod, akkor is levelenként külön rákérdezünk, mielőtt vázlatot írna vagy elküldene bármit." },
        { t: "Semmit nem tárolunk.", d: "A futás 30 perc után magától lejár. A lap bezárásakor a böngésző jelez, és azonnal törlődik — ha a jelzés nem ér célba, marad a 30 perces határidő." },
      ],
    },
    product: {
      title: "Ez egy demó — és ami megvásárolható",
      demoLead: "Ezen a lapon semmi nem marad meg.",
      demoText: "A futás 30 perc után magától lejár, a lap bezárásakor törlődik, és minden csatlakozás nulláról indul. Ez a bemutató szándékos korlátja, nem a rendszeré.",
      yoursLead: "Amit megrendelsz, az a saját rendszered:",
      yoursText: "egy alkalmazás vagy weboldal, amihez csak te férsz hozzá — a te fiókoddal, a te kiszolgálódon.",
      points: [
        "Nincs automatikus lecsatlakozás. A kapcsolat addig él, amíg te meg nem szünteted.",
        "Az agent kétóránként magától átnézi az újonnan érkezett leveleket, és jelez, ha van, amire válaszolni kell.",
        "Az első csatlakozáskor visszanéz az elmúlt öt hónapra, és kiemeli, ami még élő ügy lehet — ugyanazzal a rangsorolással, amit itt látsz.",
        "A keresés is ott van: bármilyen kulcsszóra előhozza a kapcsolódó leveleket a teljes postafiókból.",
      ],
      cta: "Kérdezz rá, mit jelentene a te postafiókodon",
    },
    disclosure: {
      summary: "Mit kérünk pontosan, és mi történik az adataiddal?",
      scopesTitle: "A kért Google-jogosultságok",
      scopeRead: "a leveleid olvasása. Ez mindig kell, és alapesetben ez az egyetlen jog, amit kérünk.",
      scopeIdentity: "hogy tudjuk, melyik fiókot nézzük.",
      scopeComposeLead: "csak ha bepipálod a vázlatírást.",
      scopeCompose: "Ettől tud vázlatot tenni a fiókodba, és ettől tudja elküldeni a választ, ha az adott levélnél külön megerősíted. A Google-nak nincs „csak vázlat” jogosultsága. Magától soha nem küld: küldés csak a te külön megerősítésedre történik. Pipa nélkül ezt a jogot nem is kérjük.",
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
      writeDraft: "Vázlatírással, levelenként és mindig a te külön megerősítésed után: egy válaszvázlatot a Gmail Vázlatok közé, és ha azt is megerősíted, ennek a vázlatnak az elküldését. Meglévő levelet nem módosítunk: nem címkézünk, nem csillagozunk, nem törlünk.",
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
      optinWarn: "Fontos: a Google-nak nincs „csak vázlat” jogosultsága, ezért a beleegyező képernyő küldési jogot is említeni fog. Az agent magától soha nem küld levelet — csak azt a vázlatot, amelynek a küldését te külön megerősíted —, de a jogosultság, amit megadsz, ennél szélesebb. Ha ez nem kényelmes, hagyd üresen: a fogalmazás pipa nélkül is működik, csak kimásolni kell.",
      cleanupTitle: "Kitakaríthatja a nem lényeges leveleket.",
      cleanupBody:
        "Ha bepipálod, a hírleveleket és a kéretlen leveleket egy gombbal a Kukába teheted — " +
        "egyesével vagy egyszerre. Csak ezt a két kategóriát érinti, és mindig te kattintasz.",
      cleanupWarn: "A Kukából a Gmail 30 napig visszaállíthatóan őrzi őket. Véglegesen semmit nem törlünk. Ehhez a Google szélesebb jogot kér, mert a levelek áthelyezéséhez az olvasás nem elég.",
      ctaClean: "Csatlakozás — olvasás és takarítás",
      ctaRead: "Csatlakozás a Google-fiókhoz",
      ctaWrite: "Csatlakozás — olvasás és vázlatírás",
      redirecting: "Átirányítás…",
      privacyLead: "Az AXIMBRA a Google API-kból kapott adatokat a Google API Services User Data Policy szerint használja és adja tovább, a korlátozott felhasználás (Limited Use) követelményeivel együtt.",
      privacyLink: "Adatkezelési tájékoztató",
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
      junkFilterNote: "Csak a nem lényegesnek jelölt levelek látszanak.",
      showAllN: "Mutasd mind a {n} levelet",
      whyUrgent: "Miért ez a sürgősség",
      nextStep: "Javasolt következő lépés",
      theEmail: "A levél",
      empty: "(üres)",
      noEmails: "Nem találtunk levelet az elmúlt 30 napból.",
      junkTitle: "Nem lényeges levelek",
      junkTag: "nem lényeges",
      junkNote: "Hírlevelek és kéretlen levelek. A Kukába kerülnek, ahonnan a Gmailben 30 napig visszaállíthatod.",
      junkAll: "Összes törlése ({n})",
      junkConfirm: "Biztos? {n} levél a Kukába.",
      junkYes: "Igen, mehet",
      junkNo: "Mégsem",
      junkOne: "Kukába",
      junkBusy: "Törlés…",
      junkDone: "{n} levél a Kukába került. A Gmailben 30 napig visszaállítható.",
      junkNoGrant: "A takarításhoz csatlakozz újra, és pipáld be a takarítást.",
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
      search_too_short: "Type at least two characters.",
      search_limit: "You have reached the number of searches for this session.",
      search_failed: "The search failed. Please try again.",
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
    search: {
      label: "Search the mailbox",
      placeholder: "Keyword — e.g. invoice, contract, booking",
      button: "Search",
      searching: "Searching…",
      back: "← Back to the run",
      results: "{n} results for “{q}”",
      results1: "1 result for “{q}”",
      none: "No results for “{q}”",
      note: "Search covers the whole mailbox, not just the 30 days analysed. Hits are not classified — that would be one model call per email.",
      openInGmail: "Open in Gmail →",
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
        { t: "It touches your existing mail only when you click.", d: "With a separate tick you can move newsletters and junk to Trash with one button — nothing else, ever, and you always click. Gmail keeps anything in Trash recoverable for about 30 days; nothing is deleted for good." },
        { t: "Writing and sending only with your permission.", d: "Even with the box ticked, we ask separately for each email before it writes a draft or sends anything." },
        { t: "We store nothing.", d: "The run expires by itself after 30 minutes. Closing the page signals the server and deletes it at once — and if that signal does not arrive, the 30-minute limit still ends it." },
      ],
    },
    product: {
      title: "This is a demo — and what you can buy",
      demoLead: "Nothing on this page is kept.",
      demoText: "The run expires by itself after 30 minutes, closing the page deletes it, and every connection starts from zero. That is a deliberate limit of the demo, not of the system.",
      yoursLead: "What you order is your own system:",
      yoursText: "an app or a website only you have access to — your account, your server.",
      points: [
        "No automatic disconnect. The connection lives until you end it yourself.",
        "Every two hours the agent goes through the newly arrived mail on its own and tells you if something needs an answer.",
        "On the first connection it looks back over the last five months and highlights what may still be open — with the same ranking you see here.",
        "Search is there too: any keyword brings up the related emails from the whole mailbox.",
      ],
      cta: "Ask what this would look like on your mailbox",
    },
    disclosure: {
      summary: "What exactly do we ask for, and what happens to your data?",
      scopesTitle: "The Google permissions requested",
      scopeRead: "reading your mail. This is always needed, and by default it is the only permission we ask for.",
      scopeIdentity: "so we know which account we're looking at.",
      scopeComposeLead: "only if you tick draft writing.",
      scopeCompose: "This is what lets it place a draft in your account, and send that reply if you confirm it for that email. Google has no draft-only permission. It never sends on its own: sending only happens after your separate confirmation. Without the tick we do not request this permission at all.",
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
      writeDraft: "With draft writing, per email and always after your separate confirmation: a reply draft in Gmail Drafts, and — if you confirm that too — sending that draft. We do not modify existing mail: no labelling, no starring, no deleting.",
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
      optinWarn: "Important: Google has no draft-only permission, so the consent screen will mention send access as well. The agent never sends an email on its own — only a draft you separately confirm for sending — but the permission you grant is broader than that. If that is uncomfortable, leave it unticked: drafting works without it, you just copy the text out.",
      cleanupTitle: "It may tidy up the mail that does not matter.",
      cleanupBody:
        "If you tick this, newsletters and junk can be moved to Trash with one button — " +
        "one at a time or all at once. It touches only those two categories, and you always click.",
      cleanupWarn: "Gmail keeps anything in Trash recoverable for about 30 days. Nothing is ever deleted for good. Google asks for a wider permission for this, because reading is not enough to move a message.",
      ctaClean: "Connect — read and tidy up",
      ctaRead: "Connect the Google account",
      ctaWrite: "Connect — read and write drafts",
      redirecting: "Redirecting…",
      privacyLead: "AXIMBRA's use and transfer of information received from Google APIs adheres to the Google API Services User Data Policy, including the Limited Use requirements.",
      privacyLink: "Privacy notice",
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
      junkFilterNote: "Only the messages marked as unimportant are shown.",
      showAllN: "Show all {n} messages",
      whyUrgent: "Why this urgency",
      nextStep: "Suggested next step",
      theEmail: "The message",
      empty: "(empty)",
      noEmails: "We found no messages from the last 30 days.",
      junkTitle: "Unimportant mail",
      junkTag: "unimportant",
      junkNote: "Newsletters and junk. They go to Trash, where Gmail keeps them recoverable for about 30 days.",
      junkAll: "Delete all ({n})",
      junkConfirm: "Are you sure? {n} messages to Trash.",
      junkYes: "Yes, go ahead",
      junkNo: "Cancel",
      junkOne: "Trash",
      junkBusy: "Deleting…",
      junkDone: "{n} messages moved to Trash. Recoverable in Gmail for about 30 days.",
      junkNoGrant: "To tidy up, connect again and tick the cleanup box.",
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
      search_too_short: "Gib mindestens zwei Zeichen ein.",
      search_limit: "Die Zahl der Suchen für diese Sitzung ist erreicht.",
      search_failed: "Die Suche ist fehlgeschlagen. Bitte erneut versuchen.",
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
    search: {
      label: "Postfach durchsuchen",
      placeholder: "Stichwort — z. B. Rechnung, Vertrag, Buchung",
      button: "Suchen",
      searching: "Suche läuft…",
      back: "← Zurück zum Lauf",
      results: "{n} Treffer für „{q}“",
      results1: "1 Treffer für „{q}“",
      none: "Keine Treffer für „{q}“",
      note: "Die Suche geht über das ganze Postfach, nicht nur über die analysierten 30 Tage. Treffer werden nicht klassifiziert — das wäre ein Modellaufruf pro Mail.",
      openInGmail: "In Gmail öffnen →",
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
        { t: "Vorhandene Mails rührt er nur auf Ihren Klick an.", d: "Mit einem eigenen Häkchen verschieben Sie Newsletter und Werbung per Knopf in den Papierkorb — sonst nichts, und geklickt wird immer von Ihnen. Aus dem Papierkorb stellt Gmail sie rund 30 Tage lang wieder her; endgültig gelöscht wird nichts." },
        { t: "Schreiben und Senden nur mit Ihrer Erlaubnis.", d: "Auch mit Häkchen fragen wir pro E-Mail einzeln nach, bevor ein Entwurf entsteht oder etwas rausgeht." },
        { t: "Wir speichern nichts.", d: "Der Lauf verfällt nach 30 Minuten von selbst. Beim Schließen der Seite meldet der Browser das und er wird sofort gelöscht — kommt die Meldung nicht an, bleibt die 30-Minuten-Frist." },
      ],
    },
    product: {
      title: "Das ist eine Demo — und das ist käuflich",
      demoLead: "Auf dieser Seite bleibt nichts erhalten.",
      demoText: "Der Lauf verfällt nach 30 Minuten von selbst, beim Schließen der Seite wird er gelöscht, und jede Verbindung beginnt bei null. Das ist eine bewusste Grenze der Demo, nicht des Systems.",
      yoursLead: "Was Sie bestellen, ist Ihr eigenes System:",
      yoursText: "eine App oder eine Website, auf die nur Sie Zugriff haben — Ihr Konto, Ihr Server.",
      points: [
        "Keine automatische Trennung. Die Verbindung bleibt, bis Sie sie selbst beenden.",
        "Alle zwei Stunden geht der Agent die neu eingegangene Post von selbst durch und meldet, wenn etwas eine Antwort braucht.",
        "Bei der ersten Verbindung schaut er fünf Monate zurück und hebt hervor, was noch offen sein könnte — mit derselben Priorisierung wie hier.",
        "Die Suche ist ebenfalls dabei: jedes Stichwort holt die zugehörigen Mails aus dem gesamten Postfach.",
      ],
      cta: "Fragen Sie, was das in Ihrem Postfach bedeuten würde",
    },
    disclosure: {
      summary: "Was genau fragen wir an, und was passiert mit Ihren Daten?",
      scopesTitle: "Die angefragten Google-Berechtigungen",
      scopeRead: "das Lesen Ihrer Mails. Das wird immer gebraucht und ist standardmäßig die einzige Berechtigung, die wir anfragen.",
      scopeIdentity: "damit wir wissen, welches Konto wir ansehen.",
      scopeComposeLead: "nur wenn Sie das Entwurfsschreiben ankreuzen.",
      scopeCompose: "Damit kann er einen Entwurf in Ihrem Konto ablegen und diese Antwort senden, wenn Sie das für die jeweilige E-Mail gesondert bestätigen. Google hat keine Nur-Entwurf-Berechtigung. Von sich aus sendet er nie: Gesendet wird nur nach Ihrer gesonderten Bestätigung. Ohne Häkchen fragen wir diese Berechtigung gar nicht an.",
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
      writeDraft: "Mit Entwurfsschreiben, pro E-Mail und immer nach Ihrer gesonderten Bestätigung: einen Antwortentwurf in den Gmail-Entwürfen und — wenn Sie auch das bestätigen — das Senden dieses Entwurfs. Vorhandene Mails ändern wir nicht: kein Labeln, kein Markieren, kein Löschen.",
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
      optinWarn: "Wichtig: Google hat keine Nur-Entwurf-Berechtigung, daher wird der Zustimmungsbildschirm auch das Senderecht erwähnen. Der Agent sendet nie von sich aus eine E-Mail — nur einen Entwurf, dessen Versand Sie gesondert bestätigen —, aber die Berechtigung, die Sie erteilen, ist breiter. Wenn Ihnen das unangenehm ist, lassen Sie es leer: Das Formulieren funktioniert auch ohne Häkchen, Sie müssen den Text nur herauskopieren.",
      cleanupTitle: "Darf die unwichtige Post aufräumen.",
      cleanupBody:
        "Wenn Sie das ankreuzen, lassen sich Newsletter und Werbung mit einem Knopf in den Papierkorb " +
        "verschieben — einzeln oder alle auf einmal. Es betrifft nur diese zwei Kategorien, und geklickt wird immer von Ihnen.",
      cleanupWarn: "Im Papierkorb hält Gmail alles rund 30 Tage wiederherstellbar. Endgültig gelöscht wird nichts. Google verlangt dafür eine breitere Berechtigung, denn zum Verschieben reicht Lesen nicht aus.",
      ctaClean: "Verbinden — lesen und aufräumen",
      ctaRead: "Mit dem Google-Konto verbinden",
      ctaWrite: "Verbinden — lesen und Entwürfe schreiben",
      redirecting: "Weiterleitung…",
      privacyLead: "Die Nutzung und Weitergabe von Daten, die AXIMBRA über Google-APIs erhält, entspricht der Google API Services User Data Policy, einschließlich der Anforderungen zur eingeschränkten Nutzung (Limited Use).",
      privacyLink: "Datenschutzhinweis (Englisch)",
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
      junkFilterNote: "Es werden nur die als unwichtig markierten E-Mails angezeigt.",
      showAllN: "Alle {n} Mails anzeigen",
      whyUrgent: "Warum diese Dringlichkeit",
      nextStep: "Vorgeschlagener nächster Schritt",
      theEmail: "Die Nachricht",
      empty: "(leer)",
      noEmails: "Wir haben keine Mails aus den letzten 30 Tagen gefunden.",
      junkTitle: "Unwichtige Mails",
      junkTag: "unwichtig",
      junkNote: "Newsletter und unerwünschte Post. Sie wandern in den Papierkorb, wo Gmail sie rund 30 Tage wiederherstellbar hält.",
      junkAll: "Alle löschen ({n})",
      junkConfirm: "Sicher? {n} Mails in den Papierkorb.",
      junkYes: "Ja, los",
      junkNo: "Abbrechen",
      junkOne: "Papierkorb",
      junkBusy: "Wird gelöscht…",
      junkDone: "{n} Mails sind im Papierkorb. In Gmail rund 30 Tage wiederherstellbar.",
      junkNoGrant: "Zum Aufräumen verbinden Sie sich erneut und kreuzen das Aufräumen an.",
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
      search_too_short: "Escribe al menos dos caracteres.",
      search_limit: "Has alcanzado el número de búsquedas de esta sesión.",
      search_failed: "La búsqueda ha fallado. Inténtalo de nuevo.",
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
    search: {
      label: "Buscar en el buzón",
      placeholder: "Palabra clave — p. ej. factura, contrato, reserva",
      button: "Buscar",
      searching: "Buscando…",
      back: "← Volver a la ejecución",
      results: "{n} resultados de «{q}»",
      results1: "1 resultado de «{q}»",
      none: "Sin resultados de «{q}»",
      note: "La búsqueda recorre todo el buzón, no solo los 30 días analizados. Los resultados no se clasifican — eso sería una llamada al modelo por correo.",
      openInGmail: "Abrir en Gmail →",
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
        { t: "Solo toca tus correos existentes cuando haces clic.", d: "Con una casilla aparte puedes mover boletines y correo basura a la Papelera con un botón — nada más, y siempre haces clic tú. Gmail los conserva recuperables unos 30 días; no se borra nada de forma definitiva." },
        { t: "Escribir y enviar solo con tu permiso.", d: "Incluso con la casilla marcada preguntamos por separado en cada correo antes de escribir un borrador o enviar nada." },
        { t: "No almacenamos nada.", d: "La ejecución caduca sola a los 30 minutos. Al cerrar la página el navegador avisa y se borra al instante — y si ese aviso no llega, queda el límite de 30 minutos." },
      ],
    },
    product: {
      title: "Esto es una demo — y esto es lo que puedes comprar",
      demoLead: "En esta página no se guarda nada.",
      demoText: "La ejecución caduca sola a los 30 minutos, al cerrar la página se borra y cada conexión empieza de cero. Es un límite deliberado de la demo, no del sistema.",
      yoursLead: "Lo que encargas es tu propio sistema:",
      yoursText: "una aplicación o un sitio web al que solo tú tienes acceso — tu cuenta, tu servidor.",
      points: [
        "Sin desconexión automática. La conexión dura hasta que tú la termines.",
        "Cada dos horas el agente repasa por su cuenta el correo nuevo y avisa si hay algo que responder.",
        "En la primera conexión mira cinco meses atrás y destaca lo que pueda seguir abierto — con la misma priorización que ves aquí.",
        "La búsqueda también está: cualquier palabra clave saca los correos relacionados de todo el buzón.",
      ],
      cta: "Pregunta qué supondría en tu buzón",
    },
    disclosure: {
      summary: "¿Qué pedimos exactamente y qué pasa con tus datos?",
      scopesTitle: "Los permisos de Google solicitados",
      scopeRead: "leer tu correo. Siempre hace falta y, por defecto, es el único permiso que pedimos.",
      scopeIdentity: "para saber qué cuenta estamos mirando.",
      scopeComposeLead: "solo si marcas la escritura de borradores.",
      scopeCompose: "Es lo que le permite dejar un borrador en tu cuenta y enviar esa respuesta si lo confirmas para ese correo. Google no tiene un permiso de «solo borrador». Nunca envía por su cuenta: solo envía tras tu confirmación aparte. Sin la marca ni siquiera pedimos este permiso.",
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
      writeDraft: "Con escritura de borradores, correo a correo y siempre tras tu confirmación aparte: un borrador de respuesta en Borradores de Gmail y, si también lo confirmas, el envío de ese borrador. No modificamos correos existentes: no etiquetamos, no destacamos, no borramos.",
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
      optinWarn: "Importante: Google no tiene un permiso de «solo borrador», así que la pantalla de consentimiento mencionará también el permiso de envío. El agente nunca envía un correo por su cuenta — solo un borrador cuyo envío confirmas aparte —, pero el permiso que concedes es más amplio. Si eso te incomoda, déjalo sin marcar: la redacción funciona igual, solo hay que copiar el texto.",
      cleanupTitle: "Puede limpiar el correo que no importa.",
      cleanupBody:
        "Si lo marcas, los boletines y el correo basura se pueden mover a la Papelera con un botón — " +
        "de uno en uno o todos a la vez. Solo afecta a esas dos categorías, y siempre haces clic tú.",
      cleanupWarn: "En la Papelera, Gmail los conserva recuperables unos 30 días. No se borra nada de forma definitiva. Google pide un permiso más amplio para esto, porque leer no basta para mover un mensaje.",
      ctaClean: "Conectar — leer y limpiar",
      ctaRead: "Conectar la cuenta de Google",
      ctaWrite: "Conectar — leer y escribir borradores",
      redirecting: "Redirigiendo…",
      privacyLead: "El uso y la transferencia por parte de AXIMBRA de la información recibida de las API de Google se ajustan a la Google API Services User Data Policy, incluidos los requisitos de uso limitado (Limited Use).",
      privacyLink: "Aviso de privacidad (en inglés)",
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
      junkFilterNote: "Solo se muestran los correos marcados como poco importantes.",
      showAllN: "Mostrar los {n} correos",
      whyUrgent: "Por qué esta urgencia",
      nextStep: "Siguiente paso sugerido",
      theEmail: "El mensaje",
      empty: "(vacío)",
      noEmails: "No hemos encontrado correos de los últimos 30 días.",
      junkTitle: "Correo sin importancia",
      junkTag: "sin importancia",
      junkNote: "Boletines y correo basura. Van a la Papelera, donde Gmail los conserva recuperables unos 30 días.",
      junkAll: "Eliminar todos ({n})",
      junkConfirm: "¿Seguro? {n} correos a la Papelera.",
      junkYes: "Sí, adelante",
      junkNo: "Cancelar",
      junkOne: "Papelera",
      junkBusy: "Eliminando…",
      junkDone: "{n} correos movidos a la Papelera. Recuperables en Gmail unos 30 días.",
      junkNoGrant: "Para limpiar, conéctate de nuevo y marca la casilla de limpieza.",
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
      search_too_short: "Saisissez au moins deux caractères.",
      search_limit: "Vous avez atteint le nombre de recherches pour cette session.",
      search_failed: "La recherche a échoué. Réessayez.",
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
    search: {
      label: "Rechercher dans la boîte",
      placeholder: "Mot-clé — ex. facture, contrat, réservation",
      button: "Rechercher",
      searching: "Recherche…",
      back: "← Retour aux résultats",
      results: "{n} résultats pour « {q} »",
      results1: "1 résultat pour « {q} »",
      none: "Aucun résultat pour « {q} »",
      note: "La recherche porte sur toute la boîte, pas seulement sur les 30 jours analysés. Les résultats ne sont pas classés — ce serait un appel au modèle par e-mail.",
      openInGmail: "Ouvrir dans Gmail →",
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
        { t: "Il ne touche à vos messages existants que si vous cliquez.", d: "Avec une case distincte, vous envoyez newsletters et courriers indésirables à la Corbeille en un bouton — rien d'autre, et c'est toujours vous qui cliquez. Gmail les garde récupérables une trentaine de jours ; rien n'est supprimé définitivement." },
        { t: "Écrire et envoyer seulement avec votre accord.", d: "Même la case cochée, nous redemandons message par message avant d'écrire un brouillon ou d'envoyer quoi que ce soit." },
        { t: "Nous ne stockons rien.", d: "L'exécution expire d'elle-même au bout de 30 minutes. À la fermeture de la page, le navigateur prévient et elle est supprimée aussitôt — si ce signal n'arrive pas, la limite de 30 minutes s'applique." },
      ],
    },
    product: {
      title: "Ceci est une démo — et voici ce qui s'achète",
      demoLead: "Rien n'est conservé sur cette page.",
      demoText: "L'exécution expire d'elle-même au bout de 30 minutes, la fermeture de la page la supprime, et chaque connexion repart de zéro. C'est une limite volontaire de la démo, pas du système.",
      yoursLead: "Ce que vous commandez, c'est votre propre système :",
      yoursText: "une application ou un site auquel vous seul avez accès — votre compte, votre serveur.",
      points: [
        "Aucune déconnexion automatique. La connexion dure jusqu'à ce que vous y mettiez fin.",
        "Toutes les deux heures, l'agent parcourt seul le courrier arrivé et signale ce qui attend une réponse.",
        "À la première connexion, il remonte cinq mois en arrière et met en avant ce qui peut encore être ouvert — avec le même classement qu'ici.",
        "La recherche est là aussi : n'importe quel mot-clé fait remonter les e-mails liés de toute la boîte.",
      ],
      cta: "Demandez ce que cela donnerait sur votre boîte",
    },
    disclosure: {
      summary: "Que demandons-nous exactement, et qu'advient-il de vos données ?",
      scopesTitle: "Les autorisations Google demandées",
      scopeRead: "la lecture de vos messages. Toujours nécessaire, et par défaut c'est la seule autorisation demandée.",
      scopeIdentity: "pour savoir quel compte nous consultons.",
      scopeComposeLead: "uniquement si vous cochez l'écriture de brouillons.",
      scopeCompose: "C'est ce qui lui permet de déposer un brouillon dans votre compte, et d'envoyer cette réponse si vous le confirmez pour ce message. Google n'a pas d'autorisation « brouillon seul ». Il n'envoie jamais de lui-même : l'envoi n'a lieu qu'après votre confirmation distincte. Sans la case, cette autorisation n'est même pas demandée.",
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
      writeDraft: "Avec l'écriture de brouillons, message par message et toujours après votre confirmation distincte : un brouillon de réponse dans les Brouillons Gmail et, si vous le confirmez aussi, l'envoi de ce brouillon. Nous ne modifions pas les messages existants : pas de libellé, pas d'étoile, pas de suppression.",
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
      optinWarn: "Important : Google n'a pas d'autorisation « brouillon seul », l'écran de consentement mentionnera donc aussi le droit d'envoi. L'agent n'envoie jamais d'e-mail de lui-même — seulement un brouillon dont vous confirmez l'envoi séparément —, mais l'autorisation que vous accordez est plus large. Si cela vous gêne, laissez la case vide : la rédaction fonctionne sans, il suffit de copier le texte.",
      cleanupTitle: "Peut faire le ménage dans les courriers sans importance.",
      cleanupBody:
        "Si vous cochez, les newsletters et les courriers indésirables peuvent partir à la Corbeille " +
        "en un bouton — un par un ou tous d'un coup. Cela ne touche que ces deux catégories, et c'est toujours vous qui cliquez.",
      cleanupWarn: "Dans la Corbeille, Gmail les garde récupérables une trentaine de jours. Rien n'est supprimé définitivement. Google demande une autorisation plus large pour cela, car lire ne suffit pas à déplacer un message.",
      ctaClean: "Connecter — lire et faire le ménage",
      ctaRead: "Connecter le compte Google",
      ctaWrite: "Connecter — lecture et écriture de brouillons",
      redirecting: "Redirection…",
      privacyLead: "L'utilisation et le transfert par AXIMBRA des informations reçues des API Google respectent la Google API Services User Data Policy, y compris les exigences d'utilisation limitée (Limited Use).",
      privacyLink: "Politique de confidentialité (en anglais)",
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
      junkFilterNote: "Seuls les messages marqués comme sans importance sont affichés.",
      showAllN: "Afficher les {n} messages",
      whyUrgent: "Pourquoi cette urgence",
      nextStep: "Prochaine étape suggérée",
      theEmail: "Le message",
      empty: "(vide)",
      noEmails: "Nous n'avons trouvé aucun message des 30 derniers jours.",
      junkTitle: "Courriers sans importance",
      junkTag: "sans importance",
      junkNote: "Newsletters et courriers indésirables. Ils partent à la Corbeille, où Gmail les garde récupérables une trentaine de jours.",
      junkAll: "Tout supprimer ({n})",
      junkConfirm: "Sûr ? {n} messages à la Corbeille.",
      junkYes: "Oui, allons-y",
      junkNo: "Annuler",
      junkOne: "Corbeille",
      junkBusy: "Suppression…",
      junkDone: "{n} messages déplacés à la Corbeille. Récupérables dans Gmail une trentaine de jours.",
      junkNoGrant: "Pour faire le ménage, reconnectez-vous et cochez la case du ménage.",
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
      search_too_short: "Scrivi almeno due caratteri.",
      search_limit: "Hai raggiunto il numero di ricerche per questa sessione.",
      search_failed: "La ricerca non è riuscita. Riprova.",
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
    search: {
      label: "Cerca nella casella",
      placeholder: "Parola chiave — es. fattura, contratto, prenotazione",
      button: "Cerca",
      searching: "Ricerca…",
      back: "← Torna ai risultati",
      results: "{n} risultati per «{q}»",
      results1: "1 risultato per «{q}»",
      none: "Nessun risultato per «{q}»",
      note: "La ricerca copre tutta la casella, non solo i 30 giorni analizzati. I risultati non vengono classificati — servirebbe una chiamata al modello per ogni e-mail.",
      openInGmail: "Apri in Gmail →",
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
        { t: "Tocca la posta esistente solo se clicchi tu.", d: "Con una spunta a parte puoi mandare newsletter e posta indesiderata nel Cestino con un pulsante — nient'altro, e a cliccare sei sempre tu. Gmail le tiene recuperabili per circa 30 giorni; non viene eliminato nulla in modo definitivo." },
        { t: "Scrive e invia solo con il tuo permesso.", d: "Anche con la casella spuntata chiediamo conferma per ogni singolo messaggio prima di scrivere una bozza o inviare qualcosa." },
        { t: "Non conserviamo nulla.", d: "L'esecuzione scade da sola dopo 30 minuti. Chiudendo la pagina il browser lo segnala e viene cancellata subito — se il segnale non arriva, resta il limite di 30 minuti." },
      ],
    },
    product: {
      title: "Questa è una demo — ed ecco cosa si può acquistare",
      demoLead: "In questa pagina non resta nulla.",
      demoText: "L'esecuzione scade da sola dopo 30 minuti, chiudendo la pagina viene cancellata e ogni collegamento riparte da zero. È un limite voluto della demo, non del sistema.",
      yoursLead: "Quello che ordini è un sistema tuo:",
      yoursText: "un'app o un sito a cui hai accesso solo tu — il tuo account, il tuo server.",
      points: [
        "Nessuna disconnessione automatica. Il collegamento dura finché non lo chiudi tu.",
        "Ogni due ore l'agente ripercorre da solo la posta appena arrivata e segnala se c'è qualcosa a cui rispondere.",
        "Al primo collegamento guarda indietro di cinque mesi e mette in evidenza ciò che potrebbe essere ancora aperto — con la stessa priorità che vedi qui.",
        "C'è anche la ricerca: qualsiasi parola chiave richiama le e-mail collegate da tutta la casella.",
      ],
      cta: "Chiedi cosa significherebbe sulla tua casella",
    },
    disclosure: {
      summary: "Che cosa chiediamo esattamente e che fine fanno i tuoi dati?",
      scopesTitle: "I permessi Google richiesti",
      scopeRead: "la lettura della tua posta. Serve sempre e, di base, è l'unico permesso che chiediamo.",
      scopeIdentity: "per sapere quale account stiamo guardando.",
      scopeComposeLead: "solo se spunti la scrittura delle bozze.",
      scopeCompose: "È ciò che gli permette di lasciare una bozza nel tuo account e di inviare quella risposta se lo confermi per quel messaggio. Google non ha un permesso di «sola bozza». Non invia mai di sua iniziativa: l'invio avviene solo dopo la tua conferma separata. Senza la spunta questo permesso non viene nemmeno chiesto.",
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
      writeDraft: "Con la scrittura delle bozze, messaggio per messaggio e sempre dopo la tua conferma separata: una bozza di risposta nelle Bozze di Gmail e, se confermi anche questo, l'invio di quella bozza. Non modifichiamo la posta esistente: niente etichette, niente stelle, niente cancellazioni.",
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
      optinWarn: "Importante: Google non ha un permesso di «sola bozza», quindi la schermata di consenso citerà anche il diritto di invio. L'agente non invia mai un'e-mail di sua iniziativa — solo una bozza di cui confermi l'invio separatamente —, ma il permesso che concedi è più ampio. Se questo ti mette a disagio, lascialo vuoto: la stesura funziona anche senza, basta copiare il testo.",
      cleanupTitle: "Può fare pulizia nella posta che non conta.",
      cleanupBody:
        "Se lo spunti, newsletter e posta indesiderata possono finire nel Cestino con un pulsante — " +
        "una alla volta o tutte insieme. Riguarda solo queste due categorie, e a cliccare sei sempre tu.",
      cleanupWarn: "Nel Cestino Gmail le tiene recuperabili per circa 30 giorni. Non viene eliminato nulla in modo definitivo. Google chiede un permesso più ampio per questo, perché leggere non basta a spostare un messaggio.",
      ctaClean: "Collega — leggi e fai pulizia",
      ctaRead: "Collega l'account Google",
      ctaWrite: "Collega — lettura e scrittura di bozze",
      redirecting: "Reindirizzamento…",
      privacyLead: "L'uso e il trasferimento da parte di AXIMBRA delle informazioni ricevute dalle API di Google rispettano la Google API Services User Data Policy, inclusi i requisiti di uso limitato (Limited Use).",
      privacyLink: "Informativa sulla privacy (in inglese)",
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
      junkFilterNote: "Sono visibili solo i messaggi contrassegnati come non importanti.",
      showAllN: "Mostra tutti i {n} messaggi",
      whyUrgent: "Perché questa urgenza",
      nextStep: "Prossimo passo suggerito",
      theEmail: "Il messaggio",
      empty: "(vuoto)",
      noEmails: "Non abbiamo trovato messaggi degli ultimi 30 giorni.",
      junkTitle: "Posta non importante",
      junkTag: "non importante",
      junkNote: "Newsletter e posta indesiderata. Finiscono nel Cestino, dove Gmail le tiene recuperabili per circa 30 giorni.",
      junkAll: "Elimina tutte ({n})",
      junkConfirm: "Sicuro? {n} messaggi nel Cestino.",
      junkYes: "Sì, procedi",
      junkNo: "Annulla",
      junkOne: "Cestino",
      junkBusy: "Eliminazione…",
      junkDone: "{n} messaggi spostati nel Cestino. Recuperabili in Gmail per circa 30 giorni.",
      junkNoGrant: "Per fare pulizia collegati di nuovo e spunta la casella della pulizia.",
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
      search_too_short: "Scrie cel puțin două caractere.",
      search_limit: "Ai atins numărul de căutări pentru această sesiune.",
      search_failed: "Căutarea a eșuat. Încearcă din nou.",
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
    search: {
      label: "Caută în căsuță",
      placeholder: "Cuvânt-cheie — ex. factură, contract, rezervare",
      button: "Caută",
      searching: "Se caută…",
      back: "← Înapoi la rezultate",
      results: "{n} rezultate pentru „{q}”",
      results1: "1 rezultat pentru „{q}”",
      none: "Niciun rezultat pentru „{q}”",
      note: "Căutarea acoperă toată căsuța, nu doar cele 30 de zile analizate. Rezultatele nu sunt clasificate — asta ar însemna un apel de model pentru fiecare e-mail.",
      openInGmail: "Deschide în Gmail →",
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
        { t: "Se atinge de mesajele existente doar la clicul tău.", d: "Cu o bifă separată poți trimite buletinele informative și mesajele nesolicitate în Coșul de gunoi cu un buton — nimic altceva, și tu ești cel care dă clic. Gmail le păstrează recuperabile circa 30 de zile; nimic nu se șterge definitiv." },
        { t: "Scrie și trimite doar cu permisiunea ta.", d: "Chiar și cu bifa pusă întrebăm separat la fiecare mesaj înainte să scrie o ciornă sau să trimită ceva." },
        { t: "Nu stocăm nimic.", d: "Rularea expiră singură după 30 de minute. La închiderea paginii browserul anunță serverul și se șterge imediat — dacă semnalul nu ajunge, rămâne limita de 30 de minute." },
      ],
    },
    product: {
      title: "Aceasta este o demonstrație — și iată ce se poate cumpăra",
      demoLead: "Pe această pagină nu rămâne nimic.",
      demoText: "Rularea expiră singură după 30 de minute, la închiderea paginii se șterge, iar fiecare conectare pornește de la zero. Este o limită intenționată a demonstrației, nu a sistemului.",
      yoursLead: "Ce comanzi este propriul tău sistem:",
      yoursText: "o aplicație sau un site la care ai acces doar tu — contul tău, serverul tău.",
      points: [
        "Fără deconectare automată. Conexiunea durează până o închizi tu.",
        "La fiecare două ore agentul parcurge singur mesajele nou sosite și anunță dacă e ceva de răspuns.",
        "La prima conectare se uită înapoi cinci luni și scoate în evidență ce ar putea fi încă deschis — cu aceeași ordonare pe care o vezi aici.",
        "Căutarea este și ea acolo: orice cuvânt-cheie aduce e-mailurile legate din toată căsuța.",
      ],
      cta: "Întreabă ce ar însemna asta în căsuța ta",
    },
    disclosure: {
      summary: "Ce cerem mai exact și ce se întâmplă cu datele tale?",
      scopesTitle: "Permisiunile Google cerute",
      scopeRead: "citirea mesajelor tale. Este mereu necesară și, implicit, este singura permisiune pe care o cerem.",
      scopeIdentity: "ca să știm ce cont ne uităm.",
      scopeComposeLead: "doar dacă bifezi scrierea de ciorne.",
      scopeCompose: "Asta îi permite să lase o ciornă în contul tău și să trimită acel răspuns dacă tu confirmi pentru mesajul respectiv. Google nu are o permisiune „doar ciornă”. Nu trimite niciodată din proprie inițiativă: trimiterea are loc doar după confirmarea ta separată. Fără bifă nici nu cerem această permisiune.",
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
      writeDraft: "Cu scrierea de ciorne, mesaj cu mesaj și mereu după confirmarea ta separată: o ciornă de răspuns în Ciornele Gmail și, dacă confirmi și asta, trimiterea acelei ciorne. Nu modificăm mesajele existente: fără etichete, fără stele, fără ștergeri.",
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
      optinWarn: "Important: Google nu are o permisiune „doar ciornă”, așa că ecranul de consimțământ va menționa și dreptul de trimitere. Agentul nu trimite niciodată un e-mail din proprie inițiativă — doar o ciornă a cărei trimitere o confirmi separat —, dar permisiunea pe care o acorzi este mai largă. Dacă asta nu îți convine, las-o nebifată: formularea funcționează și fără, doar trebuie să copiezi textul.",
      cleanupTitle: "Poate face curat în mesajele care nu contează.",
      cleanupBody:
        "Dacă bifezi, buletinele informative și mesajele nesolicitate pot ajunge în Coșul de gunoi " +
        "cu un buton — pe rând sau toate odată. Afectează doar aceste două categorii, și tu ești cel care dă clic.",
      cleanupWarn: "În Coșul de gunoi, Gmail le păstrează recuperabile circa 30 de zile. Nimic nu se șterge definitiv. Google cere o permisiune mai largă pentru asta, fiindcă cititul nu e de ajuns pentru a muta un mesaj.",
      ctaClean: "Conectează — citire și curățenie",
      ctaRead: "Conectează contul Google",
      ctaWrite: "Conectează — citire și scriere de ciorne",
      redirecting: "Redirecționare…",
      privacyLead: "Utilizarea și transferul de către AXIMBRA ale informațiilor primite prin API-urile Google respectă Google API Services User Data Policy, inclusiv cerințele de utilizare limitată (Limited Use).",
      privacyLink: "Notă de confidențialitate (în engleză)",
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
      junkFilterNote: "Se văd doar mesajele marcate ca neimportante.",
      showAllN: "Arată toate cele {n} mesaje",
      whyUrgent: "De ce această urgență",
      nextStep: "Pasul următor sugerat",
      theEmail: "Mesajul",
      empty: "(gol)",
      noEmails: "Nu am găsit mesaje din ultimele 30 de zile.",
      junkTitle: "Mesaje neimportante",
      junkTag: "neimportant",
      junkNote: "Buletine informative și mesaje nesolicitate. Ajung în Coșul de gunoi, unde Gmail le păstrează recuperabile circa 30 de zile.",
      junkAll: "Șterge tot ({n})",
      junkConfirm: "Sigur? {n} mesaje în Coșul de gunoi.",
      junkYes: "Da, hai",
      junkNo: "Renunță",
      junkOne: "Coș de gunoi",
      junkBusy: "Se șterge…",
      junkDone: "{n} mesaje au ajuns în Coșul de gunoi. Recuperabile în Gmail circa 30 de zile.",
      junkNoGrant: "Pentru curățenie conectează-te din nou și bifează curățenia.",
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
      search_too_short: "Zadaj aspoň dva znaky.",
      search_limit: "Dosiahli ste počet hľadaní pre túto reláciu.",
      search_failed: "Hľadanie zlyhalo. Skúste to znova.",
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
    search: {
      label: "Hľadať v schránke",
      placeholder: "Kľúčové slovo — napr. faktúra, zmluva, rezervácia",
      button: "Hľadať",
      searching: "Hľadá sa…",
      back: "← Späť na výsledky behu",
      results: "{n} výsledkov pre „{q}“",
      results1: "1 výsledok pre „{q}“",
      none: "Žiadne výsledky pre „{q}“",
      note: "Hľadanie prehľadá celú schránku, nielen analyzovaných 30 dní. Výsledky sa neklasifikujú — to by bolo jedno volanie modelu na každý e-mail.",
      openInGmail: "Otvoriť v Gmaile →",
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
        { t: "Existujúcej pošty sa dotkne len na váš klik.", d: "Po samostatnom zaškrtnutí presuniete newslettery a nevyžiadanú poštu do Koša jedným tlačidlom — nič iné, a klikáte vždy vy. Gmail ich z Koša obnoví ešte asi 30 dní; natrvalo sa nemaže nič." },
        { t: "Písať a odosielať len s vaším súhlasom.", d: "Aj so zaškrtnutím sa pri každej správe pýtame zvlášť, kým napíše koncept alebo niečo odošle." },
        { t: "Nič neukladáme.", d: "Beh sám vyprší po 30 minútach. Pri zatvorení stránky to prehliadač ohlási a beh sa hneď zmaže — ak sa hlásenie nedoručí, platí 30-minútový limit." },
      ],
    },
    product: {
      title: "Toto je demo — a toto sa dá kúpiť",
      demoLead: "Na tejto stránke nezostáva nič.",
      demoText: "Beh sám vyprší po 30 minútach, zatvorením stránky sa zmaže a každé pripojenie začína od nuly. Je to zámerné obmedzenie dema, nie systému.",
      yoursLead: "To, čo si objednáte, je váš vlastný systém:",
      yoursText: "aplikácia alebo web, ku ktorému máte prístup len vy — váš účet, váš server.",
      points: [
        "Žiadne automatické odpojenie. Spojenie trvá, kým ho sami neukončíte.",
        "Každé dve hodiny agent sám prejde novú poštu a ohlási, ak je niečo na odpoveď.",
        "Pri prvom pripojení sa pozrie päť mesiacov dozadu a vyzdvihne, čo môže byť ešte otvorené — s rovnakým poradím, aké vidíte tu.",
        "Hľadanie je tam tiež: akékoľvek kľúčové slovo vytiahne súvisiace e-maily z celej schránky.",
      ],
      cta: "Spýtajte sa, čo by to znamenalo vo vašej schránke",
    },
    disclosure: {
      summary: "Čo presne žiadame a čo sa stane s vašimi údajmi?",
      scopesTitle: "Požadované povolenia Google",
      scopeRead: "čítanie vašej pošty. Je vždy potrebné a predvolene je to jediné povolenie, ktoré žiadame.",
      scopeIdentity: "aby sme vedeli, na ktorý účet sa pozeráme.",
      scopeComposeLead: "iba ak zaškrtnete písanie konceptov.",
      scopeCompose: "Vďaka nemu môže vo vašom účte nechať koncept a odoslať túto odpoveď, ak to pri danej správe potvrdíte. Google nemá povolenie „iba koncept“. Sám od seba nikdy neodosiela: odoslanie prebehne len po vašom samostatnom potvrdení. Bez zaškrtnutia toto povolenie ani nežiadame.",
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
      writeDraft: "S písaním konceptov, pri každej správe a vždy po vašom samostatnom potvrdení: koncept odpovede medzi koncepty Gmailu a — ak potvrdíte aj to — odoslanie tohto konceptu. Existujúcu poštu neupravujeme: žiadne štítky, hviezdičky ani mazanie.",
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
      optinWarn: "Dôležité: Google nemá povolenie „iba koncept“, preto obrazovka so súhlasom spomenie aj právo na odosielanie. Agent nikdy sám od seba neodošle e-mail — iba koncept, ktorého odoslanie samostatne potvrdíte —, ale povolenie, ktoré udelíte, je širšie. Ak vám to nevyhovuje, nechajte to prázdne: formulovanie funguje aj bez toho, text si len skopírujete.",
      cleanupTitle: "Môže upratať nepodstatnú poštu.",
      cleanupBody:
        "Ak to zaškrtnete, newslettery a nevyžiadanú poštu presuniete do Koša jedným tlačidlom — " +
        "po jednom alebo naraz. Týka sa to len týchto dvoch kategórií a klikáte vždy vy.",
      cleanupWarn: "V Koši ich Gmail drží obnoviteľné asi 30 dní. Natrvalo sa nemaže nič. Google si na to pýta širšie oprávnenie, pretože na presun správy čítanie nestačí.",
      ctaClean: "Pripojiť — čítanie a upratovanie",
      ctaRead: "Pripojiť účet Google",
      ctaWrite: "Pripojiť — čítanie a písanie konceptov",
      redirecting: "Presmerovanie…",
      privacyLead: "Používanie a prenos informácií, ktoré AXIMBRA získa z Google API, sa riadia pravidlami Google API Services User Data Policy vrátane požiadaviek na obmedzené používanie (Limited Use).",
      privacyLink: "Zásady ochrany súkromia (v angličtine)",
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
      junkFilterNote: "Zobrazujú sa len správy označené ako nepodstatné.",
      showAllN: "Zobraziť všetkých {n} správ",
      whyUrgent: "Prečo táto naliehavosť",
      nextStep: "Navrhovaný ďalší krok",
      theEmail: "Správa",
      empty: "(prázdne)",
      noEmails: "Za posledných 30 dní sme nenašli žiadne správy.",
      junkTitle: "Nepodstatná pošta",
      junkTag: "nepodstatné",
      junkNote: "Newslettery a nevyžiadaná pošta. Idú do Koša, kde ich Gmail drží obnoviteľné asi 30 dní.",
      junkAll: "Vymazať všetko ({n})",
      junkConfirm: "Naozaj? {n} správ do Koša.",
      junkYes: "Áno, do toho",
      junkNo: "Zrušiť",
      junkOne: "Kôš",
      junkBusy: "Maže sa…",
      junkDone: "{n} správ je v Koši. V Gmaile obnoviteľné asi 30 dní.",
      junkNoGrant: "Na upratovanie sa pripojte znova a zaškrtnite upratovanie.",
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

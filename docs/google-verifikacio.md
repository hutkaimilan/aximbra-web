# Google-jóváhagyás a Gmail-bekötéshez — lépésről lépésre

Amíg a Google nem hagyja jóvá az alkalmazást, minden látogató a piros
„A Google nem ellenőrizte ezt az alkalmazást” képernyőt látja, és összesen
legfeljebb 100 felhasználó csatlakozhat. Ez kódból nem tüntethető el.

**Mennyi idő:** a te részed kb. 1–2 óra, több napra elosztva. A Google
átnézése hetekig tarthat.
**Mennyibe kerül:** a Google jóváhagyása ingyenes, de a Gmail-olvasáshoz évente
kötelező egy független biztonsági vizsgálat (CASA). Ezt egy elfogadott labor
végzi, és te fizeted: nagyságrendileg évi néhány száz, akár ezer-kétezer dollár.
A pontos szintet és árat a Google e-mailben közli a beadás után.

A lépések sorrendje számít. Mindegyik után elég nekem annyit írnod, hogy „kész”.

---

## Amit már megcsináltam

- **Angol adatkezelési tájékoztató:** https://aximbra.hu/en/adatkezeles
  (a magyar marad az irányadó, az angol lap ki is írja).
- **A Google-adatok korlátozott felhasználásáról szóló nyilatkozat** a
  tájékoztató 6. pontjában, és most már a bekötés gombja alatt is, mind a 8
  nyelven, linkkel a tájékoztatóra.
- **Egyértelmű mondat arról, hogy az OpenAI az API-n kapott adattal nem tanít
  modellt** — a Google ellenőrei ezt kérdezik a legtöbbször.

---

## 1. lépés — `api.aximbra.hu` ✅ KÉSZ

Miért kellett: a Gmail-belépés után a Google egy `…up.railway.app` címre küldte
vissza a látogatót. A Google csak olyan címet fogad el, amelyről igazolod, hogy
a tiéd — a `railway.app` pedig nem a tiéd.

Beállítva és ellenőrizve 2026-09-21-én:

```
CNAME   api.aximbra.hu  →  xlpd7dfh.up.railway.app
állapot: PROPAGATED · igazolva · tanúsítvány érvényes
```

Ezzel ez a lépés lezárult, nincs vele teendőd.

*(Megjegyzés: a Railway segédje korábban tévedésből létrehozott egy felesleges
`aximbra-api-production-cfea.up.railway.app` címet is. Nem árt semminek, a
Networking alatt a kuka ikonnal törölhető.)*

---

## 2. lépés — a domain igazolása a Google Search Console-ban ✅ KÉSZ

Az `aximbra.hu` Domain-tulajdon igazolva 2026-09-21-én, a
`hutkaimilan11@gmail.com` fiókkal. Nincs vele teendőd; az alábbi lépések
csak emlékeztetőül maradnak itt.

Ugyanazzal a Google-fiókkal csináld, amelyik a Google Cloud projekt tulajdonosa
(a piros képernyőn ez állt fejlesztőként: `hutkaimilan11@gmail.com`).

1. https://search.google.com/search-console → bal fent a tulajdonságválasztó →
   **Tulajdon hozzáadása**
2. A bal oldali **Domain** dobozba írd: `aximbra.hu` → **Folytatás**
3. A Google ad egy `google-site-verification=…` kezdetű szöveget → **másold ki**
4. Cloudflare → aximbra.hu → DNS → **Add record** → Type: **TXT** → Name: `@` →
   Content: a kimásolt szöveg → **Save**
5. Vissza a Search Console-ba → **Ellenőrzés**. Ha elsőre nem sikerül, várj 10 percet, és próbáld újra.

---

## 3. lépés — az új visszatérési cím beállítása ✅ KÉSZ

Mindkét fele megvan, 2026-09-21:

- **Google Cloud**, Authorized redirect URIs:
  `https://api.aximbra.hu/api/agent/email/callback` felvéve.
- **Railway**, `aximbra-api`: `AGENT_REDIRECT_URI` átállítva. A deploy naplója
  ezt írja indításkor, tehát élesben is ez megy:
  `email agent configured (redirect URI: https://api.aximbra.hu/api/agent/email/callback)`

A régi `…up.railway.app` visszatérési címet a Google-nél nyugodtan bent
hagyhatod, amíg a jóváhagyás le nem zárul — nem zavar semmit, viszont ha valami
visszaáll, nem esik ki a bekötés.

<details><summary>Az eredeti leírás (már nem teendő)</summary>

A sorrend számít: előbb a Google-nál vedd fel az új címet, és csak utána
állítsuk át a szerveren. Fordítva a bekötés azonnal `redirect_uri_mismatch`
hibára futna mindenkinél. A régit hagyd bent, amíg át nem álltunk — így nincs
egyetlen perc kiesés sem.

**Google Cloud:**
1. https://console.cloud.google.com/apis/credentials (felül a jó projekt legyen kiválasztva)
2. **OAuth 2.0 Client IDs** alatt kattints a klienst nevére
3. **Authorized redirect URIs** → **+ Add URI** →
   `https://api.aximbra.hu/api/agent/email/callback` → **Save**
   (A régit még ne töröld.)

**Railway:** `aximbra-api` → **Variables** → `AGENT_REDIRECT_URI` =
`https://api.aximbra.hu/api/agent/email/callback`

</details>

---

## 4. lépés — az alkalmazás adatai a Google-nél ✅ KÉSZ

A Branding lap hibátlanul elmentve, az Audience lapon **In production** /
**External**, a Data Access alatt mind az öt jogosultság bent van (a `gmail.modify`
is). Nincs vele teendőd; a táblázat alább emlékeztetőül marad.

https://console.cloud.google.com/auth/branding

| Mező | Érték |
|---|---|
| App name | `AXIMBRA` |
| User support email | `aximbra@gmail.com` (ha a listában nincs, a saját címed) |
| App logo | hagyd üresen — logóval lassabb az átnézés |
| Application home page | `https://aximbra.hu/en/demo/email-agent` |
| Application privacy policy link | `https://aximbra.hu/en/adatkezeles` |
| Application terms of service link | hagyd üresen |
| Authorized domains | `aximbra.hu` |
| Developer contact information | `aximbra@gmail.com` |

→ **Save**

https://console.cloud.google.com/auth/audience → a **Publishing status**
legyen **In production**, a **User type** **External**.

https://console.cloud.google.com/auth/scopes (Data Access) → **Add or remove scopes** → legyen bent pontosan ez az öt:
- `.../auth/gmail.readonly`
- `.../auth/gmail.compose`
- `.../auth/gmail.modify`
- `openid`
- `.../auth/userinfo.email`

**Ezt most kézzel be kell tenni.** A `gmail.modify` új: enélkül, aki a
csatlakozásnál bepipálja a takarítást, hibát kap a Google-tól, mert olyan
jogot kérünk, amit a beleegyező képernyőn nem hirdettünk meg. A pipa nélküli
(csak olvasás) és a vázlatíró út enélkül is működik.

A jogosultságok indoklását és a videó linkjét a Google a beadáskor kéri — a
szövegek lent vannak, csak be kell másolni őket.

---

## 5. lépés — a demóvideó (kb. 20 perc) ⬅️ **EZ A KÖVETKEZŐ TEENDŐD**

Ezt csak te tudod megcsinálni. A saját postafiókodat kell mutatni benne.

Beszélni nem kell, csak lassan végigkattintani. A felület legyen **angolul**.

**Felvétel:** Windowson **Win + Alt + R** indítja és állítja le a felvételt (Xbox Game Bar),
a videó a **Videók → Rögzítések** mappába kerül.
**Feltöltés:** YouTube → **Létrehozás → Videó feltöltése** → láthatóság: **Nem nyilvános (Unlisted)**.

### Rövid változat — 10 lépés (ez az ajánlott)

A Google ehhez ragaszkodik; a többi a hosszú változatban szépítés. Kb. 3 perc.

1. `aximbra.hu/en/demo/email-agent` → a nagy gomb alatti link
2. Pipáld be **mindkét** dobozt (write drafts, tidy up) → **Connect**
3. A felugró magyarázó ablak → **Értem, tovább a Google-höz**
4. Piros képernyő → **Advanced** → a lenti továbbvivő link
5. Jogosultság-képernyő: **kattints a címsorba** (látszódjon az URL a
   `client_id`-vel) → várj 5 mp → pipáld a jogokat → **Continue**
6. Várd meg a futást → görgess végig lassan a leveleken *(gmail.readonly)*
7. „Kérdés az árakról" levél → **draft a reply** → **save to Gmail Drafts**
   → Gmail fül → **Piszkozatok** → mutasd *(gmail.compose)*
8. Vissza → **küldés** megerősítése → Gmail → **Elküldött** → mutasd
9. Vissza → **Unimportant mail** blokk → **Delete all** → megerősítés →
   Gmail → **Kuka** → mutasd, hogy ott vannak *(gmail.modify)*
10. Vissza → **Log out and disconnect**, majd ha van még 20 másodperced,
    `myaccount.google.com/permissions` 5 másodpercig

A 9. lépés a legfontosabb. A `gmail.modify` a legkényesebb jog: ha a Kuka
mappa nem látszik, jó eséllyel visszakérdeznek, és megy még egy kör.

### Hosszú változat

A forgatókönyv lent van angolul (**Demo video script**). Minden képernyőnél
várj 3–4 másodpercet, hogy a Google ellenőre el tudja olvasni.

**Felvétel előtt, két perc előkészület — ez sokat spórol:**

1. Küldj magadnak egy levelet egy másik címedről, „Kérdés az árakról" tárggyal.
   A videóban EZT használd a vázlat- és küldés-bemutatóhoz: így a válasz a saját
   másik címedre megy, nem egy valódi ügyfélnek. A forgatókönyv 8–9. pontja
   különben tényleg kiküld egy levelet annak, aki írt neked.
2. A postafiókodban azt fogja látni a Google ellenőre, ami épp ott van. Ha van
   benne olyan, amit nem akarsz megmutatni, vagy használj egy másik fiókot,
   vagy archiváld előtte.
3. A felületet állítsd angolra: a `https://aximbra.hu/en` címmel kezdj.

---

## 6. lépés — beadás

https://console.cloud.google.com/auth/verification → **Prepare for verification**
→ a kérdéseknél másold be a lenti angol szövegeket és a YouTube-linket → **Submit**.

Utána a Google e-mailben jelentkezik (a `hutkaimilan11@gmail.com` címre). Ha kérdeznek,
küldd át nekem a levelet, és megírom a választ. A biztonsági vizsgálatról (CASA)
is ők írnak, a labor kiválasztásában segítek.

---

# Bemásolható angol szövegek

## Scope justification — `gmail.readonly`

AXIMBRA's email triage agent reads the user's recent emails to sort them on the
page. When the user connects their account, it reads at most 50 messages from the
last 30 days — sender, subject, date and body, plus the text of up to two
attachments per email when the body alone is not enough — and shows each one with
a category (for example customer complaint, invoice, authority notice, spam), an
urgency score and a suggested next step. A narrower scope is not sufficient:
gmail.metadata does not include message bodies, which the classification needs,
and gmail.labels gives no message content. With this scope alone the agent only
reads; it never modifies existing mail. The data lives only in server memory for a single session
that ends after 30 minutes or when the user logs out; it is not stored in a
database, not used for advertising and not used to train AI models.

## Scope justification — `gmail.compose`

Requested only when the user ticks "write drafts" on the connect screen; the box
is unticked by default. For an email the user selects, the agent writes a reply
that the user reads on the page first. After a separate confirmation that names
the recipient, that reply is saved into the user's Gmail Drafts, threaded onto
the original conversation; only after a further explicit confirmation is that same
draft sent. Google offers no drafts-only scope, and gmail.send cannot create or
update drafts, so gmail.compose is the narrowest scope that supports saving a
reply as a draft. The app never sends anything without the user's confirmation
for that specific email.

## Scope justification — `gmail.modify`

Requested only when the user ticks "tidy up" on the connect screen; the box is
unticked by default, and it is separate from the drafting box. After the agent
has categorised the user's recent mail, it marks the messages it classified as
newsletters or unsolicited mail, and offers a button that moves those - and only
those - to the user's Gmail Trash. The eligible set is decided on the server from
the categories of the run the user is looking at, so no other message can be
reached; bulk deletion asks for a confirmation on the page first. The app only
ever calls users.messages.trash, never users.messages.delete or batchDelete, so
every message stays recoverable in the user's Trash for the period Gmail
provides. A narrower scope is not sufficient: gmail.readonly cannot move a
message, gmail.compose only creates drafts and cannot touch an existing message's
labels, and Google offers no trash-only scope. The app never moves anything
without the user clicking for that specific message or confirming the bulk
action.

## How the app uses Google user data (short description)

AXIMBRA is a Budapest-based AI agent studio. Its email triage agent helps a user
see which emails need attention first: it categorises and ranks the user's recent
Gmail messages on the page and, on request, drafts replies. Email content is sent
to the OpenAI API only to produce this categorisation and the drafts shown to the
user; under OpenAI's API terms it is not used to train models. Nothing is stored
beyond the 30-minute session, no human reads the data, and it is never sold or
used for advertising. Privacy notice: https://aximbra.hu/en/adatkezeles

## Demo video script

1. Open `https://aximbra.hu/en`. Scroll down to the footer and click **Privacy**.
   Scroll to section **6. Limited use of Google user data** and pause.
2. Open `https://aximbra.hu/en/demo/email-agent`. Click the link under the sample
   button to connect a real Google account.
3. Tick the **write drafts** and the **tidy up** boxes, so the consent screen
   shows all three Gmail permissions. Pause on the Limited Use statement under the button.
4. Click **Connect — read and write drafts**. Choose the Google account.
5. If the "unverified app" warning appears: **Advanced** → continue.
6. On the consent screen, click once into the browser's address bar so the full
   URL with `client_id` is visible, pause, then tick the permissions and click
   **Continue**.
7. Back on the site: wait for the run to finish. Scroll slowly through the list —
   category, urgency and next step of each email. *(This shows gmail.readonly.)*
8. Open one email, click **draft a reply**, read it, then confirm **save to Gmail
   Drafts**. Open Gmail in a new tab → **Drafts** → open the saved reply to show
   it is threaded to the original. *(This shows gmail.compose.)*
9. Back on the site, confirm **send** for that draft. In Gmail open **Sent** and
   show the message.
9b. Scroll to the **Unimportant mail** block. Show that only newsletters and junk
   carry the mark, click **Trash** on one of them, then use **Delete all** and
   confirm. Open Gmail → **Trash** and show the messages sitting there,
   recoverable. *(This shows gmail.modify.)*
10. On the site click **Log out and disconnect**. Open
    `https://myaccount.google.com/permissions` and show that access can be removed there.

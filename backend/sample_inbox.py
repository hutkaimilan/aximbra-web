"""Példa postafiók az e-mail agent nyilvános demójához.

Miért van rá szükség:

A valódi Gmail-csatlakozás működik, de két okból rossz első élmény. A Google
egy piros "nem ellenőrzött alkalmazás" képernyőt tesz elé, amíg az app nincs
verifikálva — restricted scope-nál ez külső biztonsági auditot jelent —, és egy
most megismert ügynökségnek amúgy sem adja át senki a postafiókját. A demó
értéke nem az OAuth bizonyítása, hanem az, hogy látszik, mit csinál az agent.

Ezek a levelek kitaláltak, de nem díszletek: ugyanaz az osztályozó és ugyanaz a
fogalmazó fut rajtuk, élő modellhívással, mint egy valódi postafiókon. Amit a
látogató lát, az igazi agent-kimenet — csak a bemenet ismert.

A válogatás szándékos. Van benne olyan, amire azonnal válaszolni kell, olyan,
ami sürgősnek látszik de nem az, automatikus értesítés, csalás, hírlevél, és egy
levél, aminek a lényege egy csatolmányban van. Egy demó, amiben minden levél
fontos, semmit nem mond arról, hogy az agent tud-e rangsorolni.
"""

# 30 napnyi postafiók, relatív napokban a futás idejéhez képest — így a dátumok
# soha nem avulnak el, és a "3 napja érkezett" mindig igaz marad.
SAMPLE_EMAILS = [
    {
        "id": "sample-01",
        "days_ago": 0,
        "sender": "Kovács Anna <kovacs.anna@fenyvesipanzio.hu>",
        "subject": "Elmaradt szállítás – 3. nap",
        "body": (
            "Jó napot kívánok!\n\n"
            "Múlt hét kedden rendeltem 40 db ágyneműhuzat-garnitúrát, a visszaigazolás "
            "szerint csütörtökön érkezett volna. Azóta nem kaptam semmilyen értesítést, "
            "a telefonszámukat pedig nem veszi fel senki.\n\n"
            "Szombaton nyitunk a szezonra, 18 szoba áll felszereletlenül. Ha péntekig "
            "nem érkezik meg, kénytelen leszek máshonnan beszerezni és a foglalót "
            "visszakérni.\n\n"
            "Kérem, még ma jelezzenek vissza, hogy számíthatok-e rá.\n\n"
            "Üdvözlettel,\nKovács Anna\nFenyvesi Panzió"
        ),
    },
    {
        "id": "sample-02",
        "days_ago": 0,
        "sender": "Tóth Gergely <g.toth@medibeszerzes.hu>",
        "subject": "Árajánlatkérés – 250 db, éves keretszerződés",
        "body": (
            "Tisztelt Kollégák!\n\n"
            "Egy 12 telephelyes egészségügyi hálózat beszerzéséért felelek. A jelenlegi "
            "beszállítónk szerződése decemberben lejár, és három ajánlatot kell "
            "bekérnem a vezetőség elé.\n\n"
            "Amire ajánlatot kérek: 250 db/negyedév, éves keretszerződéssel, telephelyre "
            "szállítva. A döntést a pénzügyi igazgatóval közösen hozzuk meg.\n\n"
            "Ha a jövő hét végéig megkapom az ajánlatot, be tudom vinni a novemberi "
            "döntési körbe. Utána csak jövő tavasszal nyílik újra a keret.\n\n"
            "Köszönettel,\nTóth Gergely\nbeszerzési vezető"
        ),
    },
    {
        "id": "sample-03",
        "days_ago": 1,
        "sender": "NAV Ügyfélkapcsolat <noreply@nav.gov.hu>",
        "subject": "Értesítés hiánypótlásról – 2026/3. negyedév",
        "body": (
            "Tisztelt Adózó!\n\n"
            "A 2026. III. negyedévre benyújtott bevallásával kapcsolatban hiánypótlási "
            "felhívást bocsátottunk ki. A felhívás a Cégkapun érhető el.\n\n"
            "A hiánypótlás teljesítésének határideje a kézbesítéstől számított 15 nap. "
            "Elmulasztása esetén az eljárás a rendelkezésre álló adatok alapján folytatódik.\n\n"
            "Ez egy automatikus értesítés, kérjük, ne válaszoljon rá."
        ),
    },
    {
        "id": "sample-04",
        "days_ago": 1,
        "sender": "Nagy Péter <nagy.peter@epitoinvest.hu>",
        "subject": "Re: Re: Szerződéstervezet – 4.2 pont",
        "body": (
            "Szia!\n\n"
            "Átnéztük a jogásszal. Két dolog maradt:\n\n"
            "1. A 4.2 pontban a 30 napos fizetési határidő nálunk 60 nap, ezt minden "
            "beszállítónkkal így kötjük. Ezen nem tudunk változtatni.\n"
            "2. A késedelmi kötbér mértéke szerintünk aránytalan, a felét javasoljuk.\n\n"
            "Ha ezt a kettőt elfogadjátok, jövő héten aláírjuk. Ha nem, akkor is "
            "szóljatok, mert akkor a másik ajánlattal megyünk tovább.\n\n"
            "Üdv,\nPéter"
        ),
    },
    {
        "id": "sample-05",
        "days_ago": 2,
        "sender": "Számlázz.hu <rendszer@szamlazz.hu>",
        "subject": "Sikeres számlakiállítás – SZLA-2026-0417",
        "body": (
            "Kedves Felhasználónk!\n\n"
            "A SZLA-2026-0417 sorszámú számla sikeresen kiállításra és a NAV felé "
            "továbbításra került.\n\n"
            "Vevő: Építő Invest Kft.\nBruttó összeg: 1 270 000 Ft\nFizetési határidő: 14 nap\n\n"
            "A számla a fiókjában érhető el. Erre a levélre válaszolni nem szükséges."
        ),
    },
    {
        "id": "sample-06",
        "days_ago": 3,
        "sender": "Horváth Zsófia <zsofia@horvathstudio.hu>",
        "subject": "",
        "body": (
            "Szia!\n\n"
            "Küldöm az anyagot, amit kértél. A részletek a csatolt dokumentumban vannak, "
            "a 3. oldaltól a lényeg.\n\n"
            "Zsófi"
        ),
        "attachments": ["ajanlat_reszletek.docx"],
    },
    {
        "id": "sample-07",
        "days_ago": 4,
        "sender": "Ügyfélszolgálat <info@telekom-szamlak.biz>",
        "subject": "AZONNALI FELSZÓLÍTÁS – tartozás rendezése 24 órán belül!",
        "body": (
            "Tisztelt Ügyfelünk!\n\n"
            "Rendszerünk 5 havi elmaradást észlelt az Ön előfizetésén. Amennyiben 24 órán "
            "belül nem rendezi a tartozást, az ügyet végrehajtóhoz adjuk át és a "
            "szolgáltatást véglegesen megszüntetjük.\n\n"
            "Fizetés az alábbi linken: hxxp://telekom-szamlak.biz/befizetes\n\n"
            "Ügyintézés: azonnal!"
        ),
    },
    {
        "id": "sample-08",
        "days_ago": 5,
        "sender": "Szabó Márton <marton.szabo@logipart.hu>",
        "subject": "Automatikus válasz: Házon kívül vagyok",
        "body": (
            "Köszönöm a megkeresést.\n\n"
            "2026. szeptember 20-ig szabadságon vagyok, leveleimet nem olvasom. "
            "Sürgős esetben kollégám, Fekete Dóra segít: d.fekete@logipart.hu\n\n"
            "Üdvözlettel,\nSzabó Márton"
        ),
    },
    {
        "id": "sample-09",
        "days_ago": 7,
        "sender": "Vidra Krisztián <vidra@kavezo-bistro.hu>",
        "subject": "Kérdés a múltkori számlához",
        "body": (
            "Jó napot!\n\n"
            "A szeptemberi számlán szerepel egy 45 000 Ft-os tétel „egyéb szolgáltatás” "
            "megnevezéssel. Nem emlékszem, hogy ezt megrendeltük volna.\n\n"
            "Meg tudnák nézni, mi ez? Nem sürgős, csak a könyvelő rákérdezett.\n\n"
            "Köszönöm,\nVidra Krisztián"
        ),
    },
    {
        "id": "sample-10",
        "days_ago": 9,
        "sender": "Marketing Hírlevél <hirlevel@digitaltrendek.hu>",
        "subject": "5 AI-trend, ami 2027-ben átírja a marketinget 🚀",
        "body": (
            "Ne maradj le!\n\n"
            "Ebben a számban: generatív keresés, ügynöki automatizáció, és miért nem "
            "működik már a hagyományos hírlevél.\n\n"
            "Olvasd el a teljes cikket a weboldalunkon.\n\n"
            "Leiratkozás: a levél alján."
        ),
    },
]


# Ugyanaz a tíz eset angolul. Nem fordítás: egy angol ajánlatkérésben más a
# cégforma, a pénznem és az udvariassági formula, és a csaló levél is csak
# akkor hihető, ha a saját nyelvén az. A sorrend és a szerep viszont pontosan
# megegyezik a magyarral, hogy a demó mindkét nyelven ugyanazt bizonyítsa.
#
# A hatóságot szándékosan nem valódi hivatal küldi: a levelek kitaláltak, és
# egy létező adóhatóság nevében írni akkor sem helyes, ha a lap kiírja róla.
SAMPLE_EMAILS_EN = [
    {
        "id": "sample-01",
        "days_ago": 0,
        "sender": "Anna Coleman <anna.coleman@pinewoodrooms.co.uk>",
        "subject": "Delivery overdue - day 3",
        "body": (
            "Good morning,\n\n"
            "I ordered 40 bedding sets last Tuesday. Your confirmation said they would "
            "arrive on Thursday. Since then I have had no update at all, and nobody "
            "picks up the phone.\n\n"
            "We open for the season on Saturday with 18 rooms still unmade. If the "
            "order is not here by Friday I will have to buy elsewhere and ask for the "
            "deposit back.\n\n"
            "Please let me know today whether I can count on it.\n\n"
            "Kind regards,\nAnna Coleman\nPinewood Rooms"
        ),
    },
    {
        "id": "sample-02",
        "days_ago": 0,
        "sender": "Gregory Tate <g.tate@medisource-group.com>",
        "subject": "Request for quote - 250 units, annual framework",
        "body": (
            "Dear Sir or Madam,\n\n"
            "I handle procurement for a healthcare group with 12 sites. Our current "
            "supplier's contract ends in December and I have to put three quotes in "
            "front of the board.\n\n"
            "What I need a price for: 250 units per quarter under an annual framework "
            "agreement, delivered to site. The decision is made together with our "
            "finance director.\n\n"
            "If I have your quote by the end of next week I can take it into the "
            "November decision round. After that the budget does not reopen until "
            "spring.\n\n"
            "Many thanks,\nGregory Tate\nHead of Procurement"
        ),
    },
    {
        "id": "sample-03",
        "days_ago": 1,
        "sender": "Business Registry Office <noreply@registry-notices.example>",
        "subject": "Notice: missing documents - 2026 Q3 return",
        "body": (
            "Dear Filer,\n\n"
            "In connection with the return you submitted for Q3 2026 we have issued a "
            "request for missing documents. The request is available in your filing "
            "portal.\n\n"
            "The deadline for supplying them is 15 days from delivery of this notice. "
            "If the deadline passes, the case continues on the basis of the data "
            "already held.\n\n"
            "This is an automated message. Please do not reply."
        ),
    },
    {
        "id": "sample-04",
        "days_ago": 1,
        "sender": "Peter Nagy <peter.nagy@buildinvest-group.com>",
        "subject": "Re: Re: Draft agreement - clause 4.2",
        "body": (
            "Hello,\n\n"
            "Our partner accepts the 60-day payment term in the draft, but wants the "
            "late-payment penalty in clause 4.2 capped. They propose 0.05% per day "
            "instead of 0.1%, with a ceiling at 5% of the contract value.\n\n"
            "Legal says this is workable. Before I send it back: is the cap acceptable "
            "to you? If yes, I will have the amended draft out on Monday.\n\n"
            "Best,\nPeter"
        ),
    },
    {
        "id": "sample-05",
        "days_ago": 2,
        "sender": "Invoicing <system@invoice-service.example>",
        "subject": "Invoice issued - INV-2026-0417",
        "body": (
            "This is an automated notification.\n\n"
            "Invoice INV-2026-0417 has been issued successfully and submitted to the "
            "tax authority. Amount: 1,270.00 EUR. Customer: BuildInvest Ltd.\n\n"
            "The invoice can be downloaded from your account. No action is needed."
        ),
    },
    {
        "id": "sample-06",
        "days_ago": 3,
        "sender": "Sophie Hart <sophie@hartstudio.co.uk>",
        "subject": "",
        "body": (
            "Hi,\n\n"
            "Sending over the material you asked for. The details are in the attached "
            "document, the important part starts on page 3.\n\n"
            "Sophie"
        ),
        "attachments": ["quote_details.docx"],
    },
    {
        "id": "sample-07",
        "days_ago": 4,
        "sender": "Customer Service <info@billing-centre-secure.biz>",
        "subject": "FINAL NOTICE - settle your debt within 24 hours!",
        "body": (
            "Dear Customer,\n\n"
            "Our records show an OUTSTANDING BALANCE of 184.90 EUR on your account. "
            "Unless it is settled within 24 HOURS your service will be SUSPENDED and "
            "the case passed to debt collection.\n\n"
            "Settle now: http://billing-centre-secure.biz/pay?ref=8841\n\n"
            "Ignore this message if you have already paid."
        ),
    },
    {
        "id": "sample-08",
        "days_ago": 5,
        "sender": "Martin Shaw <martin.shaw@logipart-eu.com>",
        "subject": "Automatic reply: Out of office",
        "body": (
            "Thank you for your message.\n\n"
            "I am out of the office until 2 December with limited access to email. In "
            "urgent matters please contact my colleague at office@logipart-eu.com.\n\n"
            "This is an automatic reply."
        ),
    },
    {
        "id": "sample-09",
        "days_ago": 7,
        "sender": "Chris Vidal <chris@vidal-bistro.com>",
        "subject": "Question about last month's invoice",
        "body": (
            "Hello,\n\n"
            "On the September invoice there is a line called 'other services' for "
            "145.00 EUR. I cannot match it to anything we ordered.\n\n"
            "Could you tell me what it covers? If it is an error I would ask for a "
            "corrected invoice.\n\n"
            "Thanks,\nChris"
        ),
    },
    {
        "id": "sample-10",
        "days_ago": 9,
        "sender": "Marketing Weekly <news@digital-trends-weekly.example>",
        "subject": "5 AI trends that will rewrite marketing in 2027",
        "body": (
            "Hi there,\n\n"
            "In this issue: generative search, agentic automation, and why the "
            "traditional newsletter no longer works.\n\n"
            "Read the full article on our site.\n\n"
            "Unsubscribe: link at the bottom of this email."
        ),
    },
]

# A magyar marad az alapértelmezés; a régi név a hívók kedvéért megmarad.
SAMPLE_EMAILS_HU = SAMPLE_EMAILS
SAMPLE_SETS = {"hu": SAMPLE_EMAILS_HU, "en": SAMPLE_EMAILS_EN}


def sample_set(lang: str = "hu") -> list:
    """A nyelvhez tartozó példa levelek. Amire nincs külön készlet, az magyar.

    A többi nyelven (német, francia, román...) az angol levél idegenebb lenne,
    mint a magyar: ott az osztályozás és a válasz úgyis a felület nyelvén
    készül, a bemenet nyelve pedig a valóságban is vegyes.
    """
    return SAMPLE_SETS.get((lang or "hu").strip().lower(), SAMPLE_EMAILS_HU)


def sample_emails(now, lang: str = "hu"):
    """A példa levelek valódi dátumokkal, a hívás pillanatához igazítva.

    A dátum relatívan tárolódik, mert egy demó, amiben minden levél fél éve
    érkezett, önmagát leplezi le — a sürgősség pedig pont a dátumon múlik.
    """
    from datetime import timedelta

    out = []
    for e in sample_set(lang):
        sent = now - timedelta(days=e["days_ago"], hours=2)
        out.append({
            "id": e["id"],
            "sender": e["sender"],
            # Üres tárgynál a feliratot a lap teszi hozzá, a saját nyelvén.
            "subject": e["subject"],
            "snippet": e["body"][:120],
            "date": sent.isoformat(),
            "body": e["body"],
            # Threading fields the draft path expects. No thread to reply into:
            # a sample run can write the text, never touch a real mailbox.
            "thread_id": None,
            "message_id": "",
            "references": "",
            "reply_to": "",
            "attachments": e.get("attachments", []),
        })
    return out

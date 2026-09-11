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


def sample_emails(now):
    """A példa levelek valódi dátumokkal, a hívás pillanatához igazítva.

    A dátum relatívan tárolódik, mert egy demó, amiben minden levél fél éve
    érkezett, önmagát leplezi le — a sürgősség pedig pont a dátumon múlik.
    """
    from datetime import timedelta

    out = []
    for e in SAMPLE_EMAILS:
        sent = now - timedelta(days=e["days_ago"], hours=2)
        out.append({
            "id": e["id"],
            "sender": e["sender"],
            "subject": e["subject"] or "(nincs tárgy)",
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

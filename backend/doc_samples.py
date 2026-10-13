"""A dokumentum-elemző demó három mintadokumentuma.

Mind kitalált: a cégek, a nevek, az adószámok és az összegek nem létező
adatok, hogy a látogató valódi adat nélkül is kipróbálhassa az agentet. Egy
szándékosan furcsa feltétel mindegyikben van, hogy a „kockázat” mező ne
maradjon üres.
"""

SAMPLES = {
    "contract_hu": {
        "name": "Szolgáltatási szerződés (HU)",
        "text": """SZOLGÁLTATÁSI SZERZŐDÉS

amely létrejött egyrészről a Duna Logisztika Kft. (székhely: 1097 Budapest, Példa utca 12., adószám: 11111111-2-43), mint Megrendelő,
másrészről a Pixelvár Informatikai Bt. (székhely: 6720 Szeged, Minta tér 3., adószám: 22222222-1-06), mint Szolgáltató között, az alábbi feltételekkel.

1. A szerződés tárgya
A Szolgáltató vállalja a Megrendelő 45 munkaállomásának és 2 szerverének informatikai üzemeltetését és távoli felügyeletét.

2. Díjazás
A szolgáltatás havi díja nettó 480 000 Ft + ÁFA, amelyet a Megrendelő minden hónap 10. napjáig, átutalással fizet meg.

3. Időtartam
A szerződés 2026. november 1-jén lép hatályba, és határozatlan időre szól.

4. A Szolgáltató kötelezettségei
A Szolgáltató a hibabejelentésekre munkanapokon 4 órán belül reagál.
A Szolgáltató havonta írásos jelentést küld az elvégzett munkáról.

5. Felmondás
A szerződést bármelyik fél 90 napos felmondási idővel mondhatja fel.
A Megrendelő a szerződés első 24 hónapjában rendes felmondással nem élhet; ha mégis megszünteti, a hátralévő időszak teljes díját egy összegben köteles megfizetni.

6. Díjemelés
A Szolgáltató jogosult a díjat évente egyoldalúan, legfeljebb 15%-kal emelni, amelyről 15 nappal korábban értesíti a Megrendelőt.

Kelt: Budapest, 2026. október 15.""",
    },
    "invoice_en": {
        "name": "Supplier invoice (EN)",
        "text": """INVOICE

Invoice number: NS-2026-0418
Invoice date: 2 October 2026
Due date: 1 November 2026

Seller: Northwind Supplies Ltd., 14 Example Road, Leeds LS1 4AB, United Kingdom, VAT GB000000000
Buyer: Duna Logisztika Kft., Példa utca 12., 1097 Budapest, Hungary, EU VAT HU11111111

Description                          Qty    Unit price    Amount
Pallet wrap film, 23 µm, 500 m        120    EUR 18.50     EUR 2,220.00
Corner protectors, 1 m               1,000    EUR 0.42      EUR 420.00
Delivery (DAP Budapest)                 1    EUR 160.00    EUR 160.00

Subtotal: EUR 2,800.00
VAT: reverse charge (intra-EU supply, Article 196 of Directive 2006/112/EC)
Total due: EUR 2,800.00

Payment terms: bank transfer within 30 days of the invoice date to IBAN GB00 TEST 0000 0000 0000 00.
Late payments carry interest of 2% per month and a fixed recovery fee of EUR 70.
Goods remain the property of Northwind Supplies Ltd. until paid in full.""",
    },
    "quote_hu": {
        "name": "Árajánlat (HU)",
        "text": """ÁRAJÁNLAT

Ajánlatszám: AJ-2026/117
Kelt: 2026. október 6.
Az ajánlat érvényes: 2026. október 31-ig

Ajánlatadó: Fényes Kert Kft., 2040 Budaörs, Kitalált út 8.
Címzett: Hársfa Étterem Kft., 1052 Budapest, Képzelt utca 5.

Tárgy: Terasz árnyékolás kivitelezése

1. 6 db motoros napellenző, 4 x 3 m, szélérzékelővel — 2 340 000 Ft
2. Szerelés és villamos bekötés — 410 000 Ft
3. Elszállítás és hulladékkezelés — 60 000 Ft

Összesen: nettó 2 810 000 Ft + 27% ÁFA (bruttó 3 568 700 Ft)

Fizetési feltételek: a megrendeléskor 50% előleg, a fennmaradó összeg az átadáskor esedékes.
Kivitelezési idő: a megrendeléstől számított 5 hét.
A gyártói garancia 2 év; a garancia csak akkor érvényes, ha a Megrendelő évente a Fényes Kert Kft.-vel végezteti a karbantartást, darabonként 25 000 Ft-ért.
Az anyagárak változása esetén az ajánlatadó a végösszeget a megrendelés visszaigazolásáig módosíthatja.""",
    },
}

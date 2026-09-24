"""A lapon megjelenő szöveg ellenőrzése — nem a kódé, hanem amit az olvasó lát.

Miért itt van: a projektben a pytest az egyetlen automatikus kapu, és ez a
hibaosztály olyan, amit kódolvasással nem lehet észrevenni. A JSX eldobja a
címkék melletti sortöréseket, tehát ez:

    ... legfeljebb <b>2 évig</b>
    őrizzük.

a lapon „2 évigőrizzük"-ként jelenik meg. Kettő ilyen volt az adatkezelési
tájékoztatóban — egy jogi szövegben, ahol a legkevésbé hihető, hogy elírás.
A javítás a sor végén egy explicit `{" "}`.
"""
import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"

# Csak beágyazott (inline) címkék. A `span` szándékosan hiányzik: ebben a
# projektben blokk-elemként is használjuk (`display: block`), ott pedig a
# szóköz hiánya nem látszik, tehát csak vaklármát adna.
TAGS = r"(?:b|i|em|strong|code|a|Link)"
CLOSE_AT_EOL = re.compile(r"</" + TAGS + r">\s*$")
OPEN_AT_BOL = re.compile(r"^\s*<" + TAGS + r"[ >]")
WORD_END = re.compile(r"[\w.,;:)»”]$")
WORD_START = re.compile(r"^\s*[\w(„«]")
CLOSER = re.compile(r"^\s*</")
COMMENT = ("//", "*", "/*", "{/*")


def missing_spaces(path: pathlib.Path):
    lines = path.read_text(encoding="utf-8").split("\n")
    out = []
    for i in range(len(lines) - 1):
        cur, nxt = lines[i].rstrip(), lines[i + 1]
        if not cur or CLOSER.match(nxt):
            continue
        if cur.lstrip().startswith(COMMENT) or nxt.lstrip().startswith(COMMENT):
            continue
        if CLOSE_AT_EOL.search(cur) and WORD_START.match(nxt):
            out.append((i + 1, cur.strip(), nxt.strip()))
        elif OPEN_AT_BOL.match(nxt) and WORD_END.search(cur):
            out.append((i + 1, cur.strip(), nxt.strip()))
    return out


@pytest.mark.parametrize("path", sorted(FRONTEND.rglob("*.jsx")), ids=lambda p: p.name)
def test_no_words_glued_together_by_jsx(path):
    hits = missing_spaces(path)
    assert not hits, "A JSX itt elnyeli a szóközt (tegyél a sor végére {\" \"}):\n" + "\n".join(
        f"  {path.name}:{ln}\n    …{a[-70:]}\n  > {b[:70]}…" for ln, a, b in hits
    )


# --------------------------------------------------------- olvashatóság ---
def test_the_cards_are_not_rotated_in_3d():
    """A kártya ne dőljön meg a kurzor alatt.

    A 14 fokos térbeli forgatás miatt a böngésző egyszer kirajzolta a kártyát
    egy rétegre, és azt a kész képet döntötte meg — a szöveg pedig
    újramintázva, homályosan jelent meg, pontosan addig, amíg az ember
    olvasni akarta. A visszajelzés maradt (fénypont, megemelkedés), csak nem
    a szöveg torzításával.

    A `will-change: transform` és a `transform-style: preserve-3d` ugyanezt a
    réteget kényszeríti ki, ezért azok sem térhetnek vissza a kártyára.
    """
    agents = (FRONTEND / "components" / "Agents.jsx").read_text(encoding="utf-8")
    code = "\n".join(l for l in agents.split("\n") if not l.strip().startswith("//"))
    assert "rotateY(" not in code and "rotateX(" not in code, "a kártya megint térben forog"

    css = (FRONTEND / "index.css").read_text(encoding="utf-8")
    card_rule = css[css.index(".card { position: relative;"):]
    card_rule = card_rule[:card_rule.index("}") + 1]
    for forbidden in ("will-change", "preserve-3d"):
        assert forbidden not in card_rule, f"{forbidden} visszakerült a .card szabályba"


# A szövegdobozokat hoverkor nem toljuk el `transform`-mal. Azok a dobozok,
# amelyeken `backdrop-filter` van, saját rétegre kerülnek; egy kész réteget a
# böngésző nem rajzol újra, csak eltol. Ha az eltolás nem egész eszközpixel —
# 125%-os Windows-nagyításnál a -3px épp 3,75 —, akkor a kész képet mintázza
# újra, és a szöveg elmosódik. A `scale()` ugyanezt csinálja minden
# nagyításnál. Az emelést ezért `position: relative` + `top` adja.
STYLESHEETS = ("index.css", "components/agentsim.css")

# Csak a szöveget hordozó dobozok. A tisztán dekoratív rétegeken (.liquid a
# gomb alatt, a pulzáló pont) a transform maradhat: nincs rajtuk betű.
TEXT_BOXES = (".card", ".btn", ".ref-card", ".pkg-card", ".hero-phone", ".sim-btn", ".cf-submit")
DECORATIVE = (".liquid", ".glow", ".ref-dot", ".dot")


def _hover_rules():
    for name in STYLESHEETS:
        css = (FRONTEND / name).read_text(encoding="utf-8")
        for block in css.split("}"):
            head, _, body = block.rpartition("{")
            if not head:
                continue
            selector = head.split("\n")[-1].strip()
            if ":hover" not in selector and ":active" not in selector:
                continue
            yield name, selector, body


def test_hover_does_not_resample_text():
    offenders = []
    for name, selector, body in _hover_rules():
        if any(d in selector for d in DECORATIVE):
            continue
        if not any(b in selector for b in TEXT_BOXES):
            continue
        if "transform" in body:
            offenders.append(f"{name}: {selector} -> {body.strip()[:70]}")
    assert not offenders, (
        "Hoverkor `transform` került egy szövegdobozra — ettől lesz homályos a "
        "betű a kurzor alatt. Használj `position: relative` + `top` emelést:\n  "
        + "\n  ".join(offenders)
    )


def test_no_fractional_scale_anywhere_on_a_text_box():
    """A `scale(1.02)` minden nagyításnál újramintázza a szöveget."""
    offenders = []
    for name, selector, body in _hover_rules():
        if "scale(" in body:
            offenders.append(f"{name}: {selector} -> {body.strip()[:70]}")
    assert not offenders, "Hoverkor nagyítás:\n  " + "\n  ".join(offenders)


def test_the_simulation_has_no_copy_link_button():
    """A „Link másolása" gomb lekerült a kártyáról; ne szivárogjon vissza."""
    sim = (FRONTEND / "components" / "AgentSim.jsx").read_text(encoding="utf-8")
    assert "sim-copy" not in sim and "clipboard" not in sim, "visszakerült a link-másoló gomb"
    css = (FRONTEND / "components" / "agentsim.css").read_text(encoding="utf-8")
    assert ".sim-copy" not in css, "a .sim-copy szabály itt maradt"


def test_the_founder_introduces_himself_in_every_language():
    """A bemutatkozás magyarul és angolul is megvan.

    A többi nyelv az angolra esik vissza, tehát ha az angol hiányzik, a német
    lapon magyar szöveg jelenne meg — pontosan az a hiba, ami az agentnél már
    egyszer kiment élesbe.
    """
    for code in ("hu", "en"):
        text = (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")
        founder = text[text.index("founder: {"):]
        founder = founder[:founder.index("\n  }")]
        for key in ("bioTag:", "bio:", "facts:"):
            assert key in founder, f"{code}.js: hiányzik a founder.{key}"


def test_the_header_spans_the_screen_with_even_gaps():
    """A fejléc a teljes képernyőt fogja, egyenletes hézagokkal.

    A logó a bal szélen ül, a kapcsolat-gomb a jobb szélen, a menüpontok pedig
    egyenletesen oszlanak el közöttük. Ehhez a sáv tartalma egyetlen sorrá van
    lapítva: a burkolók `display: contents`, így a logó, a négy menüpont, a
    nyelvválasztó és a gomb mind ugyanannak a sornak a testvérei — csak így lehet
    MINDEN hézag ugyanakkora. Beágyazott dobozokkal a logó utáni hézagot a külső
    doboz szabta meg, a menüpontok közöttit a belső: más szám, szemre észrevehető.

    A két szélső elem mellett a hézag szándékosan nagyobb egy kicsivel. Ezt a
    logó jobb és a gomb bal margója adja, mert a `space-between` a margók
    levonása után oszt szét — a többi hézag így pontosan egyforma marad.
    """
    nav = (FRONTEND / "components" / "Nav.jsx").read_text(encoding="utf-8")
    assert 'className="nav-inner"' in nav, "a fejléc belső sávja eltűnt"

    css = (FRONTEND / "index.css").read_text(encoding="utf-8")
    inner = css[css.index(".nav-inner {"):]
    inner = inner[:inner.index("}") + 1]
    assert "max-width" not in inner, "a fejléc megint egy szűkebb oszlopba van zárva"
    assert "justify-content: space-between" in inner, "a fejléc elemei nem oszlanak el egyenletesen"

    desktop = css[css.index("@media (min-width: 901px){\n  .nav-right, .nav-links { display: contents; }"):]
    desktop = desktop[:desktop.index("\n}") + 2]
    assert "display: contents" in desktop, "a fejléc megint egymásba ágyazott dobozokból áll"
    assert ".nav-inner > .logo { margin-right:" in desktop, "a logó melletti nagyobb hézag elveszett"
    assert ".nav-contact-desktop { margin-left:" in desktop, "a gomb melletti nagyobb hézag elveszett"

    # A hívás-pirula 334 pixel — annyi, mint a négy menüpont együtt. Ettől lett
    # zsúfolt a sáv, ezért a fejlécből kikerült; a hero-ban és a lenyíló menüben
    # megvan.
    assert ".nav-links .btn-callbar { display: none; }" in css, \
        "a hívás-pirula visszakerült a menüsorba"
    assert 'data-testid="drawer-callbar"' in nav, "a telefonszám a lenyíló menüből is eltűnt"


def test_the_page_shows_what_can_be_checked_before_it_argues():
    """A bizonyíték-sáv a nyitány után áll, nem a lap alján.

    A négy ellenőrizhető állítás eddig a készítőt bemutató szakaszban volt, a
    lap legalján. Aki addig nem jutott el, az csak ígéreteket olvasott. A sáv
    ezért a nyitány UTÁN, az agentek ELŐTT van — és három feladatot ad, nem
    három újabb érvet.
    """
    app = (FRONTEND.parent / "src" / "App.js").read_text(encoding="utf-8")
    assert "<Proof scrollTo={scrollTo} />" in app, "a bizonyíték-sáv lekerült a lapról"
    assert app.index("<Proof") < app.index("<Agents"), "a bizonyíték-sáv az agentek mögé került"
    assert app.index("<NoTricks") > app.index("<Pricing"), \
        "az „amit nem csinálunk” az árazás elé került — a nyomásgyakorlás helye utána van"

    for code in ("hu", "en"):
        text = (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")
        for key in ("proof: {", "noTricks: {"):
            assert key in text, f"{code}.js: hiányzik a {key}"


def test_the_process_ends_with_a_measurement():
    """A folyamat visszaméréssel zárul.

    Az első lépés felméri, hova megy el az idő; enélkül a hetedik nélkül az
    egész nyitva marad — soha nem derülne ki, hogy a munka hozott-e valamit.
    Ez a modell harmadik pillére: felmérés, beavatkozás, majd újra felmérés.
    """
    for code, word in (("hu", "Visszamérés"), ("en", "Re-measurement")):
        text = (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")
        process = text[text.index("  process: {"):]
        process = process[:process.index("\n  },")]
        assert '{ n: "07"' in process, f"{code}.js: a folyamat utolsó lépése eltűnt"
        assert word in process, f"{code}.js: a visszamérés lépése átnevezve"
        assert process.count('{ n: "') == 7, f"{code}.js: nem hét lépés van"


def test_the_evidence_comes_before_the_price():
    """A bizonyíték az ár ELŐTT áll.

    Eddig fordítva volt: az árazás az esettanulmány és a referenciák előtt
    állt, tehát a látogatónak a költséget azelőtt kellett mérlegelnie, hogy
    bármit látott volna abból, amiért fizetne. A sorrend itt nem stílus,
    hanem az, hogy mihez tud viszonyítani.
    """
    app = (FRONTEND.parent / "src" / "App.js").read_text(encoding="utf-8")
    order = ["<Proof", "<Agents", "<CaseStudy", "<References", "<Objections",
             "<Process", "<Founder", "<Pricing", "<NoTricks", "<FirstStep", "<Contact"]
    seen = [app.index(tag) for tag in order]
    assert seen == sorted(seen), (
        "felborult a szakaszok sorrendje — a várt: " + " → ".join(t[1:] for t in order)
    )


def test_the_objections_are_raised_before_the_visitor_raises_them():
    """A kifogások a látogató helyett, előre.

    A retorika legrégebbi ismert fogása: az ellenérvet te hozod fel, mielőtt a
    másik megtenné. A negyedik kérdés — „mi van, ha egy év múlva abbahagyod” —
    szándékosan bent van: egy húszéves, egyszemélyes műhelynél ez a legnagyobb
    ki nem mondott ellenvetés, és kihagyni nem azt jelenti, hogy nem merül fel.
    """
    for code in ("hu", "en"):
        text = (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")
        block = text[text.index("  objections: {"):]
        block = block[:block.index("\n  },")]
        assert block.count("{ q:") == 7, f"{code}.js: nem hét ellenvetés van"
        assert "firstStep: {" in text, f"{code}.js: hiányzik a legkisebb első lépés"

    jsx = (FRONTEND / "components" / "Objections.jsx").read_text(encoding="utf-8")
    assert "useState(0)" in jsx, "az első válasz már nem nyitva indul"
    assert "aria-expanded" in jsx and "aria-controls" in jsx, "a harmonika nem jelzi az állapotát"


def test_the_footer_says_who_stands_behind_the_site():
    """A lábléc megmondja, ki áll az oldal mögött.

    A Stanford háromévnyi, több mint 4500 emberrel végzett hitelességi
    vizsgálatából négy irányelv szól ide: látszódjon, hogy valódi szervezet áll
    mögötte, legyen könnyű kapcsolatba lépni, legyen nevesített felelős, és
    legyen könnyű ellenőrizni az állításokat. A lábléc eddig ennyi volt:
    „AXIMBRA · Budapest · aximbra.hu”.

    Az adatok a legal.js-ből és a contact.js-ből jönnek, nem beírva: ugyanaz a
    név és cím áll itt, mint az impresszumban.
    """
    footer = (FRONTEND / "components" / "Contact.jsx").read_text(encoding="utf-8")
    body = footer[footer.index("export const Footer"):]
    for needed in ("CONTROLLER.name", "CONTROLLER.addressLine", "CONTROLLER.postcode",
                   "CONTACT.email", "CONTACT.phoneHref"):
        assert needed in body, f"a láblécből hiányzik: {needed}"
    assert "pathFor(lang," in body, "a jogi hivatkozások elvesztik a nyelvi előtagot"

    # Amíg nincs adószám, a lábléc ne állítson róla semmit — a „bejegyzés
    # alatt” is állítás lenne.
    assert "CONTROLLER.taxNumber &&" in body, "a lábléc adószám nélkül is mond valamit az adószámról"
    for code in ("hu", "en"):
        text = (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")
        assert "taxMissing" not in text, f"{code}.js: visszakerült a kitalált adószám-állítás"
        assert "footerId: {" in text, f"{code}.js: hiányzik a lábléc azonosító blokkja"


# ---------------------------------------------------------------------------
# A statikus index.html es a hu.js SEO-blokkja egyutt kell mozogjon
# ---------------------------------------------------------------------------

PUBLIC_HTML = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "public" / "index.html"
HU_JS = FRONTEND / "i18n" / "hu.js"


def _seo_from_hu_js() -> dict:
    """A hu.js SEO-blokkjanak cime es leirasa."""
    text = HU_JS.read_text(encoding="utf-8")
    block = re.search(r"const SEO = \{(.*?)\n\};", text, re.S)
    assert block, "a hu.js SEO-blokkja nem talalhato"
    out = {}
    for key in ("title", "description"):
        m = re.search(key + r':\s*"((?:\\.|[^"\\])*)"', block.group(1))
        assert m, f"hu.js SEO.{key} nem talalhato"
        out[key] = m.group(1)
    return out


def _meta(html: str, name: str, attr: str = "name") -> str:
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="((?:[^"])*)"', html)
    assert m, f"index.html: hianyzik a {name} meta"
    return m.group(1)


def test_the_static_html_says_the_same_as_the_app():
    """A kereso a statikus valtozatot tolti le eloszor - es sokszor azt is indexeli.

    Elesben ez vezetett oda, hogy a hu.js-ben mar at volt irva a cim, a Google
    talalat viszont tovabbra is a regit mutatta: az index.html kimaradt a
    javitasbol. A ketto egyutt kell mozogjon, kulonben a felhasznalo azt
    latja, hogy "meg mindig nem jo".
    """
    html = PUBLIC_HTML.read_text(encoding="utf-8")
    seo = _seo_from_hu_js()

    title = re.search(r"<title>(.*?)</title>", html, re.S)
    assert title, "index.html: hianyzik a <title>"
    assert title.group(1).strip() == seo["title"], (
        "az index.html cime elter a hu.js SEO-cimetol:\n"
        f"  index.html: {title.group(1).strip()}\n"
        f"  hu.js:      {seo['title']}"
    )
    assert _meta(html, "description") == seo["description"], (
        "az index.html leirasa elter a hu.js SEO-leirasatol"
    )


def test_the_business_is_not_narrowed_to_hungarian_companies():
    """A pozicionalas nemzetkozi; a "magyar cegeknek" szukites nem terhet vissza.

    Ami a tenyeket illeti (magyar mintaadat, magyar nyelvu telefon-agent,
    magyar szamrol a tulajdonos), az maradhat - ez a teszt csak azt a
    konkret szukitest tiltja, amit a Google talalat mutatott.
    """
    # Nem eleg a magyar valtozatot nezni. A szukites eloszor pont az angol
    # lapon maradt bent ("AI agents for Hungarian companies"), es epp azt
    # latja a kulfoldi latogato - meg a Google ellenore is a demovideoban.
    banned = ("magyar cégeknek", "magyar cegeknek", "for Hungarian companies")
    paths = [PUBLIC_HTML, *sorted((FRONTEND / "i18n").glob("*.js"))]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in text, f"{path.name}: visszater a szukites ({phrase!r})"


# ---------------------------------------------------------------------------
# Arak es penznemek
# ---------------------------------------------------------------------------

LANG_FILES = ("hu", "en", "de", "es", "fr", "it", "ro", "sk")
MONEY_JS = FRONTEND / "money.js"
PRICE_TOKEN = re.compile(r'price: "(\d+(?:-\d+)?\+?)"')


def _lang_source(code):
    return (FRONTEND / "i18n" / f"{code}.js").read_text(encoding="utf-8")


def test_no_price_is_hardcoded_in_a_currency():
    """Az arak forintosszegek, nem kesz szovegek.

    Amig "120 000 Ft" allt a nyolc fajlban, a nemet es a roman latogato is
    forintot latott - egy nemet cegvezetonek az nem ar, hanem rejtveny. A
    penznemet a money.js teszi ra a nyelv alapjan, ezert itt szam all.
    """
    for code in LANG_FILES:
        text = _lang_source(code)
        for bad in ("Ft", "eFt", "MFt", "€", "RON", "lei"):
            for line in text.splitlines():
                if line.strip().startswith("//") or "fxNote" in line:
                    continue  # a megjegyzes maga leirja az arfolyamot
                assert not (f'price: "' in line and bad in line), (
                    f"{code}.js: a penznem beegett az arba - {line.strip()}"
                )


def test_every_price_is_a_number_the_formatter_understands():
    """Egy elgepelt ar ures helyet hagyna a kartyan, hibauzenet nelkul."""
    for code in LANG_FILES:
        text = _lang_source(code)
        raw = re.findall(r'price: "([^"]*)"', text)
        assert raw, f"{code}.js: egyetlen ar sincs benne"
        for value in raw:
            assert PRICE_TOKEN.fullmatch(f'price: "{value}"'), (
                f"{code}.js: ertelmezhetetlen ar: {value!r}"
            )


def test_hungarian_and_english_agree_on_what_the_agents_cost():
    """A tobbi nyelv az angoltol orokli az agent-arakat, az angol a magyartol.

    Ha a ketto elcsuszik, a magyar lapon mas ar all, mint a nemeten - es ezt
    csak egy ugyfel veszi eszre, arajanlatkeres kozben.
    """
    def agent_prices(code):
        text = _lang_source(code)
        start = text.index("\n  agents: [")
        end = text.index("\n  ],", start)
        return re.findall(r'price: "([^"]*)"', text[start:end])

    hu_prices, en_prices = agent_prices("hu"), agent_prices("en")
    assert hu_prices, "hu.js: nincs agent-ar"
    assert hu_prices == en_prices, (
        f"a magyar es az angol agent-arak elcsusztak: {hu_prices} vs {en_prices}"
    )


def test_every_language_says_which_rate_it_converted_at():
    """Atvaltott arat arfolyam nelkul kiirni felrevezetes.

    A magyar lapon nincs atvaltas, ezert ott ures a megjegyzes; minden mas
    nyelven kotelezo, es meg kell neveznie a szamot, amivel dolgoztunk.
    """
    money = MONEY_JS.read_text(encoding="utf-8")
    for code in LANG_FILES:
        text = _lang_source(code)
        assert "fromFmt:" in text, f"{code}.js: hianyzik a fromFmt"
        note = re.search(r'fxNote: "([^"]*)"', text)
        assert note, f"{code}.js: hianyzik az fxNote"
        if code == "hu":
            assert note.group(1) == "", "hu.js: nincs atvaltas, ne legyen arfolyam-szoveg"
            continue
        assert note.group(1), f"{code}.js: atvaltott arak arfolyam-megjegyzes nelkul"
        # A kiirt arfolyamnak abbol a szambol kell jonnie, amivel a kod szamol.
        rate = "80" if code == "ro" else "400"
        assert f"{rate} Ft" in note.group(1), (
            f"{code}.js: az arfolyam-szoveg nem a money.js ertekevel szamol ({rate})"
        )
        assert f"RON: {rate}" in money or f"EUR: {rate}" in money, (
            f"money.js: hianyzik a {rate}-as arfolyam"
        )


def test_the_formatter_knows_every_language_on_the_site():
    """Uj nyelv eseten a penznem-tabla nem maradhat le - kulonben euroban
    latna az arat valaki, akinek nem az a penzneme."""
    money = MONEY_JS.read_text(encoding="utf-8")
    block = money[money.index("CURRENCY_BY_LANG"):money.index("export const currencyFor")]
    for code in LANG_FILES:
        assert f"{code}:" in block, f"money.js: a {code} nyelvhez nincs penznem"


# ---------------------------------------------------------------------------
# "Hivjon vissza"
# ---------------------------------------------------------------------------

CALLBACK_KEYS = (
    "title", "lead", "placeholder", "cta", "sending", "ok",
    "errNumber", "errCountry", "errRepeat", "errDaily", "errFailed", "privacy",
)


def test_the_callback_form_speaks_every_language():
    """Egy hianyzo kulcs itt ures gombot vagy `undefined`-ot jelentene a lapon.

    Ez a blokk nem oroklodhet az angolbol ugy, hogy eszre se vesszuk: a
    placeholder es a hibauzenetek orszagonkent mas telefonszam-alakot
    mutatnak, es egy nemet latogatonak a "+36 30 123 4567" minta semmit nem
    mond arrol, hogyan irja le a sajatjat.
    """
    for code in LANG_FILES:
        text = _lang_source(code)
        block = re.search(r"\n    callback: \{(.*?)\n    \},", text, re.S)
        assert block, f"{code}.js: nincs callback blokk a hero-ban"
        for key in CALLBACK_KEYS:
            assert f"{key}:" in block.group(1), f"{code}.js: hianyzik a callback.{key}"


def test_the_placeholder_is_a_local_number_in_every_language():
    """A minta-szam ne mindenhol magyar legyen.

    Az elso valtozatban minden nyelv a "+36 30 123 4567" mintat mutatta -
    ez egy nemet latogatonak pont azt nem arulja el, amit kellene.
    """
    expected = {
        "hu": "+36", "en": "+44", "de": "+49", "es": "+34",
        "fr": "+33", "it": "+39", "ro": "+40", "sk": "+421",
    }
    for code, prefix in expected.items():
        text = _lang_source(code)
        block = re.search(r"\n    callback: \{(.*?)\n    \},", text, re.S)
        assert block, code
        ph = re.search(r'placeholder: "([^"]*)"', block.group(1))
        assert ph, f"{code}.js: nincs placeholder"
        assert ph.group(1).startswith(prefix), (
            f"{code}.js: a minta-szam {ph.group(1)!r}, pedig {prefix} kellene"
        )


def test_the_callback_form_says_what_happens_to_the_number():
    """Telefonszamot elkerni adatkezelesi mondat nelkul nem korrekt."""
    for code in LANG_FILES:
        block = re.search(
            r"\n    callback: \{(.*?)\n    \},", _lang_source(code), re.S
        )
        privacy = re.search(r'privacy: "([^"]*)"', block.group(1))
        assert privacy and len(privacy.group(1)) > 30, (
            f"{code}.js: hianyzik vagy ures az adatkezelesi mondat"
        )


# ---------------------------------------------------------------------------
# Fulcimek, holt linkek, nem letezo cimek
# ---------------------------------------------------------------------------

APP_JS = FRONTEND / "App.js"
DEMOS_DIR = FRONTEND / "demos"


def test_the_website_page_has_a_title_in_every_language():
    """A /weboldal fulcime hat nyelven angolul allt.

    A lap tartalma le volt forditva, a bongeszofulon viszont "Website design
    and development" - es a keresotalalat cime is az. Pont ez az a reszlet,
    amitol egy forditas felkesznek latszik.
    """
    for code in LANG_FILES:
        text = _lang_source(code)
        block = re.search(r"\n  webPage: \{(.*?)\n  \},", text, re.S)
        assert block, f"{code}.js: nincs webPage blokk"
        title = re.search(r'title: "([^"]*)"', block.group(1))
        assert title and title.group(1).strip(), f"{code}.js: nincs /weboldal fulcim"

    # ...es a cimek tenyleg kulonbozoek, nem mindenhol az angol masolata.
    titles = set()
    for code in LANG_FILES:
        block = re.search(r"\n  webPage: \{(.*?)\n  \},", _lang_source(code), re.S)
        titles.add(re.search(r'title: "([^"]*)"', block.group(1)).group(1))
    assert len(titles) >= 7, f"gyanusan sok azonos cim: {sorted(titles)}"


def test_an_unknown_address_is_not_the_home_page():
    """Eddig minden nem letezo cim a fooldalt adta vissza, 200-as valasszal.

    A Google ezt "soft 404"-kent kezeli: ugy latja, hogy tetszoleges sok cimen
    ugyanaz a lap all. A statikus kiszolgalo nem tud 404-et adni, ezert a
    `noindex` az, ami ezeket tavol tartja a keresobol.
    """
    app = APP_JS.read_text(encoding="utf-8")
    assert 'path="*" element={<NotFound />}' in app, (
        "az ismeretlen cim megint a fooldalra esik vissza"
    )
    nf = (FRONTEND / "pages" / "NotFound.jsx").read_text(encoding="utf-8")
    assert "noindex: true" in nf, "a 404-lap bekerulhet a keresobe"
    # Nyolc nyelven szol, kulonben a nemet latogato magyarul kap hibauzenetet.
    for code in LANG_FILES:
        text = _lang_source(code)
        block = re.search(r"\n  notFound: \{(.*?)\n  \},", text, re.S)
        assert block, f"{code}.js: nincs notFound blokk"
        for key in ("title", "lead", "home", "agents"):
            assert f"{key}:" in block.group(1), f"{code}.js: hianyzik a notFound.{key}"


def test_the_demo_sites_have_no_dead_contact_links():
    """A bemutato oldalak nem letezo tartomanyokra kuldtek levelet.

    A `*-demo.hu` cimek nincsenek bejegyezve: a gombra kattintva megnyilt a
    levelezo, a level pedig visszapattant. A lapon ott a kapcsolati blokk -
    a gomb oda vigyen.
    """
    for path in sorted(DEMOS_DIR.glob("*.jsx")):
        text = path.read_text(encoding="utf-8")
        assert "mailto:${d.email}" not in text, (
            f"{path.name}: visszater a nem letezo cimre mutato mailto"
        )
        # Horgony, ami sehova nem visz.
        assert 'href="#"' not in text, f"{path.name}: holt horgony (#)"

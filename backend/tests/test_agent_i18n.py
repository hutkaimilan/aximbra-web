"""Az agent lapja nyolc nyelven fut — tényleg mind a nyolcon.

Egy hiányzó kulcs nem hibát okoz, hanem csendes visszaesést: a német látogató
egyetlen magyar mondatot kap a többi német közé, és ez pont az a fajta hiba,
amit senki nem jelent be. Ezért gép nézi.

Node nélkül olvassuk a fájlt: a kiszolgáló képében nincs JavaScript-futtató, és
egy tesztnek nem szabad ettől függenie. A fájl formája elég szabályos ahhoz,
hogy a kulcsutakat zárójel-számlálással ki lehessen szedni.
"""
import pathlib
import re

AGENT_JS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "agent.js"
LANGS = ["hu", "en", "de", "es", "fr", "it", "ro", "sk"]

# A szimulációk agens-kulcsai számok (0:, 1:, …), nem azonosítók. Egy soron
# több kulcs is lehet — a tömör írásmódban a `0: { start: ..., closing: ... }`
# három kulcs egy sorban —, ezért nem elég a sor elejét nézni.
KEY = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*|\d+)\s*:')
KEY_ANY = re.compile(r'(?:^\s*|[{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*|\d+)\s*:')
OPENS = re.compile(r"[{\[]")
CLOSES = re.compile(r"[}\]]")
# A szövegen belüli zárójelet nem szabad szerkezetnek nézni: a francia
# figyelmeztetésben a „([comme ceci])" két sorba tördelve pont ezt csinálta.
STRING = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")


def key_paths(text: str) -> dict:
    """Nyelvenként a kulcsutak halmaza.

    Egy sor egyszerre nyithat és zárhat — `reasons: [...] },` például kulcsot is
    deklarál és lezárja a szülőt. Ezért a zárójel-mérleget mindig alkalmazni
    kell, nem csak akkor, ha a sor nem kulccsal kezdődik; e nélkül a szintek
    egymásba csúsztak.
    """
    out, stack, lang = {}, [], None
    depth = 0
    for raw in text.split("\n"):
        line = STRING.sub('""', raw.split("//")[0])
        m = KEY.match(line)
        opens = len(OPENS.findall(line))
        closes = len(CLOSES.findall(line))
        net = opens - closes
        if m:
            name = m.group(1)
            if depth == 1:                       # nyelvi blokk kezdete
                lang, stack = name, []
                out.setdefault(lang, set())
            elif lang:
                names = [k.group(1) for k in KEY_ANY.finditer(line)]
                for n in names:
                    out[lang].add(".".join(stack + [n]))
                if net > 0 and names:
                    stack.append(names[0])
        if net < 0:
            for _ in range(-net):
                if stack:
                    stack.pop()
        depth += net
        if depth <= 0:
            lang, stack = None, []
    return out


def test_every_language_has_every_key():
    paths = key_paths(AGENT_JS.read_text(encoding="utf-8"))
    assert sorted(paths) == sorted(LANGS), f"nyelvek: {sorted(paths)}"
    base = paths["hu"]
    assert len(base) > 80, f"gyanúsan kevés kulcs: {len(base)}"
    for lang in LANGS:
        missing = base - paths[lang]
        extra = paths[lang] - base
        assert not missing, f"{lang}: hiányzó kulcs: {sorted(missing)}"
        assert not extra, f"{lang}: ismeretlen kulcs: {sorted(extra)}"


def test_the_categories_match_the_server():
    """A modell kulcsot ad vissza; ha a felület nem ismeri, a nyers kulcs
    jelenne meg a lapon („customer_complaint”)."""
    import server

    paths = key_paths(AGENT_JS.read_text(encoding="utf-8"))
    ui = {p.split(".", 1)[1] for p in paths["hu"] if p.startswith("cat.")}
    assert ui == server.AGENT_CATEGORIES, f"eltérés: {ui ^ server.AGENT_CATEGORIES}"


SIMS_JS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "sims.js"


def test_every_language_tells_the_same_simulation():
    """A szimulációk elbeszélő szövege is nyolc nyelven van.

    Itt a szerkezet számít: az indoklások sorrendje kötött (reasons[i] a
    picks[i]-hez tartozik), tehát egy kimaradt sor nem hiányzó szöveg, hanem
    rossz helyre kerülő indoklás.
    """
    paths = key_paths(SIMS_JS.read_text(encoding="utf-8"))
    assert sorted(paths) == sorted(LANGS), f"nyelvek: {sorted(paths)}"
    base = paths["hu"]
    assert len(base) > 50, f"gyanúsan kevés kulcs: {len(base)}"
    for lang in LANGS:
        assert not base - paths[lang], f"{lang}: hiányzik {sorted(base - paths[lang])}"
        assert not paths[lang] - base, f"{lang}: ismeretlen {sorted(paths[lang] - base)}"


def test_the_simulation_narrative_does_not_live_in_two_places():
    """Az agentSims.js a szerkezet, az i18n a szöveg. Ha a magyar szöveg
    visszaszivárog a szerkezetbe, az a fordítás mellett csendben elavul."""
    structure = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
                 / "components" / "agentSims.js").read_text(encoding="utf-8")
    body = "\n".join(l for l in structure.split("\n") if not l.strip().startswith("//"))
    for field in ("start:", "beforeLabel:", "afterHead:", "closing:", "audit:"):
        assert field not in body, f"{field} visszakerült az agentSims.js-be"

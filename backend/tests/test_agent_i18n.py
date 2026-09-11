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

KEY = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:')
OPENS = re.compile(r"[{\[]")
CLOSES = re.compile(r"[}\]]")
# A szövegen belüli zárójelet nem szabad szerkezetnek nézni: a francia
# figyelmeztetésben a „([comme ceci])" két sorba tördelve pont ezt csinálta.
STRING = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")


def key_paths(text: str) -> dict:
    """Nyelvenként a kulcsutak halmaza."""
    out, stack, lang = {}, [], None
    depth = 0
    for raw in text.split("\n"):
        line = STRING.sub('""', raw.split("//")[0])
        m = KEY.match(line)
        opens = len(OPENS.findall(line))
        closes = len(CLOSES.findall(line))
        if m:
            name = m.group(1)
            if depth == 1:                       # nyelvi blokk kezdete
                lang, stack = name, []
                out.setdefault(lang, set())
            elif lang:
                path = ".".join(stack + [name])
                out[lang].add(path)
                if opens > closes:               # beágyazott objektum nyílik
                    stack.append(name)
        elif lang and closes > opens and stack:
            stack.pop()
        depth += opens - closes
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

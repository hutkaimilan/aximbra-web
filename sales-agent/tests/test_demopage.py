"""A személyre szabott demóoldal: letöltés, ellenőrzés, összeállítás, API.
Hálózat és modell nélkül: a weboldal és a modell válasza csonk."""
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import demopage  # noqa: E402
import llm  # noqa: E402
from store import Store  # noqa: E402

HOME = """<html lang="hu"><head><title>Kert Bisztró – Szeged</title>
<meta name="description" content="Bisztró Szeged belvárosában"></head><body>
<header><nav><a href="/rolunk">Rólunk</a> <a href="/etlap">Étlap</a> <a href="/adatvedelem">Adatvédelem</a>
<a href="https://facebook.com/kert">Facebook</a> <a href="/kapcsolat">Kapcsolat</a></nav>
<p>Ez a menüben lévő mondat sosem lehet idézet, mert a fejlécben van.</p></header>
<main><h1>Üdvözöljük</h1>
<p>Asztalfoglalást hétköznap délután négy óráig telefonon fogadunk, hétvégén csak e-mailben.</p>
<p>Rövid szöveg.</p>
<p>Rendezvényekre egyedi ajánlatot küldünk, a kérést a weboldalon lévő űrlapon lehet leadni.</p>
</main>
<footer><p>Minden jog fenntartva, a Kert Bisztró és partnerei által üzemeltetve 2026 óta.</p></footer>
</body></html>"""

ABOUT = """<html><body><main><p>Családi vállalkozásként 2009 óta főzünk szezonális alapanyagokból a vendégeinknek.</p>
</main></body></html>"""

SITE = {"https://kertbisztro.hu/": HOME, "https://kertbisztro.hu/rolunk": ABOUT}


class FakeFetcher:
    def __init__(self, site=SITE):
        self.site = site
        self.asked = []

    def fetch(self, url):
        self.asked.append(url)
        return (url, self.site[url]) if url in self.site else None


GOOD_QUOTE = "Asztalfoglalást hétköznap délután négy óráig telefonon fogadunk, hétvégén csak e-mailben."

ANALYSIS = {
    "language": "hu", "company_name": "Kert Bisztró",
    "what_they_do": "Szegedi bisztró, asztalfoglalással és rendezvényekkel.",
    "audience": "szegedi vendégek", "repetitive_work": ["Foglalások felvétele telefonon"],
    "observation": {"quote": GOOD_QUOTE, "page_url": "https://kertbisztro.hu/",
                    "insight": "A foglalás nagy része telefonon jön."},
    "support_evidence": None,
    "main_agent": {"id": "phone", "reason": "A foglalás telefonon jön.",
                   "what_it_does": "Felveszi a foglalási hívásokat, és összefoglalót küld."},
    "secondary_agents": [{"id": "email", "reason": "Hétvégén e-mailben foglalnak."},
                         {"id": "phone", "reason": "ugyanaz, mint a fő"}, {"id": "nincs-ilyen", "reason": "x"}],
    "custom_agent_idea": None,
}

CONTENT = {
    "hero_subtitle": "Egy AI-recepciós felveszi a foglalási hívásokat.",
    "agent_pitch": "Felveszi a telefont, és rögzíti a foglalást.",
    "agent_steps": ["Felveszi", "Rögzíti", "Elküldi"],
    "demo": {"title": "Egy foglalási hívás", "intro": "Hallgasd meg.", "summary": "Foglalás: 4 fő, péntek 19:00.",
             "items": [{"subtitle": "caller", "body": "Jó napot, asztalt foglalnék."},
                       {"subtitle": "agent", "body": "Hány főre és mikorra?"},
                       {"subtitle": "caller", "body": "Négy főre, péntek este hétre, a számom +36 30 123 4567."},
                       {"subtitle": "agent", "body": "Rögzítettem, visszaigazolást küldök."}]},
    "roi": {"hours_per_month": 25, "hourly_rate_huf": 7000, "assumptions": ["Havi 300 hívás", "2 perc hívásonként"]},
    "price_text": "", "lead_text": "",
    "quote_check": {"full_sentence": True, "has_verb": True},
}


def fake_llm(analysis=None, content=CONTENT, analyses=None, contents=None):
    """ask(): az elemző és a tartalomíró prompt alapján más-más választ ad."""
    seen = []
    aq = list(analyses) if analyses else None
    cq = list(contents) if contents else None

    def ask(prompt):
        seen.append(prompt)
        if prompt.startswith("You are a senior AI-automation consultant"):
            a = aq.pop(0) if aq else analysis
        else:
            a = cq.pop(0) if cq else content
        return a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)
    return ask, seen


@pytest.fixture(autouse=True)
def public_hosts(monkeypatch):
    monkeypatch.setattr(demopage, "host_ok", lambda h: bool(h) and not h.startswith(("127.", "10.", "169.254.")))


def build(analysis=ANALYSIS, **kw):
    ask, seen = fake_llm(analysis, **{k: kw.pop(k) for k in ("content", "analyses", "contents") if k in kw})
    page = demopage.build_page("kertbisztro.hu", ask=ask, extract_json=llm.extract_json,
                               fetcher=FakeFetcher(kw.pop("site", SITE)), **kw)
    return page, seen


# ---- szövegkinyerés -----------------------------------------------------------

def test_extract_keeps_body_paragraphs_and_drops_menu_and_footer():
    e = demopage.extract(HOME)
    assert e["lang"] == "hu" and e["title"] == "Kert Bisztró – Szeged"
    assert e["description"] == "Bisztró Szeged belvárosában"
    assert GOOD_QUOTE in e["paras"]
    assert not any("menüben" in p for p in e["paras"])
    assert not any("jog fenntartva" in p for p in e["paras"])
    # A teljes szövegben (bizonyítékhoz) a menü is benne van.
    assert "Étlap" in e["text"]


def test_extract_survives_broken_html():
    e = demopage.extract("<html><body><p>Félbehagyott <b>bekezdés <div><p>második")
    assert "Félbehagyott" in e["text"]


def test_pick_subpages_same_site_relevant_first_skips_legal():
    subs = demopage.pick_subpages("https://kertbisztro.hu/", ["/adatvedelem", "https://facebook.com/x",
                                                              "/blog/2019/01/02/hosszu", "/rolunk", "/x.pdf",
                                                              "mailto:a@b.hu", "/kapcsolat", "/rolunk#csapat"])
    assert subs[:2] == ["https://kertbisztro.hu/rolunk", "https://kertbisztro.hu/kapcsolat"] or \
        set(subs[:2]) == {"https://kertbisztro.hu/rolunk", "https://kertbisztro.hu/kapcsolat"}
    assert not any("adatvedelem" in s or "facebook" in s or s.endswith(".pdf") for s in subs)
    assert len(subs) == len(set(subs))


def test_pick_subpages_skips_other_language_versions():
    subs = demopage.pick_subpages("https://bor.hu/hu", ["/en", "/de/kontakt", "/hu/boltok", "/hu/rolunk"])
    assert set(subs) == {"https://bor.hu/hu/boltok", "https://bor.hu/hu/rolunk"}


def test_redirect_to_login_page_is_dropped():
    class F(FakeFetcher):
        def fetch(self, url):
            if url.endswith("/rolunk"):
                return "https://kertbisztro.hu/belepes", ABOUT
            return super().fetch(url)
    pages = demopage.crawl("https://kertbisztro.hu/", F())
    assert [p["url"] for p in pages] == ["https://kertbisztro.hu/"]


@pytest.mark.parametrize("lang,text", [
    ("hu", "A cégünk 2009 óta foglalkozik azzal, hogy a vendégek és a partnerek minden kérdésre gyors választ kapjanak, "
           "és ha kell, egy órán belül visszahívjuk őket. Az irodánk Szegeden van, de az egész országban dolgozunk."),
    ("de", "Wir sind ein Familienbetrieb aus Graz und liefern seit 1998 Fenster und Türen für private Kunden und für "
           "Bauträger. Die Beratung ist kostenlos, und wir kommen auf Wunsch auch zu Ihnen nach Hause."),
    ("en", "We are a small family business from Leeds and have been making windows and doors for homeowners and "
           "builders since 1998. The consultation is free and we can also visit you at your home."),
])
def test_guess_lang(lang, text):
    assert demopage.guess_lang(text * 2) == lang


def test_guess_lang_unsure_returns_none():
    assert demopage.guess_lang("Nike Adidas Puma 42 43 44 kosár akció " * 10) is None


def test_crawl_falls_back_to_www():
    site = {"https://www.kertbisztro.hu/": HOME}
    pages = demopage.crawl("https://kertbisztro.hu/", FakeFetcher(site))
    assert pages and pages[0]["url"] == "https://www.kertbisztro.hu/"


# ---- idézet és bizonyíték ------------------------------------------------------

def test_good_quote_accepts_full_verbatim_sentence():
    para = "Bevezető mondat itt áll. " + GOOD_QUOTE
    assert demopage.good_quote(GOOD_QUOTE, para)
    assert demopage.good_quote("„" + GOOD_QUOTE + "”", para)


@pytest.mark.parametrize("q", [
    "Rövid mondat csak.",                                              # 8 szónál kevesebb
    "Asztalfoglalást hétköznap délután négy óráig telefonon fogadunk",  # nincs mondatvég
    "Asztalfoglalást hétköznap délután négy óráig fogadunk szívesen mindig.",  # nincs szó szerint ott
    "Asztalfoglalást hétköznap délután négy óráig telefonon fogadunk. Hétvégén csak e-mailben jöhet.",
    "Hívjon minket bármikor a +36 30 123 4567 számon, ha asztalt foglalna.",
    "ASZTALFOGLALÁST HÉTKÖZNAP DÉLUTÁN NÉGY ÓRÁIG TELEFONON FOGADUNK MINDIG.",
])
def test_good_quote_rejects(q):
    para = q + " " + GOOD_QUOTE if "fogadunk szívesen" not in q else GOOD_QUOTE
    assert not demopage.good_quote(q, para)


def test_evidence_must_be_on_pages():
    pages = [{"text": "Foglalás  telefonon fogadunk"}]
    assert demopage.evidence_on_pages("telefonon fogadunk", pages)
    assert not demopage.evidence_on_pages("e-mailben fogadunk", pages)
    assert not demopage.evidence_on_pages("", pages)


# ---- biztonságos letöltés ------------------------------------------------------

def test_host_ok_rejects_internal_addresses(monkeypatch):
    monkeypatch.undo()  # a valódi host_ok kell
    for h in ("127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1", ""):
        assert not demopage.host_ok(h), h
    assert demopage.host_ok("8.8.8.8")


@pytest.mark.parametrize("raw", ["", "nem url", "ftp://x.hu", "https://localhost"])
def test_normalize_url_rejects(raw):
    with pytest.raises(demopage.DemoError):
        demopage.normalize_url(raw)


def test_normalize_url_adds_scheme():
    assert demopage.normalize_url(" KertBisztro.hu ") == "https://kertbisztro.hu/"


class _Resp:
    def __init__(self, status, headers=None, content=b""):
        self.status_code, self.headers, self.content = status, headers or {}, content
        self.encoding = None


def test_redirect_to_internal_address_is_not_followed(monkeypatch):
    f = demopage.Fetcher()
    monkeypatch.setattr(f, "_allowed", lambda url: True)
    calls = []

    def one(url):
        calls.append(url)
        return _Resp(302, {"location": "http://169.254.169.254/latest/meta-data/"})
    monkeypatch.setattr(f, "_one", one)
    assert f.fetch("https://kertbisztro.hu/") is None
    assert calls == ["https://kertbisztro.hu/"]


def test_redirect_loop_stops(monkeypatch):
    f = demopage.Fetcher()
    monkeypatch.setattr(f, "_allowed", lambda url: True)
    monkeypatch.setattr(f, "_one", lambda url: _Resp(301, {"location": "/again"}))
    assert f.fetch("https://kertbisztro.hu/") is None


def test_robots_disallow_is_respected(monkeypatch):
    f = demopage.Fetcher()
    robots = _Resp(200, {}, b"User-agent: *\nDisallow: /\n")
    page = _Resp(200, {"content-type": "text/html"}, b"<p>x</p>")
    monkeypatch.setattr(f, "_one", lambda url: robots if url.endswith("/robots.txt") else page)
    assert f.fetch("https://kertbisztro.hu/") is None


def test_meta_charset_is_used_when_header_has_none(monkeypatch):
    f = demopage.Fetcher()
    monkeypatch.setattr(f, "_allowed", lambda url: True)
    body = '<meta charset="iso-8859-2"><p>Árvíztűrő tükörfúrógép</p>'.encode("iso-8859-2")
    monkeypatch.setattr(f, "_one", lambda url: _Resp(200, {"content-type": "text/html"}, body))
    _, src = f.fetch("https://kertbisztro.hu/")
    assert "Árvíztűrő tükörfúrógép" in src


def test_invalid_certificate_retries_without_verification(monkeypatch):
    import httpx
    f = demopage.Fetcher()
    calls = []

    def get(url, verify):
        calls.append(verify)
        if verify:
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired")
        return _Resp(200)
    monkeypatch.setattr(f, "_get", get)
    assert f._one("https://kertbisztro.hu/").status_code == 200
    assert calls == [True, False]
    # Más hálózati hibánál nem kapcsoljuk ki az ellenőrzést.
    g = demopage.Fetcher()
    calls.clear()

    def refused(url, verify):
        calls.append(verify)
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(g, "_get", refused)
    assert g._one("https://masik.hu/") is None and calls == [True]


# ---- katalógus és felület -----------------------------------------------------

def test_every_catalog_kind_has_a_demo_spec_and_the_ui_is_complete():
    assert {a["kind"] for a in demopage.CATALOG.values()} <= set(demopage.KIND_SPEC)
    assert set(demopage.HU_UI) == set(demopage.EN_UI)
    assert set(demopage.FALLBACK) == {"hu", "en"}
    for k, a in demopage.CATALOG.items():
        assert a["name_en"] and a["price_en"] and a["lead_en"], k


def test_untranslated_names_fall_back_to_english_not_hungarian():
    page, _ = build(lang="fr")
    assert page["agent"]["name"] == "AI phone receptionist" and page["agent"]["lead_text"] == "on quote"
    assert page["secondary"][0]["name"] == "Email triage agent"


def test_no_twenty_minute_offer_anywhere_in_the_repo():
    # A tulajdonos kérése (2026-10-23): "20 perc" / "Beszéljünk 20 percet" sehol,
    # egyik nyelven sem: se a weboldalon, se a leveleken, se a telefonon.
    import re as _re
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bad = _re.compile(r"húsz ?perc|20 ?perc|twenty.minute|20.min(?:ute|ut)|zwanzig minut|veinte minut|vingt minut|"
                      r"venti minut|douăzeci de minut|dvadsať minút|二十分钟|20 ?分钟", _re.I)
    hits = []
    for sub in ("frontend/src", "frontend/public", "sales-agent", "voice-agent/src", "video-agent", "backend",
                "webshop-agent"):
        for dirpath, dirs, files in os.walk(os.path.join(root, sub)):
            dirs[:] = [d for d in dirs if d not in ("node_modules", "build", "dist", "__pycache__", "tests")]
            for f in files:
                if f.endswith((".py", ".js", ".jsx", ".ts", ".html", ".json")) and not f.endswith(".test.ts"):
                    with open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore") as fh:
                        for n, line in enumerate(fh, 1):
                            if bad.search(line):
                                hits.append(f"{sub}/{f}:{n}")
    assert not hits, hits


def test_no_twenty_minute_call_offer_on_the_page():
    # A tulajdonos kérése (2026-10-23): a "Beszéljünk 20 percet" felhívás soha
    # többé nem kerülhet az oldalra, egyik nyelven sem.
    for ui in (demopage.HU_UI, demopage.EN_UI):
        text = " ".join(ui.values()).lower()
        assert "20" not in text and "húsz" not in text and "twenty" not in text


@pytest.mark.parametrize("name,title", [
    ("Kert Bisztró", "Ezt csinálná egy AI agent a Kert Bisztrónál"),
    ("Bortársaság", "Ezt csinálná egy AI agent a Bortársaságnál"),
    ("Kifli.hu", "Ezt csinálná egy AI agent a Kifli.hu-nál"),
    ("OTP", "Ezt csinálná egy AI agent az OTP-nél"),
    ("Optika Bt.", "Ezt csinálná egy AI agent az Optika Bt.-nél"),
    ("123 Szerviz", "Ezt csinálná egy AI agent a(z) 123 Szerviznél"),
    ("BKK", "Ezt csinálná egy AI agent a BKK-nál"),
    ("Kovács Kft.", "Ezt csinálná egy AI agent a Kovács Kft.-nél"),
    ("Ablak Zrt", "Ezt csinálná egy AI agent az Ablak Zrt-nél"),
])
def test_hungarian_title_grammar(name, title):
    assert demopage.title_and_footer(name, "hu", demopage.HU_UI, False)[0] == title


# ---- összeállítás -------------------------------------------------------------

def test_build_page_keeps_only_verified_claims():
    page, _ = build()
    assert page["generic"] is False and page["company"] == "Kert Bisztró" and page["lang"] == "hu"
    assert page["title"] == "Ezt csinálná egy AI agent a Kert Bisztrónál"
    assert page["observation"]["quote"] == GOOD_QUOTE
    assert page["observation"]["page_url"] == "https://kertbisztro.hu/"
    assert page["agent"]["id"] == "phone" and page["agent"]["demo_url"].startswith("tel:")
    assert [e["id"] for e in page["secondary"]] == ["email"]
    assert page["demo"]["kind"] == "call" and len(page["demo"]["items"]) == 4
    assert page["agent"]["steps"] == ["Felveszi", "Rögzíti", "Elküldi"]
    assert page["roi"] == {"hours_per_month": 25, "hourly_rate_huf": 7000,
                           "assumptions": ["Havi 300 hívás", "2 perc hívásonként"]}
    assert page["ui"] == demopage.HU_UI and page["contact_email"] == "aximbra@gmail.com"
    # Elérhetőség a kitalált példaadatban sem maradhat.
    assert "123 4567" not in json.dumps(page, ensure_ascii=False)


def test_invented_quote_is_dropped():
    a = dict(ANALYSIS, observation={"quote": "Nálunk minden vendég ingyen kap desszertet a vacsorához.",
                                    "page_url": "https://kertbisztro.hu/", "insight": "x"})
    assert build(a)[0]["observation"] is None


def test_contact_data_drops_the_whole_sentence_from_analysis_text():
    a = dict(ANALYSIS, secondary_agents=[{"id": "email", "reason": "Sok levél jön. Az info@kert.hu címre írnak."}])
    page, _ = build(a)
    assert page["secondary"][0]["reason"] == "Sok levél jön."
    # Rövidítés után nem vágunk: nem marad csonka "(pl." a szövegben.
    a = dict(ANALYSIS, secondary_agents=[{"id": "email", "reason": "Sok levél jön. A címeikre (pl. info@kert.hu) "
                                                                    "írnak. Gyorsabb lenne."}])
    assert build(a)[0]["secondary"][0]["reason"] == "Sok levél jön. Gyorsabb lenne."


def test_quote_from_menu_is_impossible():
    a = dict(ANALYSIS, observation={"quote": "Ez a menüben lévő mondat sosem lehet idézet, mert a fejlécben van.",
                                    "page_url": "https://kertbisztro.hu/", "insight": "x"})
    assert build(a)[0]["observation"] is None


def test_quote_rejected_by_the_second_check_is_dropped():
    page, _ = build(content=dict(CONTENT, quote_check={"full_sentence": False, "has_verb": True}))
    assert page["observation"] is None


def test_support_without_evidence_is_rechosen():
    first = dict(ANALYSIS, main_agent={"id": "support", "reason": "r", "what_it_does": "w"},
                 support_evidence={"quote": "Ügyfélszolgálatunk 0-24 elérhető", "page_url": ""})
    second = dict(ANALYSIS, main_agent={"id": "email", "reason": "r", "what_it_does": "w"})
    page, seen = build(analyses=[first, second])
    assert page["agent"]["id"] == "email"
    assert "must NOT be the main agent" in seen[1]


def test_support_twice_falls_back_to_a_secondary_agent():
    sup = dict(ANALYSIS, main_agent={"id": "support", "reason": "r", "what_it_does": "w"})
    page, _ = build(analyses=[sup, sup])
    assert page["agent"]["id"] == "email" and "support" not in [s["id"] for s in page["secondary"]]


def test_support_with_evidence_is_kept():
    a = dict(ANALYSIS, main_agent={"id": "support", "reason": "r", "what_it_does": "w"},
             support_evidence={"quote": "telefonon fogadunk", "page_url": ""})
    content = dict(CONTENT, demo={"title": "t", "intro": "i", "items": [{"title": "a", "body": "b", "output": "c"}] * 3})
    assert build(a, content=content)[0]["agent"]["id"] == "support"


def test_saved_decision_wins():
    page, seen = build(decision={"main": "lead", "extras": ["docs", "lead", "rossz"]})
    assert page["agent"]["id"] == "lead" and [e["id"] for e in page["secondary"]] == ["docs"]
    assert page["agent"]["reason"] == ""  # a modell indoklása másik agentre szólt
    assert "ALREADY DECIDED" in seen[0]


def test_other_language_gets_translated_ui_and_names():
    content = dict(CONTENT, ui={"cta": "Schreiben Sie uns", "title": "Was ein KI-Agent bei Kert Bisztró tun würde"},
                   agent_names={"phone": "KI-Telefonrezeption"}, price_text="Preis: nach Angebot", lead_text="nach Angebot")
    page, seen = build(lang="de", content=content)
    assert page["lang"] == "de" and "UI_SOURCE" in seen[1]
    assert page["ui"]["cta"] == "Schreiben Sie uns" and page["ui"]["months"] == "months"
    assert page["title"] == "Was ein KI-Agent bei Kert Bisztró tun würde"
    assert page["agent"]["name"] == "KI-Telefonrezeption" and page["agent"]["price_text"] == "nach Angebot"


def test_invalid_answer_is_sent_back_once_for_correction():
    page, seen = build(analyses=["nem json", ANALYSIS])
    assert page["agent"]["id"] == "phone" and "previous answer was invalid" in seen[1]


def test_garbage_analysis_raises_instead_of_generic_page():
    with pytest.raises(demopage.ModelError):
        build(analyses=["nem json", "megint nem"])


def test_garbage_content_for_a_read_site_raises():
    with pytest.raises(demopage.ModelError):
        build(contents=["{}", "{}"])


def test_model_outage_propagates():
    def ask(prompt):
        raise llm.LLMError("insufficient_quota")
    with pytest.raises(llm.LLMError):
        demopage.build_page("kertbisztro.hu", ask=ask, extract_json=llm.extract_json, fetcher=FakeFetcher())


def test_unreachable_site_gives_generic_page_without_claims():
    page, seen = build(site={}, company="Kert Bisztró")
    assert page["generic"] and page["observation"] is None and page["company"] == "Kert Bisztró"
    assert len(seen) == 1 and "NO website could be read" in seen[0]
    assert page["footer"].startswith("Ez a bemutató a Kert Bisztró számára készült")


def test_generic_page_falls_back_to_fixed_content_when_the_model_fails():
    page, _ = build(site={}, company="Kert Bisztró", contents=["{}", "{}"])
    assert page["generic"] and page["agent"]["id"] == "email" and page["demo"]["kind"] == "inbox"
    assert page["demo"]["items"][0]["title"] == "Árajánlatot kérnék"


def test_javascript_only_site_gives_generic_page():
    site = {"https://kertbisztro.hu/": '<html lang="de"><body><div id="root"></div><script>app()</script></body></html>'}
    page, seen = build(site=site)
    assert page["generic"] and page["lang"] == "de" and "NO website could be read" in seen[0]


def test_internal_address_refused():
    with pytest.raises(demopage.DemoError):
        demopage.build_page("http://10.0.0.5/", ask=None, extract_json=None, fetcher=FakeFetcher())


def test_slug_is_ascii_and_unique():
    a, b = demopage.make_slug("Kert Bisztró & Társa Kft.", "x.hu"), demopage.make_slug("Kert Bisztró", "x.hu")
    assert a.startswith("kert-bisztro-tarsa-kft-") and a.isascii() and a != b


# ---- tárolás ------------------------------------------------------------------

def _page():
    page, _ = build()
    return page


def test_first_open_and_first_cta_reported_once(tmp_path):
    s = Store(str(tmp_path / "d.db"))
    s.demo_add("kert-1", _page(), None, demopage.expires_at())
    assert s.demo_event("kert-1", "open") == "first_open"
    assert s.demo_event("kert-1", "open") is None
    assert s.demo_event("kert-1", "demo") is None
    assert s.demo_event("kert-1", "cta") == "first_cta"
    assert s.demo_event("kert-1", "cta") is None
    row = s.demo_list()[0]
    assert (row["opens"], row["demo_clicks"], row["cta_clicks"]) == (2, 1, 2)


def test_expired_page_is_gone(tmp_path):
    s = Store(str(tmp_path / "d.db"))
    old = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    s.demo_add("regi-1", _page(), None, old)
    assert s.demo_get("regi-1") is None and s.demo_by_domain("kertbisztro.hu") is None
    assert s.demo_list() == []


def test_decision_roundtrip(tmp_path):
    s = Store(str(tmp_path / "d.db"))
    assert s.demo_decision("x.hu") is None
    s.demo_decide("x.hu", "lead", ["docs"])
    s.demo_decide("x.hu", "email", [])
    assert s.demo_decision("x.hu") == {"main": "email", "extras": []}
    s.demo_forget("x.hu")
    assert s.demo_decision("x.hu") is None


# ---- API ----------------------------------------------------------------------

PW = ("x", "helyes-jelszo-123")


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", PW[1])
    import store as store_mod
    importlib.reload(store_mod)
    import app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    calls = []

    def gen(url, **kw):
        calls.append(kw)
        if "hibas" in url:
            raise llm.LLMError("insufficient_quota")
        if "zagyva" in url:
            raise demopage.ModelError("rossz válasz")
        return _page()
    monkeypatch.setattr(app_mod.demopage, "generate", gen)
    notified = []
    monkeypatch.setattr(app_mod, "_demo_notify", lambda row, ev: notified.append(ev))
    return TestClient(app_mod.app), app_mod, calls, notified


def test_demo_api_create_reuse_public_and_events(api):
    c, app_mod, calls, notified = api
    assert c.post("/api/demo-pages", json={"url": "kertbisztro.hu"}).status_code == 401
    r = c.post("/api/demo-pages", json={"url": "kertbisztro.hu"}, auth=PW)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["page_url"].startswith("https://aximbra.hu/neked/") and not body["existing"]
    assert body["observation"] == GOOD_QUOTE
    # Ugyanarra a domainre nem készül második oldal, és nincs új modellhívás.
    again = c.post("/api/demo-pages", json={"url": "https://www.kertbisztro.hu/"}, auth=PW).json()
    assert again["slug"] == body["slug"] and again["existing"] and len(calls) == 1
    # A döntés elmentve: újragenerálásnál ugyanazt az agentet kapja.
    assert app_mod.store.demo_decision("kertbisztro.hu")["main"] == "phone"
    c.post(f"/api/demo-pages/{body['slug']}/regenerate", auth=PW)
    assert calls[-1]["decision"]["main"] == "phone"
    c.post(f"/api/demo-pages/{body['slug']}/regenerate?rechoose=true", auth=PW)
    assert calls[-1]["decision"] is None

    pub = c.get(f"/public/neked/{body['slug']}")
    assert pub.status_code == 200 and "noindex" in pub.headers["x-robots-tag"]
    assert pub.headers["cache-control"] == "no-store"
    data = pub.json()
    assert data["company"] == "Kert Bisztró" and "lead_id" not in data and "opens" not in data
    assert c.get("/public/neked/nincs-ilyen").status_code == 404

    assert c.post(f"/public/neked/{body['slug']}/event", json={"type": "hack"}).status_code == 400
    for _ in range(2):
        assert c.post(f"/public/neked/{body['slug']}/event", json={"type": "open"}).status_code == 200
    c.post(f"/public/neked/{body['slug']}/event", json={"type": "cta"})
    import time
    time.sleep(0.2)
    assert notified == ["first_open", "first_cta"]
    listed = c.get("/api/demo-pages", auth=PW).json()["pages"][0]
    assert listed["opens"] == 2 and listed["cta_clicks"] == 1

    assert c.delete(f"/api/demo-pages/{body['slug']}", auth=PW).json() == {"ok": True}
    assert c.get(f"/public/neked/{body['slug']}").status_code == 404


def test_demo_api_errors_do_not_save(api):
    c, app_mod, _, _ = api
    assert c.post("/api/demo-pages", json={"url": "hibas.hu"}, auth=PW).status_code == 503
    assert c.post("/api/demo-pages", json={"url": "zagyva.hu"}, auth=PW).status_code == 503
    assert c.post("/api/demo-pages", json={"url": "nem url"}, auth=PW).status_code == 400
    assert app_mod.store.demo_list() == []


def test_demo_for_lead_uses_lead_site(api):
    c, app_mod, calls, _ = api
    assert c.post("/api/leads/999/demo-page", auth=PW).status_code == 404


def test_cors_only_for_aximbra(api):
    c, *_ = api
    ok = c.options("/public/neked/x", headers={"Origin": "https://aximbra.hu",
                                               "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "https://aximbra.hu"
    bad = c.options("/public/neked/x", headers={"Origin": "https://gonosz.example",
                                                "Access-Control-Request-Method": "GET"})
    assert bad.headers.get("access-control-allow-origin") is None


def test_auth_rate_limit_not_bypassed_by_forged_forwarded_for(api, monkeypatch):
    c, app_mod, _, _ = api
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)
    for i in range(5):
        r = c.get("/api/demo-pages", auth=("x", "rossz"), headers={"X-Forwarded-For": f"1.2.3.{i}, 9.9.9.9"})
        assert r.status_code == 401
    r = c.get("/api/demo-pages", auth=PW, headers={"X-Forwarded-For": "5.5.5.5, 9.9.9.9"})
    assert r.status_code == 429
    # Másik valódi IP nem szenved miatta.
    assert c.get("/api/demo-pages", auth=PW, headers={"X-Forwarded-For": "8.8.4.4"}).status_code == 200


def test_event_rate_limit(api):
    c, *_ = api
    codes = [c.post("/public/neked/nincs/event", json={"type": "open"}).status_code for _ in range(121)]
    assert codes[:120] == [404] * 120 and codes[120] == 429


# ---- utánkövetés --------------------------------------------------------------

def test_followup_with_demo_leads_with_the_page_in_every_language():
    import pipeline
    from playbook import FOLLOW_UP, FOLLOW_UP_DEMO
    assert set(FOLLOW_UP) <= set(FOLLOW_UP_DEMO)
    for lang in FOLLOW_UP_DEMO:
        body = pipeline.followup_body({"lang": lang}, "https://aximbra.hu/neked/kert-1")
        assert body.count("https://aximbra.hu/neked/kert-1") == 1
        assert "AXIMBRA" in body.rsplit("\n\n", 1)[1]           # aláírással zárul
        assert body.index("aximbra.hu/neked/") < len(body) // 2   # a link elöl van, nem a végén
    hu = pipeline.followup_body({"lang": "hu"}, "https://aximbra.hu/neked/kert-1")
    assert "elsikkadt" not in hu and hu.startswith("Jó napot!\n\nAz előző levelem óta")
    sk, hu2 = pipeline.followup_body({"lang": "hu", "lang2": "sk"}, "https://aximbra.hu/neked/x").split("— — —")
    assert sk.startswith("Dobrý deň") and "Jó napot" in hu2
    assert "neked" not in pipeline.followup_body({"lang": "en"})


def test_morning_followup_gets_demo_link_but_generic_page_does_not(api, monkeypatch):
    c, app_mod, calls, _ = api
    import pipeline
    s = app_mod.store
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    ids = []
    for dom in ("kertbisztro.hu", "zarva.hu"):
        lid = s.add_lead({"company": dom, "country": "HU", "website": f"https://{dom}", "email": f"info@{dom}",
                          "lang": "hu", "pain": "inbox", "subject": "Tárgy", "body": "b"})
        s.mark_sent_manual(lid)
        with s._conn() as conn:
            conn.execute("UPDATE leads SET sent_at = ? WHERE id = ?", (old, lid))
        ids.append(lid)

    def gen(url, **kw):
        calls.append(kw)
        page = _page()
        if "zarva" in url:
            page = dict(page, generic=True, domain="zarva.hu", url=url)
        return page
    monkeypatch.setattr(app_mod.demopage, "generate", gen)
    n = pipeline.prepare_followups(s, demo_url=app_mod._followup_demo_url(create=True))
    assert n == 2
    kert, zarva = (s.get(i) for i in ids)
    assert "aximbra.hu/neked/" in kert["followup_body"]
    assert "neked" not in zarva["followup_body"]


def test_new_drafts_get_their_demo_page_and_the_panel_shows_it(api):
    c, app_mod, calls, _ = api
    st = app_mod.store
    old = st.add_lead({"company": "Régi", "country": "HU", "lang": "hu", "email": "info@regi.hu",
                       "website": "https://regi.hu", "pain": "phone", "subject": "s", "body": "b"})
    before = {l["id"] for l in st.list("draft")}
    new = st.add_lead({"company": "Kert Bisztró", "country": "HU", "lang": "hu", "email": "info@kertbisztro.hu",
                       "website": "https://www.kertbisztro.hu", "pain": "phone", "subject": "s", "body": "b"})
    app_mod._draft_demos(before, app_mod.pipeline.RunLog())
    assert len(calls) == 1  # a régi vázlathoz nem készül
    leads = {l["id"]: l for l in c.get("/api/state", auth=PW).json()["leads"]}
    assert leads[new]["demo_url"].startswith("https://aximbra.hu/neked/")
    assert leads[old]["demo_url"] is None


def test_research_queries_spread_across_given_towns():
    import playbook
    p = playbook.queries_prompt("HU", ["logistics", "healthcare"], 2, ["Győr", "Pécs"])
    assert "Győr, Pécs" in p and "each town at most once" in p
    assert all(t for t in playbook.TOWNS) and set(playbook.TOWNS) == set(playbook.COUNTRIES)

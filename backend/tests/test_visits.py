"""A latogatasszamlalo.

Ket dolgot orzunk itt, es mindketto azert van, mert egy szamlalo csak akkor
er valamit, ha meg lehet bizni benne:

  - NEM gyujt szemelyes adatot. Ha egyszer IP vagy teljes hivatkozo URL
    kerulne bele, az sutibannert es adatkezelesi kotelezettseget hozna
    magaval - eppen azt, ami miatt nem kulso szolgaltatot tettunk be.
  - NEM all utban. Egy elszallo szamlalas nem ronthat el egy oldalbetoltest.
"""
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

visits = importlib.import_module("visits")

app = FastAPI()
app.include_router(visits.router)
c = TestClient(app)


def _reset():
    visits._paths.clear()
    visits._refs.clear()


def test_a_hit_is_counted():
    _reset()
    assert c.post("/api/hit", json={"path": "/", "lang": "hu"}).status_code == 204
    body = c.get("/api/visits").json()
    assert body["napok"][0]["osszesen"] == 1
    assert body["napok"][0]["utvonalak"]["/"] == 1


def test_only_the_referrer_host_is_kept():
    """A teljes URL tobbet arulna el a latogatorol, mint amennyi ehhez kell."""
    _reset()
    c.post("/api/hit", json={"path": "/", "ref": "https://www.google.com/search?q=titkos+kereses"})
    honnan = c.get("/api/visits").json()["napok"][0]["honnan"]
    assert honnan == {"www.google.com": 1}
    assert not any("titkos" in k for k in honnan), "a keresokifejezes nem kerulhet be"


def test_our_own_pages_are_not_counted_as_a_source():
    _reset()
    c.post("/api/hit", json={"path": "/weboldal", "ref": "https://aximbra.hu/"})
    assert c.get("/api/visits").json()["napok"][0]["honnan"] == {"sajat": 1}


def test_no_referrer_is_a_direct_visit():
    _reset()
    c.post("/api/hit", json={"path": "/"})
    assert c.get("/api/visits").json()["napok"][0]["honnan"] == {"kozvetlen": 1}


def test_a_foreign_path_cannot_be_smuggled_in():
    """Egy nyitott szamlalo elobb-utobb idegen adatot gyujt, es akkor a sajat
    szamaidban sem bizhatsz."""
    _reset()
    # A hosszu valtozat kulon tanulsag: puszta csonkolas utan egy
    # `/x/x/x/...` szabalyosnak latszott, es bekerult a szamlaloba.
    for bad in ("https://masik-oldal.hu/valami", "/../etc/passwd", "/x" * 500,
                "<script>", "/a/b/c/d/e", "/" + "h" * 40):
        c.post("/api/hit", json={"path": bad})
    utak = c.get("/api/visits").json()["napok"][0]["utvonalak"]
    assert set(utak) == {"/egyeb"}, utak


def test_the_query_string_is_dropped():
    """Egy `?email=...` paraméter szemelyes adat lenne. Az utvonal eleg."""
    _reset()
    c.post("/api/hit", json={"path": "/demo/email-agent?s=titkos-token"})
    assert list(c.get("/api/visits").json()["napok"][0]["utvonalak"]) == ["/demo/email-agent"]


def test_a_broken_counter_never_breaks_the_page(monkeypatch):
    """Ha a szamlalas elszall, a latogato akkor sem lat hibat."""
    _reset()

    def boom(*a, **kw):
        raise RuntimeError("a szamlalo elszallt")

    monkeypatch.setattr(visits, "_today", boom)
    assert c.post("/api/hit", json={"path": "/"}).status_code == 204

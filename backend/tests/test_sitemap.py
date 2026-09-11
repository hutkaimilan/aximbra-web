"""A sitemap egyezzen azzal, amit az útvonaltábla mond.

Egy kézzel vezetett sitemap csendben avul: az új oldal kimarad, a törölt
bennmarad. A generátor a forrás; ez a teszt csak azt őrzi, hogy a kimenete és
a kiszolgált fájl ne csússzon szét — és hogy a fájl érvényes XML maradjon
(a saját fejlécem egyszer épp azon bukott el, hogy XML-kommentben nem lehet
két kötőjel egymás mellett).
"""
import importlib.util
import pathlib
import xml.etree.ElementTree as ET

REPO = pathlib.Path(__file__).resolve().parents[2]
SITEMAP = REPO / "frontend" / "public" / "sitemap.xml"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _generator():
    spec = importlib.util.spec_from_file_location("sitemap_gen", REPO / "tools" / "sitemap" / "generate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_file_matches_the_route_table():
    assert SITEMAP.read_text(encoding="utf-8") == _generator().build(), (
        "A sitemap.xml elavult. Futtasd: python3 tools/sitemap/generate.py --write"
    )


def test_is_valid_xml_and_every_url_is_absolute():
    root = ET.parse(SITEMAP).getroot()
    locs = [u.find("s:loc", NS).text for u in root]
    assert locs, "üres sitemap"
    assert all(l.startswith("https://aximbra.hu") for l in locs)
    assert len(locs) == len(set(locs)), "ismétlődő URL"


def test_no_demo_pages_are_listed():
    """A referencia-demók futásidőben noindex-ek; a sitemapban sincs helyük."""
    root = ET.parse(SITEMAP).getroot()
    demos = [u.find("s:loc", NS).text for u in root if "/demo/" in u.find("s:loc", NS).text]
    assert demos == ["https://aximbra.hu/demo/email-agent"], demos

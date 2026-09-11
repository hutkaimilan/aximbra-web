#!/usr/bin/env python3
"""A sitemap.xml előállítása az útvonaltáblából.

Kézzel vezetve az a hiba, ami nem látszik: az új oldal kimarad, a törölt
bennmarad, és a kereső egy olyan térképet kap, ami mást állít, mint a lapon
lévő canonical. A forrás itt van, egy helyen, az App.js útvonalai mellett.

Futtatás a repó gyökeréből:

    python3 tools/sitemap/generate.py            # ellenőrzés (eltérésnél 1)
    python3 tools/sitemap/generate.py --write    # felülírja a fájlt
"""
import pathlib
import sys

BASE = "https://aximbra.hu"
DEFAULT_LANG = "hu"
LANGS = ["hu", "en", "de", "es", "fr", "it", "ro", "sk"]
OUT = pathlib.Path("frontend/public/sitemap.xml")

# (útvonal, lefordított?, changefreq, priority)
# „lefordított" = a lap szövege minden nyelven létezik, tehát nyelvenként külön
# URL-je van, és a nyolc változat egymás alternatívája. Ami csak magyarul van
# (jogi oldalak, az e-mail agent lapja), az egyetlen URL — különben a sitemap
# olyan fordítást ígérne, ami nincs.
ROUTES = [
    ("/", True, "weekly", "1.0"),
    ("/weboldal", True, "monthly", "0.7"),
    ("/demo/email-agent", False, "monthly", "0.8"),
    ("/impresszum", False, "yearly", "0.3"),
    ("/adatkezeles", False, "yearly", "0.3"),
]

HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERALT FAJL. Ne kezzel szerkeszd: python3 tools/sitemap/generate.py (a "write" kapcsoloval)
     A /demo/ referenciaoldalak szandekosan hianyoznak: kitalalt vallalkozasokat
     mutatnak es futasidoben noindex-ek.
     Csak a lefordított oldalak szerepelnek minden nyelven. Amelyiknek a szovege
     csak magyarul letezik (agent, jogi oldalak), az egyetlen URL-lel szerepel -
     kulonben a sitemap mast allitana, mint a lapon levo canonical. -->
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
"""


def url_for(lang: str, path: str) -> str:
    if lang == DEFAULT_LANG:
        return BASE + path
    return f"{BASE}/{lang}" if path == "/" else f"{BASE}/{lang}{path}"


def build() -> str:
    out = [HEADER]
    for path, translated, freq, prio in ROUTES:
        langs = LANGS if translated else [DEFAULT_LANG]
        for lang in langs:
            out.append("  <url>\n")
            out.append(f"    <loc>{url_for(lang, path)}</loc>\n")
            if translated:
                for alt in LANGS:
                    out.append(f'    <xhtml:link rel="alternate" hreflang="{alt}" href="{url_for(alt, path)}"/>\n')
                out.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{url_for(DEFAULT_LANG, path)}"/>\n')
            out.append(f"    <changefreq>{freq}</changefreq><priority>{prio}</priority>\n")
            out.append("  </url>\n")
    out.append("</urlset>\n")
    return "".join(out)


def main() -> int:
    xml = build()
    if "--write" in sys.argv:
        OUT.write_text(xml, encoding="utf-8")
        print(f"{OUT}: {xml.count('<url>')} URL")
        return 0
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if current != xml:
        print("A sitemap.xml eltér attól, amit az útvonaltábla ad. Futtasd: --write")
        return 1
    print(f"rendben, {xml.count('<url>')} URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

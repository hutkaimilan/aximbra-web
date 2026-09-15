#!/usr/bin/env python3
"""Az aximbra.hu apex rekordjának átállítása A-ról CNAME-re, Cloudflare API-n.

Miért van erre szükség. A Railway a saját él-IP-jét nem garantálja állandónak,
és az egyedi domainhez CNAME-et vár — A-rekordot nem támogat. Amíg az apexen
A-rekord áll, a tanúsítvány nem áll ki, és ha a Railway lecseréli az IP-t, az
oldal némán elérhetetlenné válik.

Ez a szkript abból a környezetből NEM futtatható, ahol készült: ott a
szervezeti egress-szabály tiltja az api.cloudflare.com elérését. A saját
gépeden viszont lefut.

    # 1. Token: https://dash.cloudflare.com/profile/api-tokens
    #    Sablon: "Edit zone DNS" — Zone:DNS:Edit az aximbra.hu zónára.
    export CF_API_TOKEN="..."

    python3 tools/dns/fix-apex.py            # megmutatja, mit tenne
    python3 tools/dns/fix-apex.py --apply    # meg is csinálja

Alapból semmit nem ír, csak kiírja a tervet. Az `--apply` sem töröl vakon:
előbb létrehozza a CNAME-et, és csak utána szedi ki az A-rekordot, hogy a név
egy pillanatra se maradjon rekord nélkül.
"""
import json
import os
import sys
import urllib.error
import urllib.request

ZONE = os.environ.get("CF_ZONE", "aximbra.hu")
TARGET = os.environ.get("RAILWAY_TARGET", "yaufvlw4.up.railway.app")
API = "https://api.cloudflare.com/client/v4"
APPLY = "--apply" in sys.argv


def call(method, path, body=None):
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not token:
        sys.exit("Hiányzik a CF_API_TOKEN. Lásd a fájl tetején a leírást.")
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        sys.exit(f"Cloudflare {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Nem sikerült elérni a Cloudflare-t: {e.reason}")
    if not payload.get("success"):
        sys.exit("Cloudflare hiba: " + json.dumps(payload.get("errors"), ensure_ascii=False))
    return payload["result"]


def main():
    zones = call("GET", f"/zones?name={ZONE}")
    if not zones:
        sys.exit(f"Nincs ilyen zóna a fiókban: {ZONE}")
    zone_id = zones[0]["id"]
    print(f"zóna: {ZONE}  ({zone_id})")

    records = call("GET", f"/zones/{zone_id}/dns_records?name={ZONE}")
    a_records = [r for r in records if r["type"] in ("A", "AAAA")]
    cnames = [r for r in records if r["type"] == "CNAME"]

    for r in records:
        proxy = "proxyzott" if r.get("proxied") else "DNS-only"
        print(f"  most: {r['type']:6} {r['name']} → {r['content']}  ({proxy})")

    if cnames and cnames[0]["content"].rstrip(".") == TARGET and not cnames[0].get("proxied"):
        print("\nMár jó: az apexen DNS-only CNAME áll a Railway célpontjára. Nincs teendő.")
        return

    print("\nTerv:")
    print(f"  1. LÉTREHOZ  CNAME {ZONE} → {TARGET}   (DNS-only, szürke felhő)")
    for r in a_records:
        print(f"  2. TÖRÖL     {r['type']} {r['name']} → {r['content']}")

    if not APPLY:
        print("\n(Próbafutás. Futtasd újra --apply kapcsolóval, ha ez így jó.)")
        return

    # Előbb a CNAME, csak utána a törlés: a név egy pillanatra se maradjon üresen.
    # A Cloudflare nem enged A-t és CNAME-et ugyanarra a névre, ezért ha ütközik,
    # a meglévő A-rekordot írjuk át CNAME-re egy lépésben.
    body = {"type": "CNAME", "name": ZONE, "content": TARGET, "proxied": False, "ttl": 1}
    if a_records:
        first = a_records[0]
        print(f"\n  átírás: {first['type']} → CNAME ({first['id']})")
        call("PUT", f"/zones/{zone_id}/dns_records/{first['id']}", body)
        for extra in a_records[1:]:
            print(f"  törlés: {extra['type']} {extra['content']} ({extra['id']})")
            call("DELETE", f"/zones/{zone_id}/dns_records/{extra['id']}")
    else:
        print("\n  létrehozás: CNAME")
        call("POST", f"/zones/{zone_id}/dns_records", body)

    print("\nKész. Ellenőrzés:")
    for r in call("GET", f"/zones/{zone_id}/dns_records?name={ZONE}"):
        proxy = "proxyzott" if r.get("proxied") else "DNS-only"
        print(f"  {r['type']:6} {r['name']} → {r['content']}  ({proxy})")
    print("\nInnentől a Railway tanúsítványa percek-órák alatt kiáll.")
    print("Ellenőrizd: python3 tools/dns/query.py aximbra.hu CNAME A")


if __name__ == "__main__":
    main()

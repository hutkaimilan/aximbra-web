#!/usr/bin/env python3
"""Cloudflare DNS-vezérlő az aximbra.hu zónához.

Miért van erre szükség ebben a formában. A fejlesztői futtatókörnyezetből az
api.cloudflare.com elérése szervezeti szabályból tiltott, tehát onnan DNS-t
állítani nem lehet. A GitHub Actions futtatója viszont eléri, és a tokent a
repó titkaként tárolja — így a DNS-műveletek naplózottan, egy helyen, kézi
kattintgatás nélkül futnak.

    python3 tools/dns/cf.py show
    python3 tools/dns/cf.py proxy www off
    python3 tools/dns/cf.py proxy @ off
    python3 tools/dns/cf.py set CNAME www t44uikmi.up.railway.app
    python3 tools/dns/cf.py set TXT _railway-verify.www "railway-verify=..."
    python3 tools/dns/cf.py delete A @

A `@` az apexet jelenti. Az írásnak `--apply` kell; enélkül csak kiírja, mit
tenne. A token a CF_API_TOKEN környezeti változóból jön, és sosem íródik ki.
"""
import json
import os
import sys
import urllib.error
import urllib.request

ZONE = os.environ.get("CF_ZONE", "aximbra.hu")
API = "https://api.cloudflare.com/client/v4"


def fail(msg):
    print(f"HIBA: {msg}", file=sys.stderr)
    raise SystemExit(1)


def call(method, path, body=None):
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not token:
        fail("nincs CF_API_TOKEN (GitHub Actionsben: repository secret)")
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        fail(f"Cloudflare {e.code}: {e.read().decode('utf-8', 'replace')[:600]}")
    except urllib.error.URLError as e:
        fail(f"nem érhető el a Cloudflare: {e.reason}")
    if not payload.get("success"):
        fail("Cloudflare: " + json.dumps(payload.get("errors"), ensure_ascii=False))
    return payload["result"]


def zone_id():
    zones = call("GET", f"/zones?name={ZONE}")
    if not zones:
        fail(f"a token nem lát rá erre a zónára: {ZONE}")
    return zones[0]["id"]


def fqdn(name):
    if name in ("@", "", ZONE):
        return ZONE
    return name if name.endswith(ZONE) else f"{name}.{ZONE}"


def records(zid, name=None):
    path = f"/zones/{zid}/dns_records?per_page=200"
    if name:
        path += f"&name={fqdn(name)}"
    return call("GET", path)


def line(r):
    proxy = "proxyzott 🟠" if r.get("proxied") else "DNS-only ⚪"
    content = r["content"]
    if len(content) > 72:
        content = content[:69] + "…"
    return f"  {r['type']:6} {r['name']:34} {content:74} {proxy}"


def cmd_show(zid, args):
    rs = records(zid, args[0] if args else None)
    if not rs:
        print("  (nincs ilyen rekord)")
        return
    for r in sorted(rs, key=lambda x: (x["name"], x["type"])):
        print(line(r))


def cmd_proxy(zid, args, apply_):
    if len(args) != 2 or args[1] not in ("on", "off"):
        fail("használat: proxy <név> on|off")
    name, want = fqdn(args[0]), args[1] == "on"
    hits = [r for r in records(zid, name) if r["type"] in ("A", "AAAA", "CNAME")]
    if not hits:
        fail(f"nincs proxyzható rekord ezen a néven: {name}")
    for r in hits:
        if r.get("proxied") == want:
            print(f"  változatlan: {r['type']} {r['name']} már {'proxyzott' if want else 'DNS-only'}")
            continue
        print(f"  {'ÍRÁS' if apply_ else 'TERV'}: {r['type']} {r['name']} → proxied={want}")
        if apply_:
            call("PATCH", f"/zones/{zid}/dns_records/{r['id']}", {"proxied": want})


def cmd_set(zid, args, apply_):
    if len(args) < 3:
        fail("használat: set <TYPE> <név> <érték> [--proxied]")
    rtype, name, content = args[0].upper(), fqdn(args[1]), args[2]
    proxied = "--proxied" in args and rtype in ("A", "AAAA", "CNAME")
    body = {"type": rtype, "name": name, "content": content, "ttl": 1}
    if rtype in ("A", "AAAA", "CNAME"):
        body["proxied"] = proxied
    same = [r for r in records(zid, name) if r["type"] == rtype]
    # A Cloudflare nem enged A-t és CNAME-et ugyanarra a névre, ezért ha
    # ütköző címrekord van, azt írjuk át — így a név egy pillanatra sem marad
    # rekord nélkül.
    clash = [r for r in records(zid, name)
             if rtype == "CNAME" and r["type"] in ("A", "AAAA")]
    target = (same or clash)
    if target:
        r = target[0]
        print(f"  {'ÍRÁS' if apply_ else 'TERV'}: átírás {r['type']} → {rtype} {name} = {content[:60]}")
        if apply_:
            call("PUT", f"/zones/{zid}/dns_records/{r['id']}", body)
        for extra in target[1:]:
            print(f"  {'ÍRÁS' if apply_ else 'TERV'}: törlés {extra['type']} {extra['name']}")
            if apply_:
                call("DELETE", f"/zones/{zid}/dns_records/{extra['id']}")
    else:
        print(f"  {'ÍRÁS' if apply_ else 'TERV'}: létrehozás {rtype} {name} = {content[:60]}")
        if apply_:
            call("POST", f"/zones/{zid}/dns_records", body)


def cmd_delete(zid, args, apply_):
    if len(args) != 2:
        fail("használat: delete <TYPE> <név>")
    rtype, name = args[0].upper(), fqdn(args[1])
    hits = [r for r in records(zid, name) if r["type"] == rtype]
    if not hits:
        print("  (nincs mit törölni)")
        return
    for r in hits:
        print(f"  {'ÍRÁS' if apply_ else 'TERV'}: törlés {r['type']} {r['name']} → {r['content'][:50]}")
        if apply_:
            call("DELETE", f"/zones/{zid}/dns_records/{r['id']}")


def main():
    argv = [a for a in sys.argv[1:] if a != "--apply"]
    apply_ = "--apply" in sys.argv
    if not argv:
        print(__doc__)
        raise SystemExit(2)
    cmd, args = argv[0], argv[1:]
    zid = zone_id()
    print(f"zóna: {ZONE}")
    if cmd == "show":
        cmd_show(zid, args)
    elif cmd == "proxy":
        cmd_proxy(zid, args, apply_)
    elif cmd == "set":
        cmd_set(zid, args, apply_)
    elif cmd == "delete":
        cmd_delete(zid, args, apply_)
    else:
        fail(f"ismeretlen parancs: {cmd}")
    if not apply_ and cmd != "show":
        print("\n(próbafutás — az íráshoz --apply kell)")
    else:
        print("\nutána:")
        cmd_show(zid, None)


if __name__ == "__main__":
    main()

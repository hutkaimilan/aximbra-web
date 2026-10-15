"""Megosztott iCloud-album behúzása a tárba, linkből — a telefon kihagyásával.

Miért kell: az iPhone böngészője a fotóválasztóból kijelölt elemeket egyenként
készíti elő, és ha EGY is elakad (tipikusan egy videó, aminek az eredetije még
az iCloudban van), az egész kijelölést eldobja — az oldal semmit nem kap
(WebKit, WKFileUploadPanel: _processPickerResults → failureBlock → _cancel).
22 elemnél ez rendszeresen megtörtént. Itt a telefon semmit nem készít elő: a
Fotók appban létrehozott megosztott album nyilvános linkjéből a szerver tölti
le az elemeket, egyenként, és ami nem jön le, azt kihagyja.

Az Apple nyilvános albumoldala (www.icloud.com/sharedalbum/#<token>) a
„sharedstreams" végpontokat használja; nem hivatalos API, de évek óta ugyanaz:

  POST https://p<N>-sharedstreams.icloud.com/<token>/sharedstreams/webstream
      → 330 esetén a válasz megadja a helyes gépet (X-Apple-MMe-Host)
  POST .../webasseturls {"photoGuids": [...]} → letöltési címek checksum szerint
"""
from __future__ import annotations

import logging
import os
import re

import httpx

import library

logger = logging.getLogger("reels.icloud")

TOKEN_RE = re.compile(r"sharedalbum/?#?([A-Za-z0-9]{10,})")
FIRST_HOST = "p23-sharedstreams.icloud.com"
URL_BATCH = 25
MAX_ITEMS = int(os.environ.get("ALBUM_MAX_ITEMS", "300"))
HEADERS = {"User-Agent": "Mozilla/5.0 (AximbraReels)", "Origin": "https://www.icloud.com"}
# Egy-egy elem letöltése: nagy videónál lassú lehet, de nem végtelen.
ITEM_TIMEOUT = httpx.Timeout(connect=20.0, read=180.0, write=60.0, pool=20.0)


class AlbumError(RuntimeError):
    pass


def token_of(url: str) -> str:
    """A link albumtokenje. Minden más linkre elmondja, mi kell helyette."""
    u = (url or "").strip()
    m = TOKEN_RE.search(u)
    if m:
        return m.group(1)
    if "icloud.com" in u or "icloud-content" in u:
        raise AlbumError("Ez nem megosztott album link. A Fotók appban: album → Személyek ikon → "
                         "„Nyilvános webhely” bekapcsolva → „Link megosztása” → Másolás. "
                         "A link így néz ki: https://www.icloud.com/sharedalbum/#B0...")
    raise AlbumError("Ismeretlen link — megosztott iCloud-album linkje kell "
                     "(https://www.icloud.com/sharedalbum/#…)")


def _post(client: httpx.Client, host: str, token: str, path: str, body: dict) -> tuple[str, dict]:
    """POST a sharedstreams végpontra; a 330-as gépváltást követi."""
    last = ""
    for _ in range(4):
        try:
            r = client.post(f"https://{host}/{token}/sharedstreams/{path}", json=body, headers=HEADERS)
        except httpx.HTTPError as e:
            last = str(e)
            continue
        if r.status_code == 330:
            nxt = (_json(r) or {}).get("X-Apple-MMe-Host")
            if not nxt or nxt == host:
                raise AlbumError("az iCloud körbe-körbe küld — próbáld újra pár perc múlva")
            host = nxt
            continue
        if r.status_code in (401, 403):
            raise AlbumError("az album nem nyilvános — kapcsold be nála a „Nyilvános webhely” kapcsolót")
        if r.status_code == 404:
            raise AlbumError("az album nem található — jó a link, és be van kapcsolva a „Nyilvános webhely”?")
        if r.status_code >= 400:
            raise AlbumError(f"az iCloud hibát adott ({r.status_code})")
        data = _json(r)
        if data is None:
            raise AlbumError("az iCloud válasza értelmezhetetlen volt")
        return host, data
    raise AlbumError(f"nem sikerült elérni az iCloudot{(' — ' + last) if last else ''}")


def _json(r: httpx.Response) -> dict | None:
    try:
        d = r.json()
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


def _best(derivatives: dict, video: bool) -> dict | None:
    """A legnagyobb változat; videónál a mozgókép, nem a borítókép."""
    items = [(k, v) for k, v in (derivatives or {}).items()
             if isinstance(v, dict) and v.get("checksum")]
    if video:
        moving = [(k, v) for k, v in items if k.lower() not in ("posterframe", "poster")]
        items = moving or items
    if not items:
        return None
    return max(items, key=lambda kv: int(kv[1].get("fileSize") or 0))[1]


def listing(url: str, client: httpx.Client | None = None) -> tuple[str, list[dict]]:
    """Az album neve és elemei letöltési címmel: [{guid, video, checksum, url, name, bytes}]."""
    token = token_of(url)
    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        host, stream = _post(client, FIRST_HOST, token, "webstream", {"streamCtag": None})
        photos = [p for p in (stream.get("photos") or []) if isinstance(p, dict)]
        # A Fotók app a legújabbat teszi a lista végére; a feltöltés sorrendje
        # legyen az albumban látott sorrend.
        items: list[dict] = []
        for p in photos[:MAX_ITEMS]:
            video = str(p.get("mediaAssetType") or "").lower() == "video"
            best = _best(p.get("derivatives") or {}, video)
            if best and p.get("photoGuid"):
                items.append({"guid": p["photoGuid"], "video": video, "checksum": best["checksum"],
                              "bytes": int(best.get("fileSize") or 0)})
        urls: dict[str, str] = {}
        for i in range(0, len(items), URL_BATCH):
            guids = [x["guid"] for x in items[i:i + URL_BATCH]]
            host, d = _post(client, host, token, "webasseturls", {"photoGuids": guids})
            for checksum, loc in (d.get("items") or {}).items():
                if isinstance(loc, dict) and loc.get("url_location") and loc.get("url_path"):
                    urls[checksum] = f"https://{loc['url_location']}{loc['url_path']}"
        for n, x in enumerate(items, 1):
            x["url"] = urls.get(x["checksum"], "")
            x["name"] = f"iCloud {n:03d}{'.mov' if x['video'] else '.jpg'}"
        name = str(stream.get("streamName") or "iCloud-album")[:60]
        return name, [x for x in items if x["url"]]
    finally:
        if own:
            client.close()


def _fetch_one(client: httpx.Client, x: dict, tag: str) -> tuple[dict, int]:
    """Egy elem letöltése fájlba (nem a memóriába), majd fel a tárba."""
    dest = os.path.join(library.scratch_dir(), f"album-{x['checksum'][:16]}")
    try:
        with client.stream("GET", x["url"], headers={"User-Agent": HEADERS["User-Agent"]}) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for block in r.iter_bytes(1024 * 1024):
                    f.write(block)
        ct = (r.headers.get("content-type") or "").split(";")[0].strip() \
            or ("video/quicktime" if x["video"] else "image/jpeg")
        size = os.path.getsize(dest)
        return library.store_file(dest, ct, x["name"], tag, source="icloud-album"), size
    finally:
        if os.path.exists(dest):
            os.remove(dest)


def run(url: str, tag: str, say=lambda m: None, client: httpx.Client | None = None) -> dict:
    """Az album minden eleme a tárba. A rossz elem nem állítja meg a többit."""
    say("iCloud-album beolvasása…")
    own = client is None
    client = client or httpx.Client(timeout=ITEM_TIMEOUT, follow_redirects=True)
    try:
        name, items = listing(url, client)
        if not items:
            raise AlbumError("az album üres, vagy egyetlen elemét sem lehet letölteni")
        total_mb = sum(x["bytes"] for x in items) / 1048576
        say(f"„{name}”: {len(items)} elem (~{total_mb:.0f} MB). Letöltés egyenként…")
        done, failed = [], []
        for i, x in enumerate(items, 1):
            try:
                m, size = _fetch_one(client, x, tag)
                done.append(m["id"])
                say(f"{i}/{len(items)} behúzva — {x['name']} ({size / 1048576:.1f} MB)")
            except Exception as e:  # noqa: BLE001 — egy rossz elem miatt nem áll le az egész
                failed.append(x["name"])
                logger.warning("albumelem kimaradt (%s): %s", x["name"], e)
                say(f"{i}/{len(items)} KIMARADT — {x['name']} ({type(e).__name__}: {str(e)[:120]})")
        say(f"Album kész: {len(done)} elem a tárban"
            + (f", {len(failed)} kimaradt ({', '.join(failed[:6])}" + ("…)" if len(failed) > 6 else ")")
               if failed else "."))
        return {"album": name, "ids": done, "failed": failed, "total": len(items)}
    finally:
        if own:
            client.close()

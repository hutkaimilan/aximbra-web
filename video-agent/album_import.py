"""Megosztott iCloud-album behúzása a médiatárba, linkből.

Miért kell: az iPhone böngészője a fotóválasztóból kijelölt elemeket egyenként
tölti be, és ha EGY is elakad (pl. egy videó, aminek az eredetije még az
iCloudban van), az egész kijelölést eldobja — az oldal semmit nem kap (WebKit,
WKFileUploadPanel: _processPickerResults → failureBlock → _cancel). Sok elemnél
ez szinte biztos. Itt a telefon semmit nem készít elő: a Fotók appban létrehozott
megosztott album nyilvános linkjéből a szerver maga tölti le a képeket és
videókat, egyenként, és ami nem jön le, azt kihagyja, a többit behúzza.

Az Apple nyilvános albumoldala (www.icloud.com/sharedalbum/#<token>) a
„sharedstreams” végpontokat használja; nem hivatalos, de évek óta ugyanaz:
  POST https://p23-sharedstreams.icloud.com/<token>/sharedstreams/webstream
    → 330 esetén a válasz megmondja a helyes gépet (X-Apple-MMe-Host)
  POST .../webasseturls {"photoGuids": [...]} → letöltési címek checksum szerint
"""
from __future__ import annotations

import logging
import re

import httpx

import media

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"sharedalbum/?#([A-Za-z0-9]{10,})")
URL_BATCH = 25
MAX_ITEMS = 200
UA = {"User-Agent": "Mozilla/5.0 (AximbraVideo)", "Content-Type": "text/plain", "Origin": "https://www.icloud.com"}


class ImportError_(RuntimeError):
    pass


def token_of(url: str) -> str:
    m = TOKEN_RE.search(url or "")
    if not m:
        if "icloud.com" in (url or "") or "share.icloud" in (url or ""):
            raise ImportError_("ez nem megosztott album link. A Fotók appban: album → Személyek ikon → "
                               "„Nyilvános webhely” bekapcsolva → „Link megosztása”.")
        raise ImportError_("ismeretlen link — megosztott iCloud-album linkje kell (www.icloud.com/sharedalbum/#…)")
    return m.group(1)


def _post(client: httpx.Client, host: str, token: str, path: str, body: dict) -> tuple[str, dict]:
    """POST a sharedstreams végpontra; a 330-as átirányítást (másik gép) követi."""
    for _ in range(3):
        r = client.post(f"https://{host}/{token}/sharedstreams/{path}", json=body, headers=UA)
        if r.status_code == 330:
            host = (r.json() or {}).get("X-Apple-MMe-Host") or host
            continue
        if r.status_code == 404:
            raise ImportError_("az album nem található — be van kapcsolva a „Nyilvános webhely”?")
        if r.status_code >= 400:
            raise ImportError_(f"az iCloud hibát adott ({r.status_code})")
        return host, r.json()
    raise ImportError_("az iCloud nem mondta meg, melyik szerveren van az album")


def _best(derivs: dict, video: bool) -> tuple[str, dict] | None:
    """A legnagyobb változat; videónál a mozgókép, nem a borítókép."""
    items = [(k, v) for k, v in (derivs or {}).items() if isinstance(v, dict) and v.get("checksum")]
    if video:
        items = [(k, v) for k, v in items if k.lower() != "posterframe"] or items
    if not items:
        return None
    return max(items, key=lambda kv: int(kv[1].get("fileSize") or 0))


def listing(url: str, client: httpx.Client | None = None) -> tuple[str, list[dict]]:
    """Az album neve és elemei: [{guid, video, checksum, url, name}] (letöltési címmel)."""
    token = token_of(url)
    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        host, stream = _post(client, "p23-sharedstreams.icloud.com", token, "webstream", {"streamCtag": None})
        photos = (stream.get("photos") or [])[:MAX_ITEMS]
        items = []
        for p in photos:
            video = str(p.get("mediaAssetType") or "").lower() == "video"
            best = _best(p.get("derivatives") or {}, video)
            if best and p.get("photoGuid"):
                items.append({"guid": p["photoGuid"], "video": video, "checksum": best[1]["checksum"]})
        urls = {}
        for i in range(0, len(items), URL_BATCH):
            _, d = _post(client, host, token, "webasseturls", {"photoGuids": [x["guid"] for x in items[i:i + URL_BATCH]]})
            for checksum, loc in (d.get("items") or {}).items():
                if isinstance(loc, dict) and loc.get("url_location") and loc.get("url_path"):
                    urls[checksum] = f"https://{loc['url_location']}{loc['url_path']}"
        for n, x in enumerate(items, 1):
            x["url"] = urls.get(x["checksum"], "")
            x["name"] = f"iCloud {n:02d}{'.mp4' if x['video'] else '.jpg'}"
        return str(stream.get("streamName") or "iCloud-album")[:60], [x for x in items if x["url"]]
    finally:
        if own:
            client.close()


def run(url: str, tag: str, say=lambda m: None, client: httpx.Client | None = None) -> list[str]:
    """Az album minden eleme a médiatárba. Visszaadja a felvett médiaazonosítókat."""
    say("iCloud-album beolvasása…")
    own = client is None
    client = client or httpx.Client(timeout=120, follow_redirects=True)
    try:
        name, items = listing(url, client)
        if not items:
            raise ImportError_("az album üres, vagy egyetlen elemét sem lehet letölteni")
        say(f"„{name}”: {len(items)} elem, letöltés egyenként…")
        done, failed = [], 0
        for i, x in enumerate(items, 1):
            try:
                r = client.get(x["url"])
                r.raise_for_status()
                if len(r.content) > media.MAX_BYTES:
                    raise media.MediaError("túl nagy")
                ct = r.headers.get("content-type", "") or ("video/mp4" if x["video"] else "image/jpeg")
                m = media.store(r.content, ct, x["name"], tag, redact_pii=False)
                done.append(m["id"])
                say(f"{i}/{len(items)} behúzva ({'videó' if x['video'] else 'kép'})")
            except Exception as e:  # noqa: BLE001 — egy rossz elem miatt nem áll le az egész
                failed += 1
                logger.warning("albumelem kimaradt: %s", e)
                say(f"{i}/{len(items)} kimaradt ({type(e).__name__})")
        say(f"Kész: {len(done)} elem a médiatárban" + (f", {failed} kimaradt." if failed else "."))
        return done
    finally:
        if own:
            client.close()

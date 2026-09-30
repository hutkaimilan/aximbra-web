"""Kiposztolás: Instagram és LinkedIn.

Három formátum megy ki: videó, egyetlen kép és képes körhinta. A két
platform másképp veszi át őket, ezért a két út különbözik:

- Instagram (Meta Graph API): mi csak nyilvános URL-eket adunk, a fájlt
  az ő szerverük tölti le. Videónál meg kell várni a feldolgozást. Ezért
  kell jelszó nélkül elérhető, kitalálhatatlan cím — ezt az app.py adja.
- LinkedIn (Posts API): a fájl bájtjait mi töltjük fel, nyilvános cím
  nélkül. A videót darabokban kéri és le kell zárni, a képet egyben.

Mindkettőhöz kulcs kell a szolgáltatás környezeti változóiban:
  IG_USER_ID, IG_ACCESS_TOKEN, PUBLIC_BASE_URL, PUBLIC_LINK_SECRET
  LI_ACCESS_TOKEN, LI_AUTHOR_URN   (urn:li:person:… vagy urn:li:organization:…)
"""
from __future__ import annotations

import logging
import os

import httpx

import stop

logger = logging.getLogger(__name__)

TARGETS = ("instagram", "linkedin")


class PublishError(RuntimeError):
    pass


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _err(body: dict, r) -> str:
    return (((body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else None)
            or body.get("message") or r.text[:200] or f"HTTP {r.status_code}")


def _json(r) -> dict:
    try:
        return r.json()
    except ValueError:
        return {}


# ---- Instagram ---------------------------------------------------------------

IG_API = "https://graph.facebook.com/v21.0"
IG_POLL_SECONDS = 10
IG_POLL_TRIES = 30


def ig_ready() -> bool:
    return bool(_env("IG_USER_ID") and _env("IG_ACCESS_TOKEN") and _env("PUBLIC_BASE_URL"))


def ig_missing() -> list[str]:
    need = {"IG_USER_ID": "Instagram fiókazonosító", "IG_ACCESS_TOKEN": "Instagram hozzáférési kulcs",
            "PUBLIC_BASE_URL": "a szolgáltatás nyilvános címe"}
    return [v for k, v in need.items() if not _env(k)]


def _ig_call(method: str, path: str, data: dict, timeout: int = 60) -> dict:
    token = _env("IG_ACCESS_TOKEN")
    if not token:
        raise PublishError("nincs beállítva az IG_ACCESS_TOKEN")
    url = f"{IG_API}/{path}"
    payload = {**data, "access_token": token}
    try:
        r = (httpx.post(url, data=payload, timeout=timeout) if method == "POST"
             else httpx.get(url, params=payload, timeout=timeout))
    except httpx.HTTPError as e:
        raise PublishError(f"az Instagram nem érhető el ({type(e).__name__})") from e
    body = _json(r)
    if r.status_code >= 400:
        raise PublishError(f"Instagram: {_err(body, r)}")
    return body


def ig_account() -> dict:
    """A bekötött fiók neve — a felületen ez mutatja, hova posztolunk."""
    return _ig_call("GET", _env("IG_USER_ID"), {"fields": "username,name"}, timeout=30)


def _ig_user() -> str:
    user = _env("IG_USER_ID")
    if not user:
        raise PublishError("nincs beállítva az IG_USER_ID")
    return user


def _ig_https(url: str) -> str:
    if not url.startswith("https://"):
        raise PublishError("a fájl címe csak https lehet")
    return url


def _ig_container(data: dict) -> str:
    out = _ig_call("POST", f"{_ig_user()}/media", data, timeout=120)
    cid = out.get("id")
    if not cid:
        raise PublishError("az Instagram nem adott feltöltési azonosítót")
    return str(cid)


def _ig_finish(cid: str) -> str:
    out = _ig_call("POST", f"{_ig_user()}/media_publish", {"creation_id": cid})
    if not out.get("id"):
        raise PublishError("a publikálás nem adott azonosítót")
    return str(out["id"])


def ig_publish_image(image_url: str, caption: str) -> str:
    """Egyetlen kép. A képet nem kell feldolgoztatni, mehet egyből."""
    return _ig_finish(_ig_container({"image_url": _ig_https(image_url), "caption": caption[:2200]}))


def ig_publish_carousel(image_urls: list[str], caption: str) -> str:
    """Körhinta: előbb minden kép külön tárolóba, aztán egy közös poszt.
    Az Instagram 2 és 10 kép között engedi; egyetlen kép sima képposzt."""
    urls = [_ig_https(u) for u in image_urls][:10]
    if not urls:
        raise PublishError("nincs kiposztolható kép")
    if len(urls) == 1:
        return ig_publish_image(urls[0], caption)
    kids = [_ig_container({"image_url": u, "is_carousel_item": "true"}) for u in urls]
    return _ig_finish(_ig_container({"media_type": "CAROUSEL", "children": ",".join(kids),
                                     "caption": caption[:2200]}))


def ig_publish(video_url: str, caption: str, sleep=stop.sleep) -> str:
    cid = _ig_container({"media_type": "REELS", "video_url": _ig_https(video_url),
                         "caption": caption[:2200]})
    # Az Instagram a saját szerverére tölti le a videót; ez percekig tarthat.
    for _ in range(IG_POLL_TRIES):
        sleep(IG_POLL_SECONDS)
        st = _ig_call("GET", cid, {"fields": "status_code,status"}, timeout=30)
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"a feldolgozás nem sikerült: {st.get('status') or code}")
    else:
        raise PublishError("az Instagram a várakozás alatt sem végzett a videóval")
    return _ig_finish(cid)


# ---- LinkedIn ----------------------------------------------------------------

LI_API = "https://api.linkedin.com/rest"


def li_ready() -> bool:
    return bool(_env("LI_ACCESS_TOKEN") and _env("LI_AUTHOR_URN"))


def li_missing() -> list[str]:
    need = {"LI_ACCESS_TOKEN": "LinkedIn hozzáférési kulcs",
            "LI_AUTHOR_URN": "LinkedIn szerző azonosító (urn:li:person:… vagy urn:li:organization:…)"}
    return [v for k, v in need.items() if not _env(k)]


def _li_headers() -> dict:
    token = _env("LI_ACCESS_TOKEN")
    if not token:
        raise PublishError("nincs beállítva az LI_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {token}",
            "LinkedIn-Version": _env("LI_VERSION") or "202401",
            "X-Restli-Protocol-Version": "2.0.0"}


def _li_author() -> str:
    urn = _env("LI_AUTHOR_URN")
    if not urn.startswith(("urn:li:person:", "urn:li:organization:")):
        raise PublishError("az LI_AUTHOR_URN csak urn:li:person:… vagy urn:li:organization:… lehet")
    return urn


def _li_post(author: str, caption: str, content: dict) -> str:
    post = httpx.post(f"{LI_API}/posts", headers={**_li_headers(), "Content-Type": "application/json"},
                      json={"author": author, "commentary": caption[:2900], "visibility": "PUBLIC",
                            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                                             "thirdPartyDistributionChannels": []},
                            "content": content,
                            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False},
                      timeout=120)
    if post.status_code >= 400:
        raise PublishError(f"LinkedIn poszt: {_err(_json(post), post)}")
    return post.headers.get("x-restli-id") or (_json(post).get("id") or "")


def _li_upload_image(path: str, author: str) -> str:
    """Egy kép feltöltése; a kép azonosítójával tér vissza. A kép — a videóval
    ellentétben — egyetlen kérésben megy fel, és nem kell lezárni."""
    head = _li_headers()
    try:
        r = httpx.post(f"{LI_API}/images?action=initializeUpload",
                       headers={**head, "Content-Type": "application/json"},
                       json={"initializeUploadRequest": {"owner": author}}, timeout=60)
    except httpx.HTTPError as e:
        raise PublishError(f"a LinkedIn nem érhető el ({type(e).__name__})") from e
    body = _json(r)
    if r.status_code >= 400:
        raise PublishError(f"LinkedIn: {_err(body, r)}")
    value = body.get("value") or {}
    url, urn = value.get("uploadUrl"), value.get("image")
    if not url or not urn:
        raise PublishError("a LinkedIn nem adott feltöltési címet a képhez")
    with open(path, "rb") as f:
        data = f.read()
    try:
        up = httpx.put(url, content=data, headers={"Authorization": head["Authorization"],
                                                   "Content-Type": "application/octet-stream"}, timeout=180)
    except httpx.HTTPError as e:
        raise PublishError(f"a képfeltöltés megszakadt ({type(e).__name__})") from e
    if up.status_code >= 400:
        raise PublishError(f"LinkedIn képfeltöltés: HTTP {up.status_code}")
    return urn


def li_publish_images(paths: list[str], caption: str, title: str = "") -> str:
    """Egy vagy több kép egyetlen posztban. Egynél sima képposzt, többnél
    a LinkedIn lapozható „multiImage” posztja."""
    author = _li_author()
    if not paths:
        raise PublishError("nincs kiposztolható kép")
    urns = [_li_upload_image(p, author) for p in paths[:20]]
    alt = (title or "AXIMBRA")[:300]
    content = ({"media": {"title": alt[:200], "id": urns[0]}} if len(urns) == 1
               else {"multiImage": {"images": [{"id": u, "altText": alt} for u in urns]}})
    return _li_post(author, caption, content) or urns[0]


def li_publish(path: str, caption: str, title: str = "") -> str:
    """A videó feltöltése és a poszt létrehozása. A poszt azonosítójával tér vissza."""
    author = _li_author()
    size = os.path.getsize(path)
    head = _li_headers()
    try:
        r = httpx.post(f"{LI_API}/videos?action=initializeUpload", headers={**head, "Content-Type": "application/json"},
                       json={"initializeUploadRequest": {"owner": author, "fileSizeBytes": size,
                                                         "uploadCaptions": False, "uploadThumbnail": False}},
                       timeout=60)
    except httpx.HTTPError as e:
        raise PublishError(f"a LinkedIn nem érhető el ({type(e).__name__})") from e
    body = _json(r)
    if r.status_code >= 400:
        raise PublishError(f"LinkedIn: {_err(body, r)}")
    value = body.get("value") or {}
    urn = value.get("video")
    parts = value.get("uploadInstructions") or []
    if not urn or not parts:
        raise PublishError("a LinkedIn nem adott feltöltési címet")

    # A fájlt darabokban kéri; minden darab válaszának etag-jét vissza kell adni.
    tags = []
    with open(path, "rb") as f:
        for part in parts:
            first, last = int(part.get("firstByte", 0)), int(part.get("lastByte", size - 1))
            f.seek(first)
            chunk = f.read(last - first + 1)
            try:
                up = httpx.put(part["uploadUrl"], content=chunk,
                               headers={"Authorization": head["Authorization"],
                                        "Content-Type": "application/octet-stream"}, timeout=300)
            except httpx.HTTPError as e:
                raise PublishError(f"a feltöltés megszakadt ({type(e).__name__})") from e
            if up.status_code >= 400:
                raise PublishError(f"LinkedIn feltöltés: HTTP {up.status_code}")
            tags.append((up.headers.get("etag") or up.headers.get("ETag") or "").strip('"'))

    fin = httpx.post(f"{LI_API}/videos?action=finalizeUpload", headers={**head, "Content-Type": "application/json"},
                     json={"finalizeUploadRequest": {"video": urn, "uploadToken": "", "uploadedPartIds": tags}},
                     timeout=120)
    if fin.status_code >= 400:
        raise PublishError(f"LinkedIn lezárás: {_err(_json(fin), fin)}")

    return _li_post(author, caption, {"media": {"title": (title or "AXIMBRA")[:200], "id": urn}}) or urn


# ---- közös ------------------------------------------------------------------

def status() -> dict:
    return {"instagram": {"ready": ig_ready(), "missing": ig_missing()},
            "linkedin": {"ready": li_ready(), "missing": li_missing()}}


def enabled_targets() -> list[str]:
    return [t for t, on in (("instagram", ig_ready()), ("linkedin", li_ready())) if on]


def publish(target: str, *, paths: list[str], urls: list[str], caption: str,
            title: str = "", form: str = "video") -> str:
    """A kész darab kiposztolása. `paths` a helyi fájlok, `urls` ugyanazok
    nyilvános, aláírt címen — az Instagramnak az utóbbi kell."""
    if not paths:
        raise PublishError("nincs kiposztolható fájl")
    if target == "instagram":
        if not urls:
            raise PublishError("nincs nyilvános cím; állítsd be a PUBLIC_BASE_URL-t")
        if form == "video":
            return ig_publish(urls[0], caption)
        return ig_publish_carousel(urls, caption)
    if target == "linkedin":
        if form == "video":
            return li_publish(paths[0], caption, title)
        return li_publish_images(paths, caption, title)
    raise PublishError(f"ismeretlen platform: {target}")

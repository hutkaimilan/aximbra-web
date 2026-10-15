"""Megosztott iCloud-album: minden elem lejön, a gépváltást követi, a rossz elem nem állít meg."""
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import icloud_album  # noqa: E402

URL = "https://www.icloud.com/sharedalbum/#B0aG4ABCdefGHij"

WEBSTREAM = {"streamName": "reels", "photos": [
    # Fotó: a nagyobb változatot kell választani.
    {"photoGuid": "g1", "derivatives": {"1": {"checksum": "c1s", "fileSize": "10"},
                                        "2": {"checksum": "c1b", "fileSize": "99"}}},
    # Videó: a mozgóképet, nem a borítóképet — akkor is, ha a borító nagyobb.
    {"photoGuid": "g2", "mediaAssetType": "video",
     "derivatives": {"PosterFrame": {"checksum": "c2p", "fileSize": "500"},
                     "720p": {"checksum": "c2v", "fileSize": "400"}}},
    # Ez az elem elhasal a letöltésnél: a többit nem viheti magával.
    {"photoGuid": "g3", "derivatives": {"1": {"checksum": "c3", "fileSize": "5"}}},
    # Erre nem jön letöltési cím: kimarad a listából.
    {"photoGuid": "g4", "derivatives": {"1": {"checksum": "nincs", "fileSize": "5"}}},
]}


def _client(calls, status=None):
    def handler(req: httpx.Request):
        calls.append(str(req.url))
        if status and req.url.path.endswith("/webstream"):
            return httpx.Response(status, json={})
        if req.url.host == "p23-sharedstreams.icloud.com":
            return httpx.Response(330, json={"X-Apple-MMe-Host": "p45-sharedstreams.icloud.com"})
        if req.url.path.endswith("/webstream"):
            return httpx.Response(200, json=WEBSTREAM)
        if req.url.path.endswith("/webasseturls"):
            guids = json.loads(req.content)["photoGuids"]
            assert guids == ["g1", "g2", "g3", "g4"][:len(guids)]
            return httpx.Response(200, json={"items": {
                "c1b": {"url_location": "cvws.icloud-content.com", "url_path": "/a"},
                "c2v": {"url_location": "cvws.icloud-content.com", "url_path": "/v"},
                "c3": {"url_location": "cvws.icloud-content.com", "url_path": "/bad"}}})
        if req.url.path == "/bad":
            return httpx.Response(500)
        ct = "video/quicktime" if req.url.path == "/v" else "image/jpeg"
        return httpx.Response(200, content=b"adat", headers={"content-type": ct})
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def tmp_media(tmp_path, monkeypatch):
    monkeypatch.setattr(icloud_album.library, "MEDIA_DIR", str(tmp_path / "media"))


@pytest.fixture
def stored(monkeypatch):
    """A letöltés fájlba megy, nem a memóriába: a store_file-t figyeljük."""
    out = []

    def fake(path, ct, name, note, source=""):
        out.append({"ct": ct, "name": name, "note": note, "bytes": os.path.getsize(path)})
        return {"id": name}

    monkeypatch.setattr(icloud_album.library, "store_file", fake)
    return out


def test_whole_album_comes_in_and_a_bad_item_is_skipped(stored):
    calls, said = [], []
    out = icloud_album.run(URL, "első kör", said.append, client=_client(calls))
    assert out["album"] == "reels"
    assert out["ids"] == ["iCloud 001.jpg", "iCloud 002.mov"], "a jó elemek bejönnek"
    assert out["failed"] == ["iCloud 003.jpg"], "a hibás elem kimarad, nevesítve"
    assert out["total"] == 3, "a letöltési cím nélküli elem már a listából kimaradt"
    # A videónál a mozgókép jött le, nem a borítókép.
    assert stored[1]["ct"] == "video/quicktime"
    assert stored[0]["note"] == "első kör"
    assert any("p45-sharedstreams" in c for c in calls), "a 330 után a helyes gépet hívja"
    assert any("KIMARADT" in m for m in said), "a kimaradt elem a naplóba kerül"


def test_the_download_never_goes_through_memory(stored, monkeypatch):
    """Egy nagy videó nem kerülhet egyben a memóriába."""
    seen = {}
    real = icloud_album.library.store_file
    monkeypatch.setattr(icloud_album.library, "store_file",
                        lambda path, *a, **k: seen.update(path=path) or real(path, *a, **k))
    icloud_album.run(URL, "x", client=_client([]))
    assert seen["path"], "a store_file fájlútvonalat kap, nem bájtokat"
    assert not os.path.exists(seen["path"]), "az átmeneti fájl utána törlődik"


def test_a_failing_item_does_not_stop_the_rest(stored):
    """Ez a lényeg: a telefon all-or-nothing hibáját pont ezzel kerüljük meg."""
    out = icloud_album.run(URL, "x", client=_client([]))
    assert len(out["ids"]) == 2 and len(out["failed"]) == 1


def test_empty_album_is_explained(monkeypatch, stored):
    def handler(req):
        if req.url.host == "p23-sharedstreams.icloud.com":
            return httpx.Response(330, json={"X-Apple-MMe-Host": "p45-sharedstreams.icloud.com"})
        return httpx.Response(200, json={"streamName": "üres", "photos": []})
    with pytest.raises(icloud_album.AlbumError, match="üres"):
        icloud_album.run(URL, "x", client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("status,msg", [(404, "nem található"), (403, "Nyilvános webhely"),
                                        (500, "hibát adott")])
def test_icloud_errors_say_what_to_do(status, msg):
    with pytest.raises(icloud_album.AlbumError, match=msg):
        icloud_album.listing(URL, client=_client([], status=status))


def test_redirect_loop_gives_up():
    def handler(req):
        return httpx.Response(330, json={"X-Apple-MMe-Host": req.url.host})
    with pytest.raises(icloud_album.AlbumError, match="körbe"):
        icloud_album.listing(URL, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_network_failure_is_reported():
    def handler(req):
        raise httpx.ConnectError("nincs net")
    with pytest.raises(icloud_album.AlbumError, match="nem sikerült elérni"):
        icloud_album.listing(URL, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_wrong_links_are_explained():
    # iCloud-link, de nem megosztott album: mondjuk meg, mit kell beállítani.
    with pytest.raises(icloud_album.AlbumError, match="Nyilvános webhely"):
        icloud_album.token_of("https://www.icloud.com/photos/#0abcDEF")
    with pytest.raises(icloud_album.AlbumError, match="Ismeretlen link"):
        icloud_album.token_of("https://example.com/x")
    with pytest.raises(icloud_album.AlbumError):
        icloud_album.token_of("")
    assert icloud_album.token_of(URL) == "B0aG4ABCdefGHij"
    # A # nélküli és a szóközös beillesztés is menjen.
    assert icloud_album.token_of("  https://www.icloud.com/sharedalbum/B0aG4ABCdefGHij ") \
        == "B0aG4ABCdefGHij"


def test_album_items_are_capped(monkeypatch, stored):
    monkeypatch.setattr(icloud_album, "MAX_ITEMS", 2)
    _name, items = icloud_album.listing(URL, client=_client([]))
    assert len(items) == 2

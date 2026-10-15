"""Megosztott iCloud-album: minden elem lejön, a 330-as gépváltást követi, a rossz elem nem állítja meg."""
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import album_import  # noqa: E402

URL = "https://www.icloud.com/sharedalbum/#B0aG4ABCdefGHij"


def _client(calls):
    def handler(req: httpx.Request):
        calls.append(str(req.url))
        if req.url.host == "p23-sharedstreams.icloud.com":
            return httpx.Response(330, json={"X-Apple-MMe-Host": "p45-sharedstreams.icloud.com"})
        if req.url.path.endswith("/webstream"):
            return httpx.Response(200, json={"streamName": "Nyár", "photos": [
                {"photoGuid": "g1", "derivatives": {"1": {"checksum": "c1s", "fileSize": "10"}, "2": {"checksum": "c1b", "fileSize": "99"}}},
                {"photoGuid": "g2", "mediaAssetType": "video", "derivatives": {
                    "PosterFrame": {"checksum": "c2p", "fileSize": "500"}, "720p": {"checksum": "c2v", "fileSize": "400"}}},
                {"photoGuid": "g3", "derivatives": {"1": {"checksum": "c3", "fileSize": "5"}}}]})
        if req.url.path.endswith("/webasseturls"):
            assert json.loads(req.content)["photoGuids"] == ["g1", "g2", "g3"]
            return httpx.Response(200, json={"items": {
                "c1b": {"url_location": "cvws.icloud-content.com", "url_path": "/a"},
                "c2v": {"url_location": "cvws.icloud-content.com", "url_path": "/v"},
                "c3": {"url_location": "cvws.icloud-content.com", "url_path": "/bad"}}})
        if req.url.path == "/bad":
            return httpx.Response(500)
        ct = "video/mp4" if req.url.path == "/v" else "image/jpeg"
        return httpx.Response(200, content=b"data", headers={"content-type": ct})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_whole_album_comes_in_and_a_bad_item_is_skipped(monkeypatch):
    stored = []
    monkeypatch.setattr(album_import.media, "store",
                        lambda data, ct, name, note, redact_pii=False: stored.append((ct, name, note)) or {"id": name})
    calls = []
    ids = album_import.run(URL, "iCloud-album x", client=_client(calls))
    assert ids == ["iCloud 01.jpg", "iCloud 02.mp4"]
    assert stored[1][0] == "video/mp4" and stored[0][2] == "iCloud-album x"
    assert any("p45-sharedstreams" in c for c in calls)          # a 330 után a helyes gép


def test_wrong_links_are_explained():
    with pytest.raises(album_import.ImportError_, match="Nyilvános webhely"):
        album_import.token_of("https://www.icloud.com/photos/#0abcDEF")
    with pytest.raises(album_import.ImportError_):
        album_import.token_of("https://example.com/x")
    assert album_import.token_of(URL) == "B0aG4ABCdefGHij"

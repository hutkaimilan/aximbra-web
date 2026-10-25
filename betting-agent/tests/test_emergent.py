"""Az Emergent-féle Szelvénymodell kiszolgálása: csak a felület fájljai és a hét API-végpont érhető el."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web  # noqa: E402


@pytest.mark.parametrize("path", ["/emergent/api/state", "/emergent/api/slips", "/emergent/api/check",
                                  "/emergent/api/accuracy", "/emergent/api/log", "/emergent/api/health",
                                  "/emergent/api/team/12345"])
def test_allowed_api_paths(path):
    assert web.EMERGENT_API.match(path)


@pytest.mark.parametrize("path", ["/emergent/api/../secret", "/emergent/api/team/../../x", "/emergent/api/admin",
                                  "/emergent/api/state/x", "/emergent/api/team/", "/emergent/api/team/a b"])
def test_other_api_paths_rejected(path):
    assert not web.EMERGENT_API.match(path)


@pytest.mark.parametrize("path,ok", [("/emergent/assets/index-Dv84hyAx.js", True), ("/emergent/assets/a.css", True),
                                     ("/emergent/assets/../web.py", False), ("/emergent/assets/x/y.js", False)])
def test_asset_paths(path, ok):
    assert bool(web.EMERGENT_ASSET.match(path)) is ok


def test_built_ui_is_present():
    assert (web.EMERGENT_DIR / "index.html").is_file()
    assert any((web.EMERGENT_DIR / "assets").glob("index-*.js"))


def test_keepalive_stops_after_repeated_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(web, "KEEPALIVE_SECONDS", 0.01)
    monkeypatch.setattr(web, "_emergent_alive", lambda: calls.append(1) or False)
    ka = web.EmergentKeepAlive()
    ka.kick()
    ka.kick()  # második indítás nem indít újabb szálat
    for _ in range(200):
        if not ka._running:
            break
        import time
        time.sleep(0.01)
    assert not ka._running
    assert len(calls) == web.KEEPALIVE_MAX_FAILS


def test_keepalive_disabled(monkeypatch):
    monkeypatch.setattr(web, "KEEPALIVE_SECONDS", 0)
    ka = web.EmergentKeepAlive()
    ka.kick()
    assert not ka._running

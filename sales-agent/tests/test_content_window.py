"""A napi poszt csak a beállított ablakban indulhat (pl. 18:00–19:00)."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import content  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

TZ = ZoneInfo("Europe/Budapest")


class _Store:
    def __init__(self):
        self.s = {}

    def get_setting(self, k):
        return self.s.get(k)


def test_posting_only_between_18_and_19(monkeypatch):
    monkeypatch.setenv("CONTENT_TIME", "18:00")
    monkeypatch.setattr(content, "LAST_HOUR", 19)
    at = lambda h, m: datetime(2026, 10, 24, h, m, tzinfo=TZ)  # noqa: E731
    assert not content.due(at(17, 59), _Store())
    assert content.due(at(18, 0), _Store())
    assert content.due(at(18, 45), _Store())
    assert not content.due(at(19, 0), _Store())
    assert not content.due(at(20, 30), _Store())

"""Platformonként külön posztidő: LinkedIn kedd–csütörtök 9:50-től,
Instagram hétköznap 12:20-tól, hétvégén semmi; két órás ablakon túl kimarad."""
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


def at(day, h, m):
    return datetime(2026, 11, day, h, m, tzinfo=TZ)  # 2026-11-02 hétfő


def test_linkedin_only_tuesday_to_thursday_morning():
    s = _Store()
    assert not content.lang_due("hu", at(2, 10, 0), s)        # hétfő
    assert not content.lang_due("hu", at(3, 9, 49), s)        # kedd, kezdés előtt
    assert content.lang_due("hu", at(3, 9, 50), s)
    assert content.lang_due("hu", at(5, 11, 30), s)           # csütörtök
    assert not content.lang_due("hu", at(3, 11, 50), s)       # két óra után kimarad
    assert not content.lang_due("hu", at(6, 10, 0), s)        # péntek


def test_instagram_weekdays_at_lunch_and_never_at_weekend():
    s = _Store()
    assert content.lang_due("en", at(2, 12, 20), s)           # hétfő
    assert content.lang_due("en", at(6, 13, 0), s)            # péntek
    assert not content.lang_due("en", at(3, 10, 0), s)
    assert not content.lang_due("en", at(7, 12, 30), s)       # szombat
    assert not content.due(at(8, 12, 30), s)                  # vasárnap


def test_sent_today_is_not_sent_again():
    s = _Store()
    s.s["content_sent_en"] = "2026-11-02"
    assert not content.due(at(2, 12, 30), s)

"""Szabad időpontok a 20 perces beszélgetésre, a tulajdonos naptárából.

A Google Naptár "titkos iCal-címéről" olvas (CALENDAR_ICS_URL): csak
olvasás, nincs belépés. Ha nincs beállítva, a munkaidőből ajánl, és ezt
a panel ki is írja. Írni nem ír a naptárba: a foglalást egy előre
kitöltött Google Naptár-link teszi be, egy koppintással.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Budapest")
UTC = ZoneInfo("UTC")
MEETING_MIN = int(os.environ.get("MEETING_MINUTES") or 20)
BUFFER_MIN = 15
DAY_START = time(int(os.environ.get("WORK_START_HOUR") or 9))
DAY_END = time(int(os.environ.get("WORK_END_HOUR") or 17))
LOOKAHEAD_WORKDAYS = 6

# A javasolt időpontok napszaka váltakozik: ha valakinek a délelőtt nem jó,
# a délután még igen.
PREFERRED_TIMES = [time(10, 0), time(14, 0), time(9, 30), time(15, 30), time(11, 0), time(13, 30)]


def busy_intervals(ics_text: str, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(ics_text)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        if str(ev.get("TRANSP", "")).upper() == "TRANSPARENT":
            continue  # "szabadként" jelölt esemény
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s, e = ev.get("DTSTART").dt, (ev.get("DTEND").dt if ev.get("DTEND") else None)
        if isinstance(s, date) and not isinstance(s, datetime):
            # Egész napos esemény: az egész napot foglaltnak vesszük.
            s = datetime.combine(s, time(0), TZ)
            e = datetime.combine(e if isinstance(e, date) else s.date() + timedelta(days=1), time(0), TZ)
        else:
            s = s if s.tzinfo else s.replace(tzinfo=TZ)
            e = (e if e and e.tzinfo else (e.replace(tzinfo=TZ) if e else s + timedelta(hours=1)))
        out.append((s.astimezone(TZ), e.astimezone(TZ)))
    return out


def fetch_ics(url: str) -> str | None:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        if r.status_code == 200 and "BEGIN:VCALENDAR" in r.text[:2000]:
            return r.text
        logger.warning("naptár: %s válasz", r.status_code)
    except httpx.HTTPError as e:
        logger.warning("naptár nem elérhető: %s", type(e).__name__)
    return None


def free_slots(now: datetime | None = None, ics_text: str | None = None, want: int = 3) -> list[datetime]:
    """`want` darab szabad kezdés, lehetőleg mind más napon.

    Legkorábban a következő munkanapon: egy aznapi időpontot egy hideg
    megkeresésre senki nem fogad el."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    days = []
    d = now.date() + timedelta(days=1)
    while len(days) < LOOKAHEAD_WORKDAYS:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    busy = []
    if ics_text:
        try:
            busy = busy_intervals(ics_text, datetime.combine(days[0], time(0), TZ),
                                  datetime.combine(days[-1], time(23, 59), TZ))
        except Exception as e:  # noqa: BLE001 — hibás naptár ne állítsa le a választ
            logger.warning("naptár nem olvasható: %s", e)
    pad = timedelta(minutes=BUFFER_MIN)
    dur = timedelta(minutes=MEETING_MIN)

    def ok(start: datetime) -> bool:
        end = start + dur
        if start.time() < DAY_START or end.time() > DAY_END:
            return False
        return all(not (start - pad < b_end and end + pad > b_start) for b_start, b_end in busy)

    slots = []
    for i, day in enumerate(days):
        if len(slots) >= want:
            break
        prefs = PREFERRED_TIMES[i % 2::2] + PREFERRED_TIMES[(i + 1) % 2::2]
        for t in prefs:
            cand = datetime.combine(day, t, TZ)
            if ok(cand):
                slots.append(cand)
                break
    return slots


HU_DAYS = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
HU_MONTHS = ["január", "február", "március", "április", "május", "június", "július", "augusztus",
             "szeptember", "október", "november", "december"]


def label_hu(dt: datetime) -> str:
    return f"{HU_MONTHS[dt.month - 1]} {dt.day}. ({HU_DAYS[dt.weekday()]}) {dt:%H:%M}"


def calendar_link(dt: datetime, company: str, guest: str) -> str:
    """Előre kitöltött Google Naptár-esemény; a vendég meghívót kap, ha
    a mentéskor a naptár felajánlja a meghívó elküldését."""
    end = dt + timedelta(minutes=MEETING_MIN)
    fmt = "%Y%m%dT%H%M%SZ"
    q = {
        "action": "TEMPLATE",
        "text": f"AXIMBRA – 20 perces beszélgetés ({company})",
        "dates": f"{dt.astimezone(UTC):{fmt}}/{end.astimezone(UTC):{fmt}}",
        "details": "Rövid felmérés: melyik feladat ismétlődik a legtöbbször, és mennyi automatizálható belőle.\n"
                   "Hutkai Milán · AXIMBRA · aximbra.hu",
        "add": guest,
        "ctz": "Europe/Budapest",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(q)


def slots_for(company: str, guest: str, now: datetime | None = None) -> dict:
    url = os.environ.get("CALENDAR_ICS_URL", "").strip()
    ics = fetch_ics(url) if url else None
    slots = free_slots(now=now, ics_text=ics)
    return {
        "calendar": bool(ics),
        "slots": [{"iso": s.isoformat(), "label": label_hu(s), "link": calendar_link(s, company, guest)}
                  for s in slots],
    }

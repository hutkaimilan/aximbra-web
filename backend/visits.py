"""Latogatasszamlalo — sajat, sutimentes, kulso szolgaltato nelkul.

MIERT VAN EZ: az oldal napokig ugy futott elesben, hogy senki nem tudta, jart-e
rajta barki. Egy rossz szoveget es egy nem letezo latogatottsagot ugyanaz a
jelenseg takar — nulla megkereses —, de a kettot teljesen maskepp kell
javitani. Meres nelkul ez a kulonbseg lathatatlan.

MIERT NEM GOOGLE ANALYTICS VAGY PLAUSIBLE: mindketto fiokot, es a Plausible
penzt is ker, a GA4 pedig sutibannert hoz magaval. Ez a valtozat ma mukodik,
nem kerul semmibe, es nincs rajta jogi teher. Ha kesobb kell grafikon es
megoszlas, a beacon ugyanugy atiranyithato egy rendes szolgaltatoba.

ADATVEDELEM — SZANDEKOSAN KEVESET TUDUNK:
  - nincs suti es nincs localStorage,
  - nem taroljuk az IP-cimet es nem kepzunk belole azonositot,
  - nem koveteljuk egyik latogatot sem fordulokon at.
Ami marad: melyik utvonalat neztek meg, milyen nyelven, es melyik oldalrol
jottek (csak a hivatkozo domainje). Ez osszesitett, nem szemelyes adat.

TAROLAS: a napi osszesitok a folyamat memoriajaban elnek, es minden talalat
egy sort is ir a naplóba. Az ujraindulas kinullazza a memoriat - ezert van a
naplosor: az tullep egy deployt, es abbol barmikor visszaszamolhato a nap.
"""
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Csak olyan utvonalat fogadunk el, ami az oldalon letezhet. Egy nyitott
# szamlalo, ami barmit elfogad, elobb-utobb idegen adatot gyujt - es akkor a
# sajat szamaidban sem bizhatsz.
#
# A leghosszabb valodi utvonal harom szeletbol all (`/en/demo/email-agent`),
# ezert ennel tobbet nem engedunk. Puszta hosszkorlat kevés volt: egy 500
# karakteres `/x/x/x/...` a csonkolas utan szabalyosnak latszott, es bekerult
# a szamlalóba.
PATH_OK = re.compile(r"^/(?:[A-Za-z0-9_-]{1,32}(?:/[A-Za-z0-9_-]{1,32}){0,2})?$")
LANG_OK = re.compile(r"^[a-z]{2}$")

# Nap -> utvonal -> darab, es nap -> hivatkozo -> darab.
_paths: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_refs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
# Mennyi napot tartunk a memoriaban. Egy latogatoszamlalonak a mult heti
# bontasa mar nem donteshez kell, hanem kivancsisagbol - az a naplóban van.
KEEP_DAYS = 14


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _trim() -> None:
    for store in (_paths, _refs):
        while len(store) > KEEP_DAYS:
            store.pop(min(store), None)


def _referrer_host(raw: str) -> str:
    """Csak a hivatkozo domainje. A teljes URL mar tobbet arulna el a
    latogatorol, mint amennyi ehhez kell."""
    if not raw:
        return "kozvetlen"
    try:
        host = (urlparse(raw).hostname or "").lower()
    except ValueError:
        return "ismeretlen"
    if not host:
        return "kozvetlen"
    if host.endswith("aximbra.hu"):
        return "sajat"
    return host[:80]


class Hit(BaseModel):
    path: str
    ref: str = ""
    lang: str = ""

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        v = (v or "/").split("?")[0].split("#")[0][:120].rstrip("/") or "/"
        return v if PATH_OK.match(v) else "/egyeb"

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        v = (v or "").strip().lower()[:2]
        return v if LANG_OK.match(v) else ""


@router.post("/hit", status_code=204)
async def hit(body: Hit, request: Request) -> None:
    """Egy oldalmegtekintes. Soha nem dob hibat a latogato fele: egy
    szamlalo nem ronthat el egy oldalbetoltest."""
    try:
        day = _today()
        ref = _referrer_host(body.ref)
        _paths[day][body.path] += 1
        _refs[day][ref] += 1
        _trim()
        # Ez a sor eli tul az ujraindulast. A naplobol barmelyik nap
        # visszaszamolhato akkor is, ha a memoria kozben kinullazodott.
        logger.info(
            "[hit] nap=%s ut=%s honnan=%s nyelv=%s", day, body.path, ref, body.lang or "?"
        )
    except Exception:  # pragma: no cover - a szamlalo soha nem all utban
        logger.exception("[hit] a szamlalas elszallt, a keres ettol meg rendben van")


@router.get("/visits")
async def visits() -> dict:
    """Amit eddig szamoltunk, naponta. Nyilvanos: nincs benne semmi, ami ne
    lenne osszesitett - es ha egy szam mogott nincs bizalom, nem hasznaljuk."""
    days = sorted(set(_paths) | set(_refs), reverse=True)
    return {
        "megjegyzes": (
            "Az ujrainditas kinullazza; a teljes tortenet a szolgaltatas "
            "naploiban van, a [hit] sorokban."
        ),
        "napok": [
            {
                "nap": d,
                "osszesen": sum(_paths.get(d, {}).values()),
                "utvonalak": dict(sorted(_paths.get(d, {}).items(), key=lambda kv: -kv[1])[:20]),
                "honnan": dict(sorted(_refs.get(d, {}).items(), key=lambda kv: -kv[1])[:20]),
            }
            for d in days
        ],
    }

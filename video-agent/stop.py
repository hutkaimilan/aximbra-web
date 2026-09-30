"""A futó gyártás leállítása.

Egy szálat Pythonban nem lehet kívülről megölni, ezért a munka maga
figyeli a leállítás kérését: minden lépés között, renderelésnél minden
képkockánál, várakozásnál pedig azonnal. A folyamatban lévő egyetlen
hálózati kérés (pl. egy modellhívás) még végigmegy, utána áll meg.

Egyszerre csak egy gyártás fut, ezért egy közös jelző elég.
"""
import threading

_event = threading.Event()


class Cancelled(Exception):
    pass


def request() -> None:
    _event.set()


def reset() -> None:
    _event.clear()


def requested() -> bool:
    return _event.is_set()


def check() -> None:
    if _event.is_set():
        raise Cancelled("leállítva")


def sleep(seconds: float) -> None:
    """Várakozás, amit a leállítás azonnal megszakít."""
    if _event.wait(max(0.0, seconds)):
        raise Cancelled("leállítva")

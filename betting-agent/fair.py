"""Árrés eltávolítása: az iroda szorzóiból valós esélyt számolunk.

A szorzók inverzének összege 1 fölött van; a többlet az iroda árrése. A
hatványmódszer (1/o)^k alakban osztja szét, ami a nagy esélytelenekre több
árrést tesz, mint a kedvencekre — így viselkednek az irodák a valóságban is
(favourite–longshot torzítás). Az arányos módszer egyszerűbb, de az
esélytelen kimenetelek esélyét túlbecsüli.
"""
import statistics


def _check(odds):
    if len(odds) < 2:
        raise ValueError("legalább két kimenetel kell")
    for o in odds:
        if not (isinstance(o, (int, float)) and 1.0 < o < 10_000):
            raise ValueError(f"érvénytelen szorzó: {o!r}")


def overround(odds) -> float:
    _check(odds)
    return sum(1 / o for o in odds) - 1


def devig_multiplicative(odds) -> list[float]:
    _check(odds)
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def devig_power(odds) -> list[float]:
    _check(odds)
    inv = [1 / o for o in odds]
    lo, hi = 0.01, 20.0
    # sum(inv^k) k-ban szigorúan csökkenő, mert minden inv < 1: felezéssel megvan.
    for _ in range(100):
        k = (lo + hi) / 2
        if sum(x ** k for x in inv) > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    probs = [x ** k for x in inv]
    s = sum(probs)
    return [p / s for p in probs]


def consensus(by_book: dict[str, list[float]], sharp_books) -> tuple[list[float], str, list[str]]:
    """Irodánként árrésmentesített esélyekből egy becslés.

    Visszaad: (esélyek, bizalom, felhasznált irodák). Ha van Pinnacle, az az
    irányadó: ott a legkisebb az árrés, és a profi pénz azt mozgatja. Ha
    nincs, a többi éles piac átlaga; ha az sincs, az összes iroda mediánja,
    alacsony bizalommal.
    """
    if not by_book:
        raise ValueError("nincs egy iroda sem")
    if "pinnacle" in by_book:
        return by_book["pinnacle"], "magas", ["pinnacle"]
    sharp = [b for b in sharp_books if b in by_book]
    if sharp:
        n = len(by_book[sharp[0]])
        probs = [statistics.fmean(by_book[b][i] for b in sharp) for i in range(n)]
        conf = "közepes"
        used = sharp
    else:
        n = len(next(iter(by_book.values())))
        probs = [statistics.median(v[i] for v in by_book.values()) for i in range(n)]
        conf = "alacsony"
        used = sorted(by_book)
    s = sum(probs)
    return [p / s for p in probs], conf, used

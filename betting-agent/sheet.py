"""A kitöltendő táblázat: az elemzés ide írja a valós esélyeket, te ide írod a Tippmix-szorzót.

A TippmixPro szorzóit nem töltjük le: nincs nyilvános API-ja, a weboldal
lekaparása a felhasználási feltételekbe ütközhet és bármikor eltörhet. Egy
csapatnév-egyeztetés (angol forrás ↔ magyar Tippmix-nevek) pedig csendben
rossz meccshez párosíthatna egy szorzót. Ezért a táblázat soronként azonosít,
és a szelvény az elemzés saját esélyeiből számol: a második lépés nem kér
újabb API-hívást.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

from slip import Leg

COLUMNS = ["id", "meccs_id", "generalva", "kezdes", "liga", "merkozes", "piac", "tipp",
           "forras", "bizalom", "fair_esely", "fair_szorzo", "min_szorzo", "tippmix_szorzo", "kotes"]


class SheetError(ValueError):
    pass


def write(path: Path, analyses, leagues: dict, strategy, generated: datetime) -> int:
    rows = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM: az Excel így ismeri fel az ékezeteket
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUMNS)
        for a in sorted(analyses, key=lambda x: x.match.kickoff):
            m = a.match
            for s in a.selections:
                sid = f"{m.id}|{s.market}|{s.pick}"
                w.writerow([sid, m.id, generated.isoformat(timespec="seconds"),
                            m.kickoff.isoformat(timespec="minutes"), leagues.get(m.sport, m.sport),
                            f"{m.home} – {m.away}", s.market, s.pick, s.source, s.confidence,
                            _fmt(s.prob, 4), _fmt(s.fair_odds, 2), _fmt(s.min_odds(strategy), 2), "", "1"])
                rows += 1
    return rows


def _fmt(x: float, nd: int) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _num(raw: str, what: str, row: int) -> float:
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError as e:
        raise SheetError(f"{row}. sor: a(z) {what} nem szám: {raw!r}") from e


def read(path: Path, now: datetime | None = None, max_age_hours: float = 6.0,
         allow_stale: bool = False) -> tuple[list, list]:
    """A kitöltött sorokból lábak, és a figyelmeztetések listája."""
    now = now or datetime.now(timezone.utc)
    if not path.exists():
        raise SheetError(f"nincs ilyen fájl: {path}")
    legs, warnings, oldest = [], [], None
    with path.open(newline="", encoding="utf-8-sig") as f:
        # A fejlécből döntjük el: az adatsorokban a tizedesvessző megtévesztené a számolást.
        header = f.readline()
        f.seek(0)
        delim = ";" if header.count(";") >= header.count(",") else ","
        reader = csv.DictReader(f, delimiter=delim)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise SheetError(f"hiányzó oszlop(ok): {', '.join(sorted(missing))} — az elemzés által írt fájlt töltsd ki")
        for i, r in enumerate(reader, start=2):
            raw = (r.get("tippmix_szorzo") or "").strip()
            if not raw:
                continue
            odds = _num(raw, "tippmix_szorzo", i)
            if not 1.01 <= odds <= 1000:
                raise SheetError(f"{i}. sor: a {odds} nem lehet Tippmix-szorzó")
            prob = _num(r["fair_esely"], "fair_esely", i)
            if not 0 < prob < 1:
                raise SheetError(f"{i}. sor: hibás fair_esely: {prob}")
            kotes_raw = (r.get("kotes") or "1").strip() or "1"
            kotes = int(_num(kotes_raw, "kotes", i))
            if not 1 <= kotes <= 20:
                raise SheetError(f"{i}. sor: a kötés 1 és 20 között lehet, nem {kotes}")
            try:
                kickoff = datetime.fromisoformat(r["kezdes"])
                generated = datetime.fromisoformat(r["generalva"])
            except ValueError as e:
                raise SheetError(f"{i}. sor: hibás dátum ({e})") from e
            oldest = generated if oldest is None or generated < oldest else oldest
            if kickoff <= now:
                warnings.append(f"Kihagyva, már elkezdődött: {r['merkozes']} ({r['piac']} {r['tipp']})")
                continue
            legs.append(Leg(id=r["id"], match_id=r["meccs_id"], match=r["merkozes"],
                            label=f"{r['piac']}: {r['tipp']}", prob=prob, odds=odds, kotes=kotes,
                            source=r["forras"], min_odds=_num(r["min_szorzo"], "min_szorzo", i)))
    if oldest is not None:
        age_h = (now - oldest).total_seconds() / 3600
        if age_h > max_age_hours:
            msg = (f"Az elemzés {age_h:.1f} órás (határ: {max_age_hours:g} óra): azóta sérülés, "
                   f"kezdőcsapat vagy piacmozgás átírhatta az esélyeket. Futtasd újra az elemzést.")
            if not allow_stale:
                raise SheetError(msg + " (Ha mégis ebből kérsz szelvényt: --regi-is)")
            warnings.append(msg)
    return legs, warnings

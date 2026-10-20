"""Fogadáskészítő agent: BL, EL, Premier League, La Liga, Bundesliga → TippmixPro-szelvény.

Két lépés, mert a Tippmix-szorzókat te olvasod le az appból (lásd sheet.py):

  python agent.py elemzes                  # szorzók letöltése, esélyek, kitöltendő táblázat
  python agent.py szelveny --tabla out/tippmix_kitoltendo.csv --keret 50000

Kulcs nélkül, a mellékelt mintaadattal kipróbálható:

  python agent.py elemzes --offline sample/odds_sample.json
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import markets
import odds_api
import report
import sheet
import slip
from config import DEFAULT_BOOKMAKERS, LEAGUES, load_rules, load_strategy

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def _load_offline(path: Path, now: datetime) -> dict:
    """A mintaadat időpontjait a jövőbe toljuk, hogy a szelvény-lépés is kipróbálható legyen."""
    data = json.loads(path.read_text("utf-8"))
    times = [datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
             for evs in data.values() for e in evs]
    if times:
        # Holnap 16:00 UTC (18:00 budapesti idő) lesz az első kezdés.
        shift = (now + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0) - min(times)
        for evs in data.values():
            for e in evs:
                t = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) + shift
                e["commence_time"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    return data


def cmd_elemzes(args) -> int:
    strategy = load_strategy()
    now = datetime.now(timezone.utc)
    leagues = {k: v for k, v in LEAGUES.items() if not args.liga or k in args.liga}
    raw_by_league, errors, statuses = {}, [], []
    if args.offline:
        raw_by_league = _load_offline(Path(args.offline), now)
        statuses.append(f"Mintaadat: {args.offline} (nem valós mérkőzések)")
    else:
        key = os.environ.get("ODDS_API_KEY", "").strip()
        if not key:
            print("Hiányzik az ODDS_API_KEY (ingyenes kulcs: https://the-odds-api.com). "
                  "Kipróbáláshoz: --offline sample/odds_sample.json", file=sys.stderr)
            return 2
        books = os.environ.get("ODDS_BOOKMAKERS", DEFAULT_BOOKMAKERS)
        for sport in leagues:
            try:
                data, status = odds_api.fetch_league(sport, key, books, strategy.days_ahead, OUT / "cache",
                                                     cache_minutes=args.cache_perc, now=now)
                raw_by_league[sport] = data
                statuses.append(f"{leagues[sport]}: {len(data)} meccs — {status}")
            except odds_api.AuthError as e:
                print(f"Hiba: {e}", file=sys.stderr)
                return 2
            except odds_api.OddsApiError as e:
                errors.append(f"{leagues[sport]}: nem sikerült letölteni ({e})")

    analyses = []
    for sport, raw in raw_by_league.items():
        if sport not in leagues:
            continue
        for m in odds_api.parse_events(raw, sport):
            try:
                analyses.append(markets.analyse(m, strategy))
            except ValueError as e:
                errors.append(f"{m.home} – {m.away}: kihagyva ({e})")

    stamp = now.astimezone(report.BUDAPEST).strftime("%Y%m%d-%H%M")
    sheet_path = Path(args.tabla) if args.tabla else OUT / "tippmix_kitoltendo.csv"
    rows = sheet.write(sheet_path, analyses, LEAGUES, strategy, now)
    md = report.analysis(analyses, LEAGUES, strategy, errors, statuses, now, sheet_path)
    md_path = OUT / f"elemzes-{stamp}.md"
    md_path.write_text(md, "utf-8")
    print(md)
    print(f"\nJelentés: {md_path}\nKitöltendő táblázat ({rows} sor): {sheet_path}", file=sys.stderr)
    return 0 if analyses or not errors else 1


def cmd_szelveny(args) -> int:
    rules, strategy = load_rules(), load_strategy()
    if args.keret < rules.min_stake:
        print(f"A keret legalább {rules.min_stake} Ft legyen.", file=sys.stderr)
        return 2
    if args.cel_szorzo is not None and args.cel_szorzo <= 1:
        print("A célszorzó 1-nél nagyobb legyen.", file=sys.stderr)
        return 2
    try:
        legs, warnings = sheet.read(Path(args.tabla), max_age_hours=strategy.max_age_hours,
                                    allow_stale=args.regi_is)
    except sheet.SheetError as e:
        print(f"Hiba a táblázatban: {e}", file=sys.stderr)
        return 2
    if not legs:
        print("Egy sorban sincs kitöltve a tippmix_szorzo oszlop (vagy mind elkezdődött).", file=sys.stderr)
        return 1
    singles, skipped = slip.singles(legs, args.keret, rules, strategy)
    combos = slip.combos(legs, args.keret, rules, strategy, target_odds=args.cel_szorzo,
                         allow_negative=args.negativ_is)
    cap_notes = []
    singles, dropped1, n1 = slip.cap_total(singles, args.keret, rules, strategy)
    combos, dropped2, n2 = slip.cap_total(combos, args.keret, rules, strategy)
    if n1:
        cap_notes.append(f"A terv: {n1}")
        skipped += [(b.legs[0], "kiesett a napi plafon miatt (a minimális tét alá csökkent volna)")
                    for b in dropped1]
    if n2:
        cap_notes.append(f"B terv: {n2}" + (f"; {len(dropped2)} kötés kiesett" if dropped2 else ""))
    md = report.slips(legs, singles, skipped, combos, warnings, cap_notes, args.keret, rules, strategy,
                      args.cel_szorzo)
    OUT.mkdir(exist_ok=True)
    path = OUT / f"szelveny-{datetime.now(report.BUDAPEST):%Y%m%d-%H%M}.md"
    path.write_text(md, "utf-8")
    print(md)
    print(f"\nSzelvényjavaslat: {path}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Fogadáskészítő agent TippmixPro-hoz")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("elemzes", help="szorzók letöltése és elemzés")
    e.add_argument("--liga", nargs="*", choices=list(LEAGUES), help="csak ezek a bajnokságok")
    e.add_argument("--offline", metavar="JSON", help="mintaadat a The Odds API helyett")
    e.add_argument("--tabla", metavar="CSV", help="a kitöltendő táblázat helye")
    e.add_argument("--cache-perc", type=int, default=30, help="ennyi percig nem kér újra (kvótavédelem)")
    e.set_defaults(func=cmd_elemzes)

    s = sub.add_parser("szelveny", help="szelvény a kitöltött táblázatból")
    s.add_argument("--tabla", required=True, metavar="CSV")
    s.add_argument("--keret", type=int, required=True, help="a fogadásra szánt teljes keret, Ft")
    s.add_argument("--cel-szorzo", type=float, help="a kötés eredő szorzója legalább ennyi legyen")
    s.add_argument("--negativ-is", action="store_true",
                   help="a célszorzóhoz negatív várható értékű lábat is felhasználhat (nem ajánlott)")
    s.add_argument("--regi-is", action="store_true", help="régi elemzésből is számol")
    s.set_defaults(func=cmd_szelveny)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

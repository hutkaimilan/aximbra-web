"""Magyar nyelvű Markdown-jelentések: az elemzésé és a szelvényé."""
from datetime import datetime
from zoneinfo import ZoneInfo

BUDAPEST = ZoneInfo("Europe/Budapest")


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%".replace(".", ",")


def _ev(x: float) -> str:
    return f"{x * 100:+.1f}%".replace(".", ",")


def _odds(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _ft(x: int) -> str:
    return f"{x:,}".replace(",", " ") + " Ft"


def _when(dt: datetime) -> str:
    return dt.astimezone(BUDAPEST).strftime("%m.%d. %H:%M")


def analysis(analyses, leagues: dict, strategy, errors: list, statuses: list, generated: datetime,
             sheet_path) -> str:
    out = [f"# Meccselemzés — {generated.astimezone(BUDAPEST):%Y.%m.%d. %H:%M}", ""]
    out += ["Az esélyek a legélesebb elérhető piac (Pinnacle, tőzsde) szorzóiból számolódnak, árrés nélkül.",
            "A **min. szorzó** az a legkisebb Tippmix-szorzó, amelynél a tipp hosszú távon nyereséges "
            f"(piaci tippnél {_pct(strategy.min_edge_market)}, modellből számoltnál "
            f"{_pct(strategy.min_edge_model)} előnnyel). Ez alatt **ne** játszd meg.", ""]
    for s in statuses:
        out.append(f"- {s}")
    for e in errors:
        out.append(f"- ⚠️ {e}")
    out.append("")
    by_league = {}
    for a in analyses:
        by_league.setdefault(a.match.sport, []).append(a)
    for sport, items in by_league.items():
        out += [f"## {leagues.get(sport, sport)}", ""]
        for a in sorted(items, key=lambda x: x.match.kickoff):
            m = a.match
            ph, pd, pa = a.p1x2
            out += [f"### {m.home} – {m.away}  ·  {_when(m.kickoff)}", ""]
            out.append(f"- **Valós esély:** 1 {_pct(ph)} · X {_pct(pd)} · 2 {_pct(pa)}  "
                       f"(fair szorzó {_odds(1 / ph)} / {_odds(1 / pd)} / {_odds(1 / pa)})")
            out.append(f"- **Forrás:** {', '.join(a.sources)} — bizalom: {a.confidence}; "
                       f"{len(a.book_margins)} iroda, árrés {_pct(min(a.book_margins.values()))}–"
                       f"{_pct(max(a.book_margins.values()))}")
            out.append(f"- **Várható gólok:** {m.home} {a.lam_home:.2f}, {m.away} {a.lam_away:.2f} "
                       f"(összesen {a.lam_home + a.lam_away:.2f}); modell–piac eltérés {_pct(a.fit_error)}")
            out.append(f"- **Mindkét csapat gólt szerez:** {_pct(a.btts)}  ·  "
                       "**Legvalószínűbb eredmények:** "
                       + ", ".join(f"{s} ({_pct(p)})" for s, p in a.top_scores))
            for n in a.notes:
                out.append(f"- ⚠️ {n}")
            out += ["", "| Piac | Tipp | Esély | Fair | Min. szorzó | Forrás |", "|---|---|---|---|---|---|"]
            for s in a.selections:
                out.append(f"| {s.market} | {s.pick} | {_pct(s.prob)} | {_odds(s.fair_odds)} | "
                           f"**{_odds(s.min_odds(strategy))}** | {s.source} |")
            out.append("")
    if not analyses:
        out.append("Nincs elemezhető mérkőzés a megadott időablakban.")
    out += ["---", "**Következő lépés:** nyisd meg a TippmixPro-t, és a "
            f"`{sheet_path}` táblázat `tippmix_szorzo` oszlopába írd be a szorzót azoknál a soroknál, "
            "ahol a Tippmix legalább a min. szorzót adja (a többit hagyd üresen). Ha egy eseménynél a "
            "Tippmix kötést ír elő (pl. csak 2-es kötésben játszható), a `kotes` oszlopba írd a számot. "
            "Utána: `python agent.py szelveny --tabla <fájl> --keret <Ft>`."]
    return "\n".join(out) + "\n"


def _leg_line(l) -> str:
    return (f"{l.match} — **{l.label}** @ {_odds(l.odds)}  (esély {_pct(l.prob)}, "
            f"fair {_odds(1 / l.prob)}, EV {_ev(l.ev)})")


def _bet_block(b, title: str) -> list:
    out = [f"**{title}** — tét {_ft(b.stake)}, eredő szorzó {_odds(b.odds)}, "
           f"nyerési esély {_pct(b.prob)}, lehetséges nyeremény {_ft(b.payout)}, "
           f"várható érték {_ev(b.ev)} ({int(b.stake * b.ev):+d} Ft)"]
    for l in b.legs:
        out.append(f"  - {_leg_line(l)}")
    if b.note:
        out.append(f"  - _{b.note}_")
    return out


def slips(legs, single_bets, skipped, combo_bets, warnings, cap_notes, bankroll, rules, strategy,
          target_odds) -> str:
    out = ["# Szelvényjavaslat", ""]
    out.append(f"Keret: {_ft(bankroll)} · tétméret: {str(strategy.kelly_fraction).replace('.', ',')} × Kelly · "
               f"fogadásonként max. {_pct(strategy.max_bet_share)}, tervenként max. {_pct(strategy.max_daily_share)} · "
               f"TippmixPro: min. tét {_ft(rules.min_stake)}, max. tét {_ft(rules.max_stake)}, "
               f"max. nyeremény {_ft(rules.max_payout)}, max. {rules.max_events} esemény")
    out.append("")
    for w in warnings + cap_notes:
        out.append(f"- ⚠️ {w}")
    value = sorted([l for l in legs if l.qualifies], key=lambda x: -x.ev)
    neg = [l for l in legs if not l.qualifies]
    out += ["", f"## Értékes tippek ({len(value)} / {len(legs)} kitöltött sorból)", ""]
    for l in value:
        out.append(f"- {_leg_line(l)}" + (f" — csak {l.kotes}-es kötésben" if l.kotes > 1 else ""))
    if not value:
        out.append("**Egyik beírt Tippmix-szorzó sem éri el a min. szorzót.** Ilyenkor a helyes döntés "
                   "a kihagyás: minden ilyen tipp hosszú távon veszteséges, a szelvény pedig a lábak "
                   "veszteségét összeszorozza.")
    if neg:
        out += ["", f"<details><summary>{len(neg)} kitöltött sor nem éri el a min. szorzót — kimaradt</summary>", ""]
        for l in sorted(neg, key=lambda x: -x.ev):
            out.append(f"- {_leg_line(l)} — legalább {_odds(l.min_odds)} kellene")
        out += ["", "</details>"]

    out += ["", "## A terv — egyesek (ajánlott)", ""]
    if single_bets:
        for i, b in enumerate(single_bets, 1):
            out += _bet_block(b, f"{i}. szelvény")
        out.append(f"\nÖsszes tét: {_ft(sum(b.stake for b in single_bets))}, várható eredmény: "
                   f"{int(sum(b.stake * b.ev for b in single_bets)):+d} Ft")
    else:
        out.append("Nincs megjátszható egyes.")
    for l, why in skipped:
        out.append(f"- kimaradt: {l.match} {l.label} — {why}")

    title = "## B terv — kötések" + (f" (célszorzó ≥ {_odds(target_odds)})" if target_odds else "")
    out += ["", title, ""]
    if combo_bets:
        for i, b in enumerate(combo_bets, 1):
            out += _bet_block(b, f"{i}. kötés ({len(b.legs)} esemény)")
        out.append("\nA kötés nagyobbat fizet, de ritkábban: ugyanannyi előnyért sokkal nagyobb a szórás.")
    else:
        out.append("Nincs olyan kötés, amely minden feltételnek megfelel"
                   + (" (a célszorzót csak negatív lábakkal lehetne elérni: `--negativ-is`)." if target_odds else "."))
    out += ["", "_Az A és a B terv ugyanazokat a tippeket használja: egyiket játszd meg, ne mindkettőt._"]
    return "\n".join(out) + "\n"

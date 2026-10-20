"""Szelvény építése a Tippmix-szorzókból: várható érték, tét, TippmixPro-korlátok.

Két terv készül, és közülük egyet érdemes megjátszani, nem mindkettőt (ugyanazok
a tippek szerepelnek bennük):
- A terv: egyesek. Matematikailag ez a jobb: a tét tippenként a saját
  előnyéhez igazodik, és egy elrontott tipp nem viszi magával a többit.
- B terv: kötések. Csak pozitív várható értékű lábakból, mert minden negatív
  láb a teljes szelvény várható értékét rontja, akármilyen „biztos".

A kötés esélyét a lábak esélyeinek szorzataként számoljuk: különböző
mérkőzések kimenetelei gyakorlatilag függetlenek. Ugyanabból a meccsből ezért
egy szelvényre legfeljebb egy tipp kerül (a TippmixPro sem engedi a normál
kötésben).
"""
import itertools
import math
from dataclasses import dataclass

from config import Rules, Strategy


@dataclass(frozen=True)
class Leg:
    id: str
    match_id: str
    match: str
    label: str
    prob: float
    odds: float
    kotes: int = 1          # a TippmixPro „kötés" száma: legalább ennyi eseményes szelvényen játszható
    source: str = "piaci"
    min_odds: float = 0.0   # az elemzésben kiírt legkisebb elfogadható szorzó

    @property
    def ev(self) -> float:
        return self.prob * self.odds - 1

    @property
    def qualifies(self) -> bool:
        """Eléri-e a megkövetelt előnyt: a puszta pozitív EV kevés, mert az esély is becslés."""
        return self.odds >= self.min_odds if self.min_odds > 1 else self.ev > 0


@dataclass
class Bet:
    legs: tuple
    stake: int
    note: str = ""

    @property
    def prob(self) -> float:
        return math.prod(l.prob for l in self.legs)

    @property
    def odds(self) -> float:
        return math.prod(l.odds for l in self.legs)

    @property
    def ev(self) -> float:
        return self.prob * self.odds - 1

    @property
    def payout(self) -> int:
        return int(self.stake * self.odds)


def kelly(p: float, o: float) -> float:
    if o <= 1:
        return 0.0
    return max(0.0, (p * o - 1) / (o - 1))


def growth(p: float, o: float, f: float) -> float:
    """Várható logaritmikus keretnövekedés f arányú téttel — ez rangsorolja a kötéseket."""
    if f <= 0:
        return 0.0
    if f >= 1:
        return -math.inf
    return p * math.log1p(f * (o - 1)) + (1 - p) * math.log1p(-f)


def stake_for(p: float, o: float, bankroll: int, rules: Rules, strat: Strategy) -> tuple[int, str]:
    """A tét forintban és egy megjegyzés; 0, ha nem érdemes / nem lehet megjátszani."""
    full = kelly(p, o) * bankroll
    if full <= 0:
        return 0, "nincs előny"
    raw = min(full * strat.kelly_fraction, bankroll * strat.max_bet_share,
              rules.max_stake, rules.max_payout / o)
    stake = int(raw // rules.stake_step * rules.stake_step)
    note = ""
    if stake < rules.min_stake:
        # A minimális tét csak akkor fér bele, ha a teljes Kelly is legalább ennyit mondana,
        # és a keret egy fogadásra szánt része is elbírja.
        if rules.min_stake <= min(full, bankroll * strat.max_bet_share, rules.max_payout / o):
            stake, note = rules.min_stake, "minimális tét (a negyed Kelly kevesebbet mondana)"
        else:
            return 0, "az előny túl kicsi a minimális téthez ekkora keretnél"
    if stake * o > rules.max_payout:
        stake = int(rules.max_payout / o // rules.stake_step * rules.stake_step)
    return stake, note


def singles(legs, bankroll: int, rules: Rules, strat: Strategy) -> tuple[list, list]:
    """Meccsenként a legjobb egy tipp: ugyanarra a meccsre több egyes egymással korrelált kockázat."""
    bets, skipped, taken = [], [], set()
    for l in sorted(legs, key=lambda x: -x.ev):
        if not l.qualifies:
            continue
        if l.match_id in taken:
            skipped.append((l, "erre a meccsre már van nagyobb előnyű tipp a tervben"))
            continue
        if l.kotes > 1:
            skipped.append((l, f"csak legalább {l.kotes}-es kötésben játszható"))
            continue
        stake, note = stake_for(l.prob, l.odds, bankroll, rules, strat)
        if stake:
            bets.append(Bet((l,), stake, note))
            taken.add(l.match_id)
        else:
            skipped.append((l, note))
    return bets, skipped


def combos(legs, bankroll: int, rules: Rules, strat: Strategy, target_odds: float | None = None,
           allow_negative: bool = False, top: int = 3) -> list:
    """A legjobb kötések, meccsenként legfeljebb egy lábbal, és két kötés nem épít ugyanarra a meccsre."""
    pool = [l for l in legs if allow_negative or l.qualifies]
    pool = sorted(pool, key=lambda x: -x.ev)[:strat.max_combo_candidates]
    max_legs = min(strat.max_combo_legs, rules.max_events)
    scored = []
    for n in range(2, max_legs + 1):
        for c in itertools.combinations(pool, n):
            if len({l.match_id for l in c}) < n or any(l.kotes > n for l in c):
                continue
            p = math.prod(l.prob for l in c)
            o = math.prod(l.odds for l in c)
            if target_odds and o < target_odds:
                continue
            ev = p * o - 1
            f = kelly(p, o) * strat.kelly_fraction
            # Pozitív szelvénynél a logaritmikus növekedés dönt (az EV egyedül a hosszú
            # kötéseket jutalmazná); negatívnál a legkisebb várható veszteség.
            key = growth(p, o, f) if ev > 0 else ev - 1
            scored.append((key, c))
    scored.sort(key=lambda x: -x[0])
    out, used = [], set()
    for _, c in scored:
        if used & {l.match_id for l in c}:
            continue
        p = math.prod(l.prob for l in c)
        o = math.prod(l.odds for l in c)
        if p * o > 1:
            stake, note = stake_for(p, o, bankroll, rules, strat)
        elif rules.min_stake * o <= rules.max_payout:
            stake, note = rules.min_stake, "NEGATÍV várható érték — csak a kért célszorzó miatt"
        else:
            stake, note = 0, ""
        if not stake:
            continue
        out.append(Bet(c, stake, note))
        used |= {l.match_id for l in c}
        if len(out) >= top:
            break
    return out


def cap_total(bets: list, bankroll: int, rules: Rules, strat: Strategy) -> tuple[list, list, str]:
    """Egy terv össztétje legfeljebb a keret max_daily_share része; arányosan csökkentünk.

    Visszaad: (megmaradt fogadások, a plafon miatt kiesettek, megjegyzés).
    """
    cap = bankroll * strat.max_daily_share
    total = sum(b.stake for b in bets)
    if total <= cap or not bets:
        return bets, [], ""
    # Arányosan csökkentünk, de ha így bármelyik tét a minimum alá esne, inkább a leggyengébb
    # fogadást ejtjük és újraszámolunk — különben sok kis előnyű tippnél minden tét kiesne.
    ranked = sorted(bets, key=lambda x: -x.ev)
    out = []
    while ranked:
        scale = min(1.0, cap / sum(b.stake for b in ranked))
        out = [Bet(b.legs, int(b.stake * scale // rules.stake_step * rules.stake_step), b.note) for b in ranked]
        if all(b.stake >= rules.min_stake for b in out):
            break
        ranked.pop()
        out = []
    # A kerekítés után is a plafon alatt kell maradni: a leggyengébbet ejtjük, amíg kell.
    while out and sum(b.stake for b in out) > cap:
        out.pop()
    kept = {id(b.legs) for b in out}
    dropped = [b for b in bets if id(b.legs) not in kept]
    return out, dropped, f"az össztétet a napi plafonra ({int(cap)} Ft, a keret {strat.max_daily_share:.0%}-a) csökkentettem"

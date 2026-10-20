"""Egy mérkőzés teljes elemzése: valós esélyek, gólmodell, és a megjátszható tippek.

A piacból számolt tippek (1X2, kétesély, a lekért gólszámvonalak) csak az
árrésmentesítésen múlnak. A modellből számoltak (mindkét csapat gólt szerez,
a nem lekért gólszámvonalak) a Poisson-illesztésen is, ezért külön jelöljük
őket, és több előnyt követelünk hozzájuk.
"""
from dataclasses import dataclass, field

import fair
import poisson
from config import SHARP_BOOKS, Strategy
from odds_api import Match

# Ha a Poisson ennél jobban eltér a piactól, a modellből számolt tippeket nem kínáljuk.
MAX_FIT_ERROR = 0.02
MODEL_LINES = (1.5, 2.5, 3.5)


@dataclass
class Selection:
    market: str     # pl. "1X2", "Kétesély", "Gólszám 2,5", "Mindkét csapat gólt szerez"
    pick: str       # pl. "1", "X2", "Több", "Igen"
    prob: float
    source: str     # "piaci" | "modell"
    confidence: str

    @property
    def fair_odds(self) -> float:
        return 1 / self.prob

    def min_edge(self, s: Strategy) -> float:
        edge = s.min_edge_model if self.source == "modell" else s.min_edge_market
        return edge + (s.low_conf_extra_edge if self.confidence == "alacsony" else 0)

    def min_odds(self, s: Strategy) -> float:
        """A legkisebb Tippmix-szorzó, amelynél a tipp a megkövetelt előnnyel pozitív várható értékű."""
        return (1 + self.min_edge(s)) / self.prob


@dataclass
class Analysis:
    match: Match
    p1x2: list
    confidence: str
    sources: list
    book_margins: dict          # iroda -> árrés az 1X2-n
    totals: dict                # vonal -> (felett esély, bizalom)
    lam_home: float
    lam_away: float
    fit_error: float
    btts: float
    top_scores: list
    selections: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def _line(pt: float) -> str:
    return f"{pt:.1f}".replace(".", ",")


def analyse(m: Match, strategy: Strategy) -> Analysis:
    by_book = {b: fair.devig_power(list(o)) for b, o in m.h2h.items()}
    p1x2, conf, used = fair.consensus(by_book, SHARP_BOOKS)
    margins = {b: fair.overround(list(o)) for b, o in m.h2h.items()}

    totals = {}
    lines = sorted({pt for d in m.totals.values() for pt in d})
    for pt in lines:
        per_book = {b: fair.devig_power(list(d[pt])) for b, d in m.totals.items() if pt in d}
        probs, tconf, _ = fair.consensus(per_book, SHARP_BOOKS)
        totals[pt] = (probs[0], tconf)

    # Az illesztéshez csak a 2,5-ös környéki vonalakat használjuk: a szélső vonalak árrése torzabb.
    fit_overs = {pt: p for pt, (p, _) in totals.items() if 1.5 <= pt <= 3.5}
    lh, la, err = poisson.fit(p1x2, fit_overs)
    mp = poisson.outcome_probs(poisson.score_matrix(lh, la))

    a = Analysis(match=m, p1x2=p1x2, confidence=conf, sources=used, book_margins=margins,
                 totals=totals, lam_home=lh, lam_away=la, fit_error=err, btts=mp["btts"],
                 top_scores=poisson.top_scores(lh, la))

    ph, pd, pa = p1x2
    for pick, p in (("1", ph), ("X", pd), ("2", pa)):
        a.selections.append(Selection("1X2", pick, p, "piaci", conf))
    # A kétesély az 1X2-ből pontosan következik, nem modell.
    for pick, p in (("1X", ph + pd), ("X2", pd + pa), ("12", ph + pa)):
        a.selections.append(Selection("Kétesély", pick, p, "piaci", conf))

    for pt in MODEL_LINES:
        if pt in totals:
            p_over, tconf = totals[pt]
            src = "piaci"
        else:
            p_over, tconf, src = poisson.over_prob(mp["by_total"], pt), conf, "modell"
        if src == "modell" and err > MAX_FIT_ERROR:
            continue
        a.selections.append(Selection(f"Gólszám {_line(pt)}", "Több", p_over, src, tconf))
        a.selections.append(Selection(f"Gólszám {_line(pt)}", "Kevesebb", 1 - p_over, src, tconf))

    if err <= MAX_FIT_ERROR:
        a.selections.append(Selection("Mindkét csapat gólt szerez", "Igen", mp["btts"], "modell", conf))
        a.selections.append(Selection("Mindkét csapat gólt szerez", "Nem", 1 - mp["btts"], "modell", conf))
    else:
        a.notes.append(f"A gólmodell {err:.1%}-kal eltér a piactól: modellből számolt tippet nem adok.")
    if conf == "alacsony":
        a.notes.append("Nincs éles piac (Pinnacle, tőzsde) a forrásban: az esélyek bizonytalanabbak.")
    # Nagyon kis esélyű tippnél a becslés relatív hibája nagy, és a Tippmix ott a legdrágább.
    a.selections = [s for s in a.selections if 0.05 <= s.prob <= 0.97]
    return a

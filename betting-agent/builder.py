"""Fogadásépítős szelvények a legesélyesebb tippekből, a TippmixPro szelvényének mintájára.

Öt stratégia (VERSIONS). A Fogadásépítős változatoknál meccsenként egy csoport:
előbb a győztes, aztán az a gólszám-oldal, amelyik a győztessel EGYÜTT a
legvalószínűbb, végül az a „mindkét csapat szerez gólt" válasz, amelyik
mindezzel együtt a legvalószínűbb. Az
együttes esélyt a meccs gólmodelljének eredménymátrixából számoljuk, így az
összefüggést is figyelembe vesszük (ha a favorit nyer, valószínűbb a több gól).

A csoport szorzóját nem mi számoljuk: azt a TippmixPro Fogadásépítője adja
(bettingOptionsV2 → betBuilderOdds), mert az egy meccsen belüli tippek nem
függetlenek, és a TippmixPro is a saját árával fogadja el. A csoportok egymás
között függetlenek, ezért a szelvény esélye a csoportok esélyének szorzata.
"""
import itertools
import math
from dataclasses import dataclass, field

import names
import poisson

# (név, stratégia, meccsek száma célszorzó nélkül, leírás)
VERSIONS = (
    ("Biztos tippek", "safe", 4, "Meccsenként a legvalószínűbb kétesély: a csapat nyer vagy döntetlen."),
    ("Győztesek", "win", 3, "A legesélyesebb favoritok, meccsenként csak a győztes."),
    ("Győztes + gólok", "win_goals", 3, "Győztes és a vele együtt legvalószínűbb gólszám, Fogadásépítőben."),
    ("Gólos szelvény", "goals", 3, "Győztes nélkül: a legvalószínűbb gólszám és „mindkét csapat szerez gólt” együtt."),
    ("Teljes Fogadásépítő", "full", 2, "Győztes, gólszám és „mindkét csapat szerez gólt”, Fogadásépítőben."),
)
KINDS = {v[1] for v in VERSIONS}
# stratégia → a calibration.json piackulcsa (a „safe" kétesély, a „win" 1X2-tipp)
CAL_KEY = {"safe": "dc", "win": "1x2", "win_goals": "win_goals", "goals": "goals", "full": "full"}
MAX_MATCHES = 6
MIN_GROUP_ODDS = 1.10  # ennél kisebb szorzójú csoport alig ad szorzót, csak egy újabb helyet, ahol a szelvény elbukhat
CANDIDATES = 10  # változatonként ennyi legesélyesebb meccsből válogatunk (a csapatismétlés kiszűr néhányat)


@dataclass
class Group:
    match_id: str
    match: str
    competition: str
    kickoff: str
    picks: list            # outcome dictek a state-ből (id, pick, odds, label…) + "market"
    prob: float            # a csoport együttes esélye
    odds: float | None = None   # a TippmixPro szorzója (egy tippnél a tipp szorzója)
    teams: tuple = ()      # normalizált csapatnevek: egy csapat egy szelvényen csak egyszer


@dataclass
class Version:
    name: str
    desc: str
    groups: list = field(default_factory=list)

    @property
    def odds(self) -> float:
        out = 1.0
        for g in self.groups:
            out *= g.odds or 1.0
        return out

    @property
    def prob(self) -> float:
        out = 1.0
        for g in self.groups:
            out *= g.prob
        return out


def _cond(market: str, pick: str, line):
    if market == "1x2":
        return {"1": lambda i, j: i > j, "X": lambda i, j: i == j, "2": lambda i, j: i < j}[pick]
    if market == "dc":
        return {"1X": lambda i, j: i >= j, "X2": lambda i, j: i <= j, "12": lambda i, j: i != j}[pick]
    if market == "ou":
        return (lambda i, j: i + j > line) if pick == "Több" else (lambda i, j: i + j < line)
    if market == "btts":
        return (lambda i, j: i > 0 and j > 0) if pick == "Igen" else (lambda i, j: i == 0 or j == 0)
    raise ValueError(f"ismeretlen piac: {market}")


def joint_prob(matrix, picks) -> float:
    """A tippek együttes esélye az eredménymátrixból. picks: [(piac, tipp, vonal)]."""
    conds = [_cond(*p) for p in picks]
    n = len(matrix)
    total = sum(matrix[i][j] for i in range(n) for j in range(n))
    hit = sum(matrix[i][j] for i in range(n) for j in range(n) if all(c(i, j) for c in conds))
    return hit / total


def _outcomes(match: dict) -> dict:
    out = {}
    for mk in match["markets"]:
        for o in mk["outcomes"]:
            out[(mk["key"], o["pick"], mk["line"])] = {**o, "market": mk["key"], "market_name": mk["name"],
                                                       "line": mk["line"]}
    return out


def options(match: dict) -> dict:
    """Stratégia → (tippek, együttes esély). Csak a TippmixPro-n kiírt piacokból."""
    a = match.get("analysis")
    if not a:
        return {}
    m = poisson.score_matrix(a["xg_home"], a["xg_away"])
    outs = _outcomes(match)
    res = {}
    pick = lambda keys: [outs[k] for k in keys]  # noqa: E731

    dcs = [k for k in (("dc", "1X", None), ("dc", "X2", None), ("dc", "12", None)) if k in outs]
    if dcs:
        best_dc = max(dcs, key=lambda k: joint_prob(m, [k]))
        res["safe"] = (pick([best_dc]), joint_prob(m, [best_dc]))

    sides = [k for k in (("ou", "Több", 2.5), ("ou", "Kevesebb", 2.5)) if k in outs]
    btts = [k for k in (("btts", "Igen", None), ("btts", "Nem", None)) if k in outs]
    if sides and btts:
        pair = max(((s_, b) for s_ in sides for b in btts), key=lambda kb: joint_prob(m, list(kb)))
        res["goals"] = (pick(pair), joint_prob(m, list(pair)))

    fav = "1" if a["p_home"] >= a["p_away"] else "2"
    if ("1x2", fav, None) not in outs:
        return res
    chosen = [("1x2", fav, None)]
    res["win"] = (pick(chosen), joint_prob(m, chosen))
    if not sides:
        return res
    chosen = chosen + [max(sides, key=lambda k: joint_prob(m, chosen + [k]))]
    res["win_goals"] = (pick(chosen), joint_prob(m, chosen))
    if btts:
        chosen = chosen + [max(btts, key=lambda k: joint_prob(m, chosen + [k]))]
        res["full"] = (pick(chosen), joint_prob(m, chosen))
    return res


def ranked(state: dict, kind: str, cal=None) -> list[Group]:
    """Az adott stratégia csoportjai minden meccsre, a legesélyesebb elöl.

    cal(piackulcs, esély) → visszamért esély (calibration.Calibration.apply); nélküle a nyers esély.
    """
    out = []
    for c in state["competitions"]:
        for match in c["matches"]:
            opt = options(match).get(kind)
            if not opt:
                continue
            picks, prob = opt
            if cal is not None:
                prob = cal(CAL_KEY[kind], prob)
            out.append(Group(match_id=match["id"], match=f"{match['home']} – {match['away']}",
                             competition=c["name"], kickoff=match["kickoff"], picks=picks, prob=prob,
                             odds=picks[0]["odds"] if len(picks) == 1 else None,
                             teams=(names.norm(match["home"]), names.norm(match["away"]))))
    out.sort(key=lambda g: -g.prob)
    return out


def assemble(name: str, desc: str, groups: list, n_default: int, target: float | None,
             min_prob: float | None = None) -> Version | None:
    """A legjobb szelvény a csoportokból (esély szerint csökkenő sorrendben érkeznek).

    - célszorzóval: a LEGNAGYOBB ESÉLYŰ kombináció, amely eléri a célszorzót (és a küszöböt, ha van);
      egyenlőségnél a célhoz közelebbi szorzó. Mohó hozzáadással egy utolsó nagy láb
      jócskán túllőhet a célon, feleslegesen kis eséllyel — ezért pontos keresés.
    - küszöbbel, célszorzó nélkül: a LEGNAGYOBB SZORZÓJÚ kombináció, amelynek esélye még eléri a küszöböt.
    - egyik sem: az n_default legesélyesebb csoport.
    A jelöltek legfeljebb CANDIDATES darabok, a meccsek legfeljebb MAX_MATCHES: ≤ ~850 kombináció.
    """
    pool = [g for g in groups if g.odds is not None and g.odds >= MIN_GROUP_ODDS][:CANDIDATES]
    if target is None and min_prob is None:
        v = Version(name=name, desc=desc)
        used: set = set()
        for g in pool:
            if used & set(g.teams):
                continue  # ugyanaz a csapat két fordulóban: a két láb ugyanazon a formán állna vagy bukna
            v.groups.append(g)
            used |= set(g.teams)
            if len(v.groups) >= n_default:
                break
        return v if v.groups else None

    best_key, best = None, None
    for k in range(1, min(MAX_MATCHES, len(pool)) + 1):
        for combo in itertools.combinations(pool, k):
            teams = [t for g in combo for t in g.teams]
            if len(teams) != len(set(teams)):
                continue
            odds = math.prod(g.odds for g in combo)
            prob = math.prod(g.prob for g in combo)
            if min_prob is not None and prob < min_prob:
                continue
            if target is not None:
                if odds < target:
                    continue
                key = (prob, -odds)
            else:
                key = (odds, prob)
            if best_key is None or key > best_key:
                best_key, best = key, combo
    if best is None:
        return None
    # A szelvényen esély szerinti sorrendben állnak, ahogy a jelöltek is.
    return Version(name=name, desc=desc, groups=sorted(best, key=lambda g: -g.prob))

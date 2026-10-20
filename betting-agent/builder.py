"""Fogadásépítős szelvények a legesélyesebb tippekből, a TippmixPro szelvényének mintájára.

Meccsenként egy csoport (Fogadásépítő): előbb a győztes, aztán az a gólszám-
oldal, amelyik a győztessel EGYÜTT a legvalószínűbb, végül az a „mindkét
csapat szerez gólt" válasz, amelyik mindezzel együtt a legvalószínűbb. Az
együttes esélyt a meccs gólmodelljének eredménymátrixából számoljuk, így az
összefüggést is figyelembe vesszük (ha a favorit nyer, valószínűbb a több gól).

A csoport szorzóját nem mi számoljuk: azt a TippmixPro Fogadásépítője adja
(bettingOptionsV2 → betBuilderOdds), mert az egy meccsen belüli tippek nem
függetlenek, és a TippmixPro is a saját árával fogadja el. A csoportok egymás
között függetlenek, ezért a szelvény esélye a csoportok esélyének szorzata.
"""
from dataclasses import dataclass, field

import names
import poisson

# (név, tippszint meccsenként, meccsek száma célszorzó nélkül, leírás)
VERSIONS = (
    ("Győztesek", 1, 3, "A legesélyesebb favoritok, meccsenként csak a győztes."),
    ("Győztes + gólok", 2, 3, "Győztes és a vele együtt legvalószínűbb gólszám, Fogadásépítőben."),
    ("Teljes Fogadásépítő", 3, 2, "Győztes, gólszám és „mindkét csapat szerez gólt”, Fogadásépítőben."),
)
MAX_MATCHES = 6
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
    """Tippszint (1–3) → (tippek, együttes esély). Csak a TippmixPro-n kiírt piacokból."""
    a = match.get("analysis")
    if not a:
        return {}
    m = poisson.score_matrix(a["xg_home"], a["xg_away"])
    outs = _outcomes(match)
    fav = "1" if a["p_home"] >= a["p_away"] else "2"
    if ("1x2", fav, None) not in outs:
        return {}
    chosen = [("1x2", fav, None)]
    res = {1: ([outs[chosen[0]]], joint_prob(m, chosen))}
    sides = [k for k in (("ou", "Több", 2.5), ("ou", "Kevesebb", 2.5)) if k in outs]
    if not sides:
        return res
    best_side = max(sides, key=lambda k: joint_prob(m, chosen + [k]))
    chosen = chosen + [best_side]
    res[2] = ([outs[k] for k in chosen], joint_prob(m, chosen))
    btts = [k for k in (("btts", "Igen", None), ("btts", "Nem", None)) if k in outs]
    if btts:
        best_b = max(btts, key=lambda k: joint_prob(m, chosen + [k]))
        chosen = chosen + [best_b]
        res[3] = ([outs[k] for k in chosen], joint_prob(m, chosen))
    return res


def ranked(state: dict, level: int) -> list[Group]:
    """Az adott tippszintű csoportok minden meccsre, a legesélyesebb elöl."""
    out = []
    for c in state["competitions"]:
        for match in c["matches"]:
            opt = options(match).get(level)
            if not opt:
                continue
            picks, prob = opt
            out.append(Group(match_id=match["id"], match=f"{match['home']} – {match['away']}",
                             competition=c["name"], kickoff=match["kickoff"], picks=picks, prob=prob,
                             odds=picks[0]["odds"] if len(picks) == 1 else None,
                             teams=(names.norm(match["home"]), names.norm(match["away"]))))
    out.sort(key=lambda g: -g.prob)
    return out


def assemble(name: str, desc: str, groups: list, n_default: int, target: float | None) -> Version | None:
    """A legesélyesebb csoportokból: célszorzó nélkül n_default meccs, célszorzóval addig, amíg el nem éri."""
    v = Version(name=name, desc=desc)
    used_teams: set = set()
    for g in groups:
        if g.odds is None or g.odds <= 1.0:
            continue  # a TippmixPro nem árazta (tiltott vagy nem elérhető) — kimarad
        if used_teams & set(g.teams):
            continue  # ugyanaz a csapat két fordulóban: a két láb ugyanazon a formán állna vagy bukna
        v.groups.append(g)
        used_teams |= set(g.teams)
        if target is None and len(v.groups) >= n_default:
            break
        if target is not None and v.odds >= target:
            break
        if len(v.groups) >= MAX_MATCHES:
            break
    if not v.groups or (target is not None and v.odds < target):
        return None
    return v

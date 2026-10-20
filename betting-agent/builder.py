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


def ranked(state: dict, kind: str) -> list[Group]:
    """Az adott stratégia csoportjai minden meccsre, a legesélyesebb elöl."""
    out = []
    for c in state["competitions"]:
        for match in c["matches"]:
            opt = options(match).get(kind)
            if not opt:
                continue
            picks, prob = opt
            out.append(Group(match_id=match["id"], match=f"{match['home']} – {match['away']}",
                             competition=c["name"], kickoff=match["kickoff"], picks=picks, prob=prob,
                             odds=picks[0]["odds"] if len(picks) == 1 else None,
                             teams=(names.norm(match["home"]), names.norm(match["away"]))))
    out.sort(key=lambda g: -g.prob)
    return out


def assemble(name: str, desc: str, groups: list, n_default: int, target: float | None,
             min_prob: float | None = None) -> Version | None:
    """A legesélyesebb csoportokból.

    - min_prob nélkül, célszorzó nélkül: n_default meccs.
    - célszorzóval: addig vesz hozzá, amíg el nem éri.
    - min_prob-bal: csak addig, amíg a szelvény együttes esélye nem esik alá; célszorzó nélkül
      ezen belül a lehető legtöbb meccs, mert az adja a legnagyobb szorzót ugyanakkora esélyküszöb mellett.
    """
    v = Version(name=name, desc=desc)
    used_teams: set = set()
    for g in groups:
        if g.odds is None or g.odds < MIN_GROUP_ODDS:
            continue  # nem árazott (tiltott, nem elérhető) vagy szinte semmit nem ad — kimarad
        if used_teams & set(g.teams):
            continue  # ugyanaz a csapat két fordulóban: a két láb ugyanazon a formán állna vagy bukna
        if min_prob is not None and v.prob * g.prob < min_prob:
            break  # a csoportok esély szerint csökkenő sorrendben jönnek: a következő sem férne bele
        v.groups.append(g)
        used_teams |= set(g.teams)
        if target is None and min_prob is None and len(v.groups) >= n_default:
            break
        if target is not None and v.odds >= target:
            break
        if len(v.groups) >= MAX_MATCHES:
            break
    if not v.groups or (target is not None and v.odds < target):
        return None
    return v

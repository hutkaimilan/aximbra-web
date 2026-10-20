"""Szelvény célszorzóra, külső valós esély nélkül.

Ha nincs The Odds API-kulcs, a TippmixPro saját szorzóiból becsüljük az
esélyt: piaconként levonjuk az árrést (hatványmódszer). Ez nem ad előnyt —
ugyanannak az irodának az árából nem lehet a saját árát megverni —, de két
dolgot igen: lábanként megmutatja, mennyit vesz el a Tippmix (p·o < 1), és
így a célszorzóhoz azokat a lábakat választhatjuk, ahol ez a legkevesebb. Az
eredmény a „legkevésbé rossz" szelvény az adott szorzóra, és a felület ezt
így is nevezi.

A kétesély kimenetelei átfedik egymást (1X, X2, 12), ezért ott nem árrést
vonunk le, hanem az 1X2 árrésmentes esélyeiből számolunk.
"""
import heapq
import math
from dataclasses import dataclass

import fair

MIN_ODDS = 1.15      # ennél kisebb szorzójú láb szinte semmit nem ad a szelvényhez, csak árrést
MAX_LEGS = 6
POOL = 40            # ennyi legjobb lábból keresünk
PER_MATCH = 2        # meccsenként legfeljebb ennyi jelölt láb a keresésben


@dataclass(frozen=True)
class Cand:
    id: str
    match_id: str
    match: str
    label: str
    odds: float
    prob: float

    @property
    def ratio(self) -> float:
        """p·o: 1 lenne az árrésmentes ár; minél közelebb van hozzá, annál kevesebbet veszít a láb."""
        return self.prob * self.odds

    @property
    def loss(self) -> float:
        """−ln(p·o): a láb árrésvesztesége; a szelvényé a lábaké összeadva."""
        return max(1e-4, -math.log(self.ratio))

    @property
    def efficiency(self) -> float:
        """Mennyi szorzót (ln o) ad a láb egységnyi veszteségért: a célszorzóhoz ez a jó mérce,
        nem a puszta árrés — egy 1,20-as favoritból sok kell, és mindegyik visz el valamennyit."""
        return math.log(self.odds) / self.loss


def candidates(state: dict, max_odds: float) -> list[Cand]:
    out = []
    for c in state["competitions"]:
        for m in c["matches"]:
            name = f"{m['home']} – {m['away']}"
            by_key = {(mk["key"], mk["line"]): mk for mk in m["markets"]}
            p1x2 = None
            if ("1x2", None) in by_key and len(by_key[("1x2", None)]["outcomes"]) == 3:
                outs = by_key[("1x2", None)]["outcomes"]
                try:
                    p1x2 = dict(zip([o["pick"] for o in outs], fair.devig_power([o["odds"] for o in outs])))
                except ValueError:
                    p1x2 = None
            legs = []
            for mk in m["markets"]:
                outs = mk["outcomes"]
                if mk["key"] == "dnb":
                    continue  # döntetlennél visszajár a tét: nem kétkimenetelű fogadás
                if mk["key"] == "dc":
                    if not p1x2:
                        continue
                    probs = {"1X": p1x2["1"] + p1x2["X"], "X2": p1x2["X"] + p1x2["2"], "12": p1x2["1"] + p1x2["2"]}
                    pairs = [(o, probs.get(o["pick"])) for o in outs]
                else:
                    if len(outs) < 2:
                        continue
                    try:
                        ps = fair.devig_power([o["odds"] for o in outs])
                    except ValueError:
                        continue
                    pairs = list(zip(outs, ps))
                for o, p in pairs:
                    if p is None or not MIN_ODDS <= o["odds"] <= max_odds:
                        continue
                    legs.append(Cand(id=o["id"], match_id=m["id"], match=name,
                                     label=f"{mk['name']}: {o['pick']}", odds=o["odds"], prob=p))
            legs.sort(key=lambda x: -x.efficiency)
            out += legs[:PER_MATCH]
    out.sort(key=lambda x: -x.efficiency)
    return out[:POOL]


def search(cands: list[Cand], target: float, max_legs: int = MAX_LEGS, slack: float = 1.35,
           keep: int = 300) -> list[tuple]:
    """A legkisebb összveszteségű lábkombinációk, amelyek eredő szorzója [target, target·slack] közé esik.

    Meccsenként egy láb. Visszaad: [(Π p·o, −lábszám, eredő szorzó, lábak)], a legjobb elöl.
    Ág és korlát: a jelöltek hatékonyság szerint csökkenő sorrendben jönnek, így a még
    hiányzó szorzó legalább (hiányzó ln-szorzó / a következő láb hatékonysága) veszteséggel
    jár — ha ez a már megtalált `keep` legjobb közé sem fér be, az ágat levágjuk.
    """
    cands = sorted(cands, key=lambda c: -c.efficiency)
    lo_t, lo_hi = math.log(target), math.log(target * slack)
    logs = [math.log(c.odds) for c in cands]
    eff = [c.efficiency for c in cands] + [1e-9]
    heap: list = []  # (−veszteség, sorszám, lábak): a tetején a legrosszabb megtartott
    counter = [0]

    def worst():
        return -heap[0][0] if len(heap) >= keep else math.inf

    def dfs(start, chosen, lo, loss, matches):
        if lo >= lo_t:
            counter[0] += 1
            item = (-loss, counter[0], tuple(chosen))
            if len(heap) < keep:
                heapq.heappush(heap, item)
            elif loss < -heap[0][0]:
                heapq.heapreplace(heap, item)
            return  # további láb csak veszteséget és kockázatot adna
        if len(chosen) >= max_legs:
            return
        for i in range(start, len(cands)):
            c = cands[i]
            nlo = lo + logs[i]
            if nlo > lo_hi or c.match_id in matches:
                continue
            nloss = loss + c.loss
            need = max(0.0, lo_t - nlo)
            if nloss + need / eff[i + 1 if i + 1 < len(cands) else -1] >= worst() and need > 0:
                continue
            if nloss >= worst():
                continue
            chosen.append(c)
            matches.add(c.match_id)
            dfs(i + 1, chosen, nlo, nloss, matches)
            matches.discard(c.match_id)
            chosen.pop()

    dfs(0, [], 0.0, 0.0, set())
    out = []
    for _, _, legs in heap:
        # A rangsorhoz a levágott veszteség kell (a nullánál nem kisebb), a kiírt érték viszont a tényleges Π p·o.
        out.append((math.prod(c.ratio for c in legs), -len(legs), math.prod(c.odds for c in legs), legs))
    out.sort(key=lambda f: (-f[0], -f[1]))
    return out


def pick_disjoint(found: list[tuple], n: int = 3) -> list[tuple]:
    """A legjobb n kombináció, amelyek nem építenek ugyanarra a meccsre."""
    out, used = [], set()
    for f in found:
        ms = {c.match_id for c in f[3]}
        if ms & used:
            continue
        out.append(f)
        used |= ms
        if len(out) >= n:
            break
    return out

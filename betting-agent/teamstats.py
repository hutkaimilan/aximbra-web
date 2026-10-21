"""Szöglet- és lapmodell csapatszinten, a football-data.co.uk meccsadataiból.

Egy meccs várható szöglete (és lapja) hazai és vendég oldalon külön:

    hazai = bajnoki hazai átlag × hazai csapat támadó szorzója (otthon) × vendég csapat engedő szorzója (idegenben)

A szorzók a csapat átlaga osztva a bajnoki átlaggal, kevés meccsnél 1 felé húzva
(SHRINK meccsnyi „bajnoki átlag" hozzáadásával), az előző évad fél súllyal. Az összeg
eloszlása negatív binomiális: a szöglet és a lap szóródása nagyobb a Poissonénál; a
diszperziót a calibrate.py becsüli, és a calibration.json-ba írja.

Csak a négy hazai bajnokság csapataira működik (PL, La Liga, Bundesliga, portugál liga);
BL/EL-meccsnél akkor, ha mindkét csapat ezekből való. Más csapatnál nincs becslés.
"""
import math
from dataclasses import dataclass, field

SHRINK = 5.0
PREV_WEIGHT = 0.5
# minden lap egynek számít (sárga + piros), ahogy a football-data is: a TippmixPro második sárgánál eltérhet
STATS = {"corners": ("HC", "AC"), "cards": (("HY", "HR"), ("AY", "AR"))}


def _val(row: dict, cols) -> float | None:
    cols = cols if isinstance(cols, tuple) else (cols,)
    try:
        return float(sum(int(row[c]) for c in cols))
    except (KeyError, ValueError, TypeError):
        return None


@dataclass
class _Acc:
    """Súlyozott összegek: (összeg, súly)."""
    s: float = 0.0
    w: float = 0.0

    def add(self, x: float, w: float):
        self.s += x * w
        self.w += w

    def mean(self, default: float) -> float:
        return self.s / self.w if self.w else default


@dataclass
class LeagueStats:
    """Egy bajnokság csapatai egy statisztikára (szöglet vagy lap)."""
    home_for: dict = field(default_factory=dict)      # csapat → otthon szerzett
    home_against: dict = field(default_factory=dict)  # csapat → otthon engedett
    away_for: dict = field(default_factory=dict)
    away_against: dict = field(default_factory=dict)
    league_home: _Acc = field(default_factory=_Acc)
    league_away: _Acc = field(default_factory=_Acc)

    def add(self, home: str, away: str, h: float, a: float, w: float):
        for d, team, x in ((self.home_for, home, h), (self.home_against, home, a),
                           (self.away_for, away, a), (self.away_against, away, h)):
            d.setdefault(team, _Acc()).add(x, w)
        self.league_home.add(h, w)
        self.league_away.add(a, w)

    def _ratio(self, d: dict, team: str, league_mean: float) -> float:
        acc = d.get(team)
        if not acc or not league_mean:
            return 1.0
        # 1 felé húzva: SHRINK meccsnyi bajnoki átlag hozzáadva
        return (acc.s + SHRINK * league_mean) / (acc.w + SHRINK) / league_mean

    def expected(self, home: str, away: str) -> tuple[float, float] | None:
        if home not in self.home_for or away not in self.away_for:
            return None
        lh, la = self.league_home.mean(0.0), self.league_away.mean(0.0)
        if not lh or not la:
            return None
        eh = lh * self._ratio(self.home_for, home, lh) * self._ratio(self.away_against, away, lh)
        ea = la * self._ratio(self.away_for, away, la) * self._ratio(self.home_against, home, la)
        return eh, ea

    @property
    def teams(self) -> set:
        return set(self.home_for) | set(self.away_for)


def build(rows_current: list[dict], rows_prev: list[dict]) -> dict:
    """{statisztika: LeagueStats} egy bajnokságra: az aktuális évad teljes, az előző fél súllyal."""
    out = {k: LeagueStats() for k in STATS}
    for rows, w in ((rows_prev, PREV_WEIGHT), (rows_current, 1.0)):
        for r in rows:
            home, away = r.get("HomeTeam"), r.get("AwayTeam")
            if not home or not away:
                continue
            for key, (hc, ac) in STATS.items():
                h, a = _val(r, hc), _val(r, ac)
                if h is not None and a is not None:
                    out[key].add(home, away, h, a, w)
    return out


def actual(row: dict, key: str) -> float | None:
    hc, ac = STATS[key]
    h, a = _val(row, hc), _val(row, ac)
    return None if h is None or a is None else h + a


# --- negatív binomiális ---

def nb_pmf(k: int, mu: float, r: float) -> float:
    """P(X = k), átlag mu, diszperzió r (Var = mu + mu²/r); r → ∞ a Poisson."""
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    if r >= 1e6:
        return math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1))
    p = r / (r + mu)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1) + r * math.log(p) + k * math.log1p(-p))


def over_prob(mu: float, r: float, line: float) -> float:
    """P(összeg > line), x,5-ös vonalra."""
    upto = int(math.floor(line))
    return max(0.0, min(1.0, 1.0 - sum(nb_pmf(k, mu, r) for k in range(upto + 1))))


def fit_dispersion(pairs: list[tuple[float, float]]) -> float:
    """Momentumbecslés: (várható, valós) párokból r, hogy Var(valós − várható) ≈ mu + mu²/r."""
    if len(pairs) < 50:
        return 1e6
    excess = sum((y - m) ** 2 - m for m, y in pairs)
    denom = sum(m * m for m, _ in pairs)
    if excess <= 0 or denom <= 0:
        return 1e6  # nincs túlszóródás: Poisson
    return max(1.0, denom / excess)

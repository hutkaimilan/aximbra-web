"""A TippmixPro szabályai és a stratégia paraméterei, környezeti változóból felülírhatóan.

A minimális tétet a TippmixPro szelvény-ellenőrzője maga visszaadja. A többi
számot nyilvános összefoglalókból vettük (2018-as részvételi szabályzat,
2026-os cikkek), és ahol a források eltérnek, a szigorúbbat választottuk:
egy túl szigorú korlát legfeljebb kihagy egy szelvényt, egy túl laza viszont
olyat ajánl, amit a TippmixPro nem fogad el. A hivatalos szabályzatban
érdemes egyszer ellenőrizni őket, és eltérés esetén itt átírni.
"""
import os
from dataclasses import dataclass


def _num(name: str, default, cast):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return cast(raw.strip().replace(",", "."))
    except ValueError as e:
        raise ValueError(f"{name}={raw!r} nem szám") from e


@dataclass(frozen=True)
class Rules:
    # A TippmixPro szelvény-ellenőrzője maga adja vissza (minStake: 100); a webes felület onnan olvassa.
    min_stake: int = 100          # Ft, kombinációnként
    max_stake: int = 100_000      # Ft, egységnyi fogadásonként
    # A 2018-as szabályzat 1 000 000 Ft-ot ír, egy újabb forrás 2 000 000-et: a kisebbel számolunk.
    max_payout: int = 1_000_000   # Ft, egységnyi fogadásonként
    max_events: int = 20          # esemény egy szelvényen
    stake_step: int = 100         # a téteket erre kerekítjük lefelé


@dataclass(frozen=True)
class Strategy:
    min_edge_market: float = 0.03      # piacból számolt esélynél ennyi előny kell (3%)
    min_edge_model: float = 0.06       # Poisson-modellből számolt piacnál több, mert a modellnek is van hibája
    low_conf_extra_edge: float = 0.02  # ha nincs éles iroda (Pinnacle, tőzsde) a forrásban
    kelly_fraction: float = 0.25       # negyed Kelly: a teljes Kelly a becslési hiba mellett túl agresszív
    max_bet_share: float = 0.02        # egy fogadásra legfeljebb a keret 2%-a
    max_daily_share: float = 0.05      # egy tervre összesen legfeljebb a keret 5%-a
    max_combo_legs: int = 4
    max_combo_candidates: int = 18     # ennyi lábból keresünk kötést (C(18,4)=3060 kombináció)
    max_age_hours: float = 6.0         # ennél régebbi elemzésre nem építünk szelvényt
    days_ahead: int = 4


def load_rules() -> Rules:
    return Rules(
        min_stake=_num("TIPPMIX_MIN_STAKE", Rules.min_stake, int),
        max_stake=_num("TIPPMIX_MAX_STAKE", Rules.max_stake, int),
        max_payout=_num("TIPPMIX_MAX_PAYOUT", Rules.max_payout, int),
        max_events=_num("TIPPMIX_MAX_EVENTS", Rules.max_events, int),
        stake_step=_num("TIPPMIX_STAKE_STEP", Rules.stake_step, int),
    )


def load_strategy() -> Strategy:
    s = Strategy(
        min_edge_market=_num("BET_MIN_EDGE_MARKET", Strategy.min_edge_market, float),
        min_edge_model=_num("BET_MIN_EDGE_MODEL", Strategy.min_edge_model, float),
        low_conf_extra_edge=_num("BET_LOW_CONF_EXTRA_EDGE", Strategy.low_conf_extra_edge, float),
        kelly_fraction=_num("BET_KELLY_FRACTION", Strategy.kelly_fraction, float),
        max_bet_share=_num("BET_MAX_BET_SHARE", Strategy.max_bet_share, float),
        max_daily_share=_num("BET_MAX_DAILY_SHARE", Strategy.max_daily_share, float),
        max_combo_legs=_num("BET_MAX_COMBO_LEGS", Strategy.max_combo_legs, int),
        max_combo_candidates=_num("BET_MAX_COMBO_CANDIDATES", Strategy.max_combo_candidates, int),
        max_age_hours=_num("BET_MAX_AGE_HOURS", Strategy.max_age_hours, float),
        days_ahead=_num("BET_DAYS_AHEAD", Strategy.days_ahead, int),
    )
    if not 0 < s.kelly_fraction <= 1:
        raise ValueError("BET_KELLY_FRACTION 0 és 1 közé essen")
    if not 0 < s.max_bet_share <= s.max_daily_share <= 1:
        raise ValueError("BET_MAX_BET_SHARE ≤ BET_MAX_DAILY_SHARE ≤ 1 kell")
    if not 2 <= s.max_combo_legs <= 8:
        raise ValueError("BET_MAX_COMBO_LEGS 2 és 8 közé essen")
    return s


# A The Odds API bajnokság-kulcsai.
LEAGUES = {
    "soccer_uefa_champs_league": "Bajnokok Ligája",
    "soccer_uefa_europa_league": "Európa-liga",
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_portugal_primeira_liga": "Portugál bajnokság",
}

# Éles (alacsony árrésű, gyorsan korrigáló) piacok: ezek árából számolunk valós esélyt.
SHARP_BOOKS = ("pinnacle", "betfair_ex_eu", "matchbook")
# Tíz iroda egy régiónak számít a kvótában, ezért pont tízet kérünk.
DEFAULT_BOOKMAKERS = (
    "pinnacle,betfair_ex_eu,matchbook,unibet_eu,williamhill,"
    "marathonbet,onexbet,sport888,betsson,nordicbet"
)

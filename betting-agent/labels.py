"""Emberi nyelvű tippek: „Lens nyer", „Legalább 3 gól", „Mindkét csapat lő gólt" — kódok („1X2: 2") helyett."""


def _goals(line: float, over: bool) -> str:
    n = int(line + 0.5)  # 2,5 → 3
    return f"Legalább {n} gól" if over else f"Legfeljebb {n - 1} gól"


def _ln(x: float) -> str:
    return f"{x:+g}".replace(".", ",")


def short(market: str, pick: str, home: str, away: str, line: float | None = None) -> str:
    """A tipp neve úgy, ahogy a TippmixPro szelvényén áll („Real Madrid", „Több, mint 2,5", „Igen")."""
    if market in ("1x2", "dnb", "ht1x2"):
        return {"1": home, "X": "Döntetlen", "2": away}[pick]
    if market == "hcp":
        h = line or 0.0
        return {"1": f"{home} ({_ln(h)})", "X": f"Döntetlen - ({away} {_ln(-h)})", "2": f"{away} ({_ln(-h)})"}[pick]
    if market == "htou":
        ln = str(line or 0.5).replace(".", ",")
        return f"Több, mint {ln}" if pick == "Több" else f"Kevesebb, mint {ln}"
    if market == "dc":
        return {"1X": f"{home} vagy döntetlen", "X2": f"{away} vagy döntetlen", "12": f"{home} vagy {away}"}[pick]
    if market == "ou":
        ln = str(line or 2.5).replace(".", ",")
        return f"Több, mint {ln}" if pick == "Több" else f"Kevesebb, mint {ln}"
    if market == "btts":
        return "Igen" if pick == "Igen" else "Nem"
    return pick


def sentence(market: str, pick: str, home: str, away: str, line: float | None = None) -> str:
    """A szelvényen és a javaslatokban álló teljes mondat."""
    if market == "1x2":
        return {"1": f"{home} nyer", "X": "Döntetlen lesz", "2": f"{away} nyer"}[pick]
    if market == "dnb":
        team = home if pick == "1" else away
        return f"{team} nyer (döntetlennél visszajár a tét)"
    if market == "dc":
        return {"1X": f"{home} nem kap ki (nyer vagy döntetlen)", "X2": f"{away} nem kap ki (nyer vagy döntetlen)",
                "12": "Nem lesz döntetlen (valamelyik csapat nyer)"}[pick]
    if market == "ou":
        return _goals(line or 2.5, pick == "Több") + " lesz a meccsen"
    if market == "btts":
        return "Mindkét csapat lő gólt" if pick == "Igen" else "Legalább az egyik csapat nem lő gólt"
    if market == "ht1x2":
        return {"1": f"Az 1. félidőben {home} vezet", "X": "Az 1. félidő döntetlen",
                "2": f"Az 1. félidőben {away} vezet"}[pick]
    if market == "htou":
        n = int((line or 0.5) + 0.5)
        if pick == "Több":
            return f"Legalább {n} gól az 1. félidőben"
        return "Gól nélküli 1. félidő" if n == 1 else f"Legfeljebb {n - 1} gól az 1. félidőben"
    if market == "hcp":
        return _hcp_sentence(pick, home, away, line or 0.0)
    return pick


def _hcp_sentence(pick: str, home: str, away: str, h: float) -> str:
    """Háromesélyes hendikep a hazai vonal (h) szerint: hazai nyer, ha gólkülönbség + h > 0."""
    k = int(abs(h))
    if h < 0:  # a hazai a favorit, k gól előnyt ad
        return {"1": f"{home} legalább {k + 1} góllal nyer", "X": f"{home} pontosan {k} góllal nyer",
                "2": f"{home} nem nyer" if k == 1 else f"{home} legfeljebb {k - 1} góllal nyer, vagy nem nyer"}[pick]
    return {"1": f"{home} nem kap ki" if k == 1 else f"{away} legfeljebb {k - 1} góllal nyer, vagy nem nyer",
            "X": f"{away} pontosan {k} góllal nyer", "2": f"{away} legalább {k + 1} góllal nyer"}[pick]

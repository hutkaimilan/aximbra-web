"""Emberi nyelvű tippek: „Lens nyer", „Legalább 3 gól", „Mindkét csapat lő gólt" — kódok („1X2: 2") helyett."""


def _goals(line: float, over: bool) -> str:
    n = int(line + 0.5)  # 2,5 → 3
    return f"Legalább {n} gól" if over else f"Legfeljebb {n - 1} gól"


def short(market: str, pick: str, home: str, away: str, line: float | None = None) -> str:
    """A tipp neve úgy, ahogy a TippmixPro szelvényén áll („Real Madrid", „Több, mint 2,5", „Igen")."""
    if market in ("1x2", "dnb"):
        return {"1": home, "X": "Döntetlen", "2": away}[pick]
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
    return pick

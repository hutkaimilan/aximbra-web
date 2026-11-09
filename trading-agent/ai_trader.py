"""AI-kereskedő: óránként az AI dönt, mit vegyen és mit adjon el — mint egy ember.

A megbízó kérése: aktív, napi kereskedés, korlátok nélkül. Amit a kód ennek ellenére betart:
- csak a figyelt listából, csak a meglévő készpénzből vásárol (a számla összege a valóság, nem korlát);
- minden vételhez stop tartozik, amit az AI ad meg (2–15%), és ami a nyerőknél felfelé követ;
- tőzsdén kívüli időben (hétvége, éjszaka) részvényt, indexet, nyersanyagot nem köt: a régi árat
  hétfőn már nem lehetne valós áron teljesíteni.
Ez a döntési mód visszamenőleg nem tesztelhető; az eredményét a napló és a felület méri.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import strategy
from llm import LLMError, extract_json
from market import MarketError

logger = logging.getLogger(__name__)

SYSTEM = (
    "Tapasztalt, aktív, bátor kereskedő vagy, aki egy játékpénzes számlát kezel. Célod a lehető legnagyobb nyereség, "
    "aktív napi kereskedéssel: naponta több vételt és eladást is csinálsz, a pozíciókat jellemzően 1–5 napig tartod. "
    "Dönthetsz a trend, a lendület, a túladott visszapattanás és a hírek alapján. Vágd le gyorsan a vesztes pozíciókat, "
    "a nyerőket hagyd futni, és ha egy pozíció célja teljesült vagy a helyzet megváltozott, add el. "
    "Csak a megadott adatokra támaszkodj, ne találj ki árat vagy hírt. Válaszolj KIZÁRÓLAG JSON-nal."
)


def market_open(cls: str, now: datetime) -> bool:
    if cls == "crypto":
        return True
    if now.weekday() >= 5:
        return False
    return 7 <= now.hour < 21          # európai és amerikai kereskedési idő (UTC) nagyjából


def snapshot(agent, cls_of) -> dict:
    rows, held = [], {p.symbol: p for p in agent.store.open_positions()}
    now = datetime.now(timezone.utc)
    for sym in agent.cfg.symbols:
        try:
            c = agent.market.candles(sym, agent.cfg.interval, limit=260)
            price = agent.market.price(sym)
        except MarketError:
            continue
        if len(c) < 60:
            continue
        ind = strategy.compute(c)
        cl = [x.close for x in c]
        r200 = ind["regime"][-1]
        row = {"jel": sym, "név": agent.name_of(sym), "osztály": cls_of(sym), "ár": round(price, 6),
               "kereskedhető_most": market_open(cls_of(sym), now),
               "változás_1": round((price / cl[-2] - 1) * 100, 2), "változás_5": round((price / cl[-6] - 1) * 100, 2),
               "változás_20": round((price / cl[-21] - 1) * 100, 2),
               "trend_ema200_felett": bool(r200 and price > r200), "ema20_ema50_felett": bool(ind["fast"][-1] > ind["slow"][-1]),
               "rsi14": round(ind["rsi"][-1] or 0, 1), "atr_százalék": round((ind["atr"][-1] or 0) / price * 100, 2)}
        p = held.get(sym)
        if p:
            row["pozíció"] = {"irány": "long" if p.side == 1 else "short", "belépés": p.entry_price,
                              "eredmény_százalék": round(p.side * (price / p.entry_price - 1) * 100, 2),
                              "stop": p.stop, "nyitva_óta": p.opened_at}
        rows.append(row)
    return {"gyertya": agent.cfg.interval, "piacok": rows}


def owner_notes(agent) -> list[str]:
        """A megbízó chatüzenetei az utolsó 24 órából (a parancsok nélkül)."""
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))
        store = agent.radar.store if agent.radar is not None else agent.store
        with store._lock:
            rows = store._conn.execute("SELECT content FROM chat WHERE role = 'user' AND created_at >= ? "
                                       "ORDER BY id DESC LIMIT 10", (cutoff,)).fetchall()
        return [r["content"][:300] for r in rows if not r["content"].startswith("/")]


def decide(agent, cls_of, news: list[dict]) -> dict:
    snap = snapshot(agent, cls_of)
    eq = agent.equity({r["jel"]: r["ár"] for r in snap["piacok"]})
    acct = {"számla_érték": round(eq, 2), "szabad_készpénz": round(agent.store.cash(), 2),
            "nyitott_pozíciók": len(agent.store.open_positions()),
            "esésre_fogadhat": not agent.executor.live}
    prompt = (
        f"Számla: {json.dumps(acct, ensure_ascii=False)}\n"
        f"Piacok (változás %-ban, '{snap['gyertya']}' gyertyákon): {json.dumps(snap['piacok'], ensure_ascii=False)}\n"
        f"Friss hírek: {json.dumps(news, ensure_ascii=False)}\n"
        f"Milán (a megbízó) üzenetei az elmúlt 24 órából — ha hírt vagy tippet ad, vedd komolyan, de ne vakon: "
        f"{json.dumps(owner_notes(agent), ensure_ascii=False)}\n\n"
        "Döntsd el, mit csinálsz MOST. Lehetséges lépések:\n"
        '- {"lépés":"vesz","jel":"...","összeg_százalék":5-40,"stop_százalék":2-15,"ok":"egy mondat magyarul"}\n'
        '- {"lépés":"elad","jel":"...","ok":"..."}  (csak nyitott long pozícióra)\n'
        + ('- {"lépés":"short","jel":"...","összeg_százalék":5-30,"stop_százalék":2-15,"ok":"..."} (esésre fogadás)\n'
           '- {"lépés":"fedez","jel":"...","ok":"..."} (short zárása)\n' if not agent.executor.live else "")
        + "Csak 'kereskedhető_most': true piacon köss. Aktív kereskedő vagy: ha van értelmes lehetőség, lépj; "
          "ha egy pozíció rosszul áll vagy a célja megvan, add el. Az összeg a számla értékének százaléka, "
          "és nem lehet több a szabad készpénznél.\n"
          'Válasz: {"lépések":[...], "összefoglaló":"2-3 mondat magyarul: mit látsz a piacon és mit miért csinálsz"}')
    fast = [m.strip() for m in os.environ.get("GEMINI_TRADER_MODELS",
                                              "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash,gemini-flash-latest").split(",")]
    raw = agent.llm.ask(prompt, system=SYSTEM, models=fast, timeout=60)
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("a döntés nem objektum")
    return data


def run_once(agent, cls_of, news_fn) -> str:
    """Egy döntési kör: AI-döntés, végrehajtás, beszámoló. Visszaadja az összefoglalót."""
    if agent.llm is None:
        return "nincs AI"
    try:
        data = decide(agent, cls_of, news_fn())
    except (LLMError, ValueError) as e:
        logger.warning("%s: az AI-kereskedő most nem döntött: %s", agent.label, e)
        return ""
    now = datetime.now(timezone.utc)
    done = []
    for step in (data.get("lépések") or [])[:12]:
        try:
            kind = str(step.get("lépés", "")).lower()
            sym = str(step.get("jel", "")).strip()
            reason = str(step.get("ok", ""))[:200]
            if sym not in agent.cfg.symbols:
                continue
            if kind in ("vesz", "short") and not market_open(cls_of(sym), now):
                done.append(f"⏸ {agent.name_of(sym)}: zárva a piac, kihagyva")
                continue
            if kind in ("vesz", "short"):
                side = 1 if kind == "vesz" else -1
                if side == -1 and agent.executor.live:
                    continue
                pct = max(1.0, min(100.0, float(step.get("összeg_százalék", 10))))
                stop_pct = max(1.0, min(25.0, float(step.get("stop_százalék", 5))))
                done.append(agent.ai_entry(sym, side, pct / 100, stop_pct / 100, reason))
            elif kind in ("elad", "fedez"):
                pos = agent.store.open_position_for(sym)
                if pos is not None:
                    done.append(agent.manual_exit(sym, reason=f"AI-döntés: {reason}"))
        except (TypeError, ValueError) as e:
            logger.warning("hibás AI-lépés kihagyva (%s): %s", e, step)
    summary = str(data.get("összefoglaló", ""))[:600]
    agent.notify(f"🧠 AI-kereskedő ({agent.label.split('—')[0].strip()})\n{summary}"
                 + ("\n" + "\n".join(f"• {d}" for d in done if d) if done else "\nMost nem kötöttem."),
                 email=False, kind="ai", push=None)
    agent.store.set("ai_last", json.dumps({"ts": int(time.time()), "summary": summary, "done": done}, ensure_ascii=False))
    return summary

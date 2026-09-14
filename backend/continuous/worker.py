"""A kétóránkénti futás.

Mit csinál egy futás:

  1. sorra veszi a fiókokat, amelyek esedékesek (két óra telt el, nincs
     szüneteltetve, és nem bukott el túl sokszor egymás után);
  2. a tárolt refresh tokenből friss hozzáférést kér a Google-tól;
  3. **első alkalommal** visszanéz öt hónapot, utána csak azt, ami a legutóbbi
     futás óta érkezett — a Gmail `historyId`-ja pontosan erre való;
  4. osztályozza az új leveleket ugyanazzal az osztályozóval, ami a demóban fut;
  5. elmenti a megállapítást, és megjegyzi, hol tartott.

Amit szándékosan nem csinál:

  * nem ír a postafiókba — ez a modul olvasásra kapott jogot, a válaszírás az
    ügyfél kezében marad, ugyanúgy, ahogy a demóban;
  * nem törli és nem címkézi a leveleket;
  * nem küld semmit sehova; a megállapítást az ügyfél saját felülete mutatja.

Hibatűrés: egy visszavont hozzáférés vagy egy elérhetetlen Google nem állítja
meg a többi fiókot, és nem is pörög újra kétpercenként — a sorozatos hibák
után a fiók hátrébb sorolódik, és a hiba oka odakerül a fiók mellé.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Kétóránként. A postafiók nem változik olyan gyorsan, hogy sűrűbben érné meg,
# és minden futás Gmail- és modellhívásokba kerül.
INTERVAL_MINUTES = int(os.environ.get("CONTINUOUS_INTERVAL_MINUTES") or 120)
# Az első futás ennyit néz vissza. Öt hónap: ami ennél régebbi, az ritkán él még.
BACKFILL_MONTHS = int(os.environ.get("CONTINUOUS_BACKFILL_MONTHS") or 5)
# Egy futásban ennyi levelet dolgozunk fel, hogy egy évekre visszanyúló első
# pásztázás ne fusson órákig és ne égesse el a napi keretet.
MAX_PER_RUN = int(os.environ.get("CONTINUOUS_MAX_PER_RUN") or 120)
RUN_CONCURRENCY = 5
# Ennyi egymás utáni hiba után a fiók szünetel, amíg valaki rá nem néz.
MAX_FAILURES = 5


def is_enabled() -> bool:
    return (os.environ.get("CONTINUOUS_ENABLED") or "").strip().lower() in ("1", "true", "yes")


def due_accounts(accounts: list, now: datetime | None = None, interval_minutes: int | None = None) -> list:
    """Melyik fiók esedékes most.

    Külön függvény, mert ez a logika az, ami csendben elromlik: egy rossz
    összehasonlítás vagy egy időzóna nélküli dátum mellett vagy sosem fut,
    vagy percenként fut.
    """
    now = now or datetime.now(timezone.utc)
    interval = timedelta(minutes=interval_minutes or INTERVAL_MINUTES)
    due = []
    for a in accounts:
        if a.get("paused") or (a.get("failures") or 0) >= MAX_FAILURES:
            continue
        last = a.get("last_run_at")
        if not last:
            due.append(a)
            continue
        try:
            when = datetime.fromisoformat(last)
        except ValueError:
            due.append(a)
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if now - when >= interval:
            due.append(a)
    return due


def backfill_query(now: datetime | None = None, months: int | None = None) -> str:
    """A Gmail keresőkifejezése az első pásztázáshoz."""
    now = now or datetime.now(timezone.utc)
    days = int((months or BACKFILL_MONTHS) * 30.44)
    after = int((now - timedelta(days=days)).timestamp())
    return f"after:{after}"


async def run_account(account: dict, store, gmail, classify, lang: str = "hu") -> dict:
    """Egy fiók egy futása. A Gmail-hozzáférést és az osztályozót kívülről kapja,
    hogy a logika hálózat nélkül is tesztelhető legyen."""
    account_id = account["id"]
    first_run = not account.get("history_id")
    try:
        if first_run:
            ids, history_id = await gmail.list_since(query=backfill_query(), limit=MAX_PER_RUN)
        else:
            ids, history_id = await gmail.list_new(account["history_id"], limit=MAX_PER_RUN)
    except Exception as e:  # noqa - visszavont jog, hálózat, kvóta
        logger.warning("continuous: listing failed for %s: %s", account_id, type(e).__name__)
        store.mark_run(account_id, error=f"{type(e).__name__}: {e}"[:300])
        return {"account": account_id, "new": 0, "error": type(e).__name__}

    # Amit már láttunk, nem osztályozzuk újra: az fölösleges modellhívás lenne.
    known = store.known_message_ids(account_id)
    todo = [mid for mid in ids if mid not in known][:MAX_PER_RUN]

    gate = asyncio.Semaphore(RUN_CONCURRENCY)
    findings: list = []
    halted: dict = {"why": None}

    async def one(mid: str):
        if halted["why"]:
            return
        async with gate:
            if halted["why"]:
                return
            try:
                email = await gmail.fetch(mid)
                verdict = await classify(email, lang)
                findings.append({**email, **verdict})
            except Exception as e:  # noqa
                # A napi keret elfogyása az egyetlen, ami az egész futást megállítja;
                # egy hibás levél nem viheti el a többit.
                if "429" in str(e) or "keret" in str(e).lower() or "budget" in str(e).lower():
                    halted["why"] = "budget"
                else:
                    logger.info("continuous: message %s failed: %s", mid, type(e).__name__)

    await asyncio.gather(*(one(mid) for mid in todo))
    saved = store.save_findings(account_id, findings)
    # A history_id csak akkor lép előre, ha a futás nem akadt el — különben a
    # kihagyott levelek soha többé nem kerülnének elő.
    if not halted["why"] and history_id:
        store.set_history_id(account_id, history_id)
    store.mark_run(account_id, error="napi keret elfogyott" if halted["why"] else None)
    return {"account": account_id, "new": saved, "scanned": len(todo),
            "first_run": first_run, "halted": halted["why"]}


async def run_once(store, gmail_for, classify, now: datetime | None = None) -> list:
    """Egy kör az összes esedékes fiókon. A fiókok egymás után futnak: a
    párhuzamosság a leveleken belül van, és két fiók egyszerre futtatása csak
    a Google kvótáját feszítené."""
    out = []
    for account in due_accounts(store.accounts(), now=now):
        gmail = gmail_for(account)
        out.append(await run_account(account, store, gmail, classify))
    return out


async def loop(store, gmail_for, classify, tick_seconds: int = 300, stop: asyncio.Event | None = None):
    """A háttérben futó kör. Nem az intervallumot alszik végig: gyakrabban
    ébred, és megnézi, ki esedékes — így egy újonnan csatlakozott fiók nem vár
    két órát az első futására."""
    stop = stop or asyncio.Event()
    while not stop.is_set():
        try:
            results = await run_once(store, gmail_for, classify)
            if results:
                logger.info("continuous: %d account(s) processed", len(results))
        except Exception:  # noqa - a kör soha ne haljon meg csendben
            logger.exception("continuous: run failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
        except asyncio.TimeoutError:
            pass

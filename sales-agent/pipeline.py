"""A munkafolyamat: keresés → ellenőrzés → levélírás → (ember jóváhagy) →
küldés → válaszfigyelés → egy utánkövetés.

A külső függőségek (modell, levelezés, letöltés) paraméterként jönnek, így
a teljes folyamat hálózat nélkül tesztelhető.
"""
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import json

import calendar_slots
import llm as llm_mod
import mailer as mailer_mod
import verify
from playbook import COUNTRIES, FOLLOW_UP, OPT_OUT, SECTORS, SIGNAL_TYPES
from store import Store, domain_of

logger = logging.getLogger(__name__)

DAILY_CAP = 25          # új levél + utánkövetés együtt, naponta
MAX_PER_RUN = 20        # egy kereséssel legfeljebb ennyi vázlat
BATCH = 6               # egy modellhívásban ennyi céget kérünk
FOLLOWUP_AFTER_WORKDAYS = 5
SEND_GAP = (25, 70)     # másodperc két levél között: nem egyszerre zúdul ki
MIN_SCORE = 70          # ennél gyengébb illeszkedésre nem pazarolunk levelet


@dataclass
class RunLog:
    lines: list[str] = field(default_factory=list)
    added: int = 0
    rejected: int = 0

    def say(self, s: str):
        logger.info(s)
        self.lines.append(s)


def research_run(store: Store, plan: dict[str, int], log: RunLog, *, llm=llm_mod,
                 fetch=verify.fetch_text, mailbox_factory=mailer_mod.Mailbox) -> RunLog:
    total = sum(max(0, n) for n in plan.values())
    if total > MAX_PER_RUN:
        raise ValueError(f"egy futásban legfeljebb {MAX_PER_RUN} cég")
    for c in plan:
        if c not in COUNTRIES:
            raise ValueError(f"nem célország: {c}")

    mailbox = None
    try:
        mailbox = mailbox_factory()
    except mailer_mod.MailError as e:
        # Gmail nélkül is lehet vázlatot írni; a küldés előtt úgyis kell.
        log.say(f"Figyelem: a Gmail-előzményt nem tudtam megnézni ({e}). Csak a saját naplóból szűrök.")

    focus = ", ".join(store.best_sectors())
    if focus:
        log.say(f"Tanulás: eddig itt válaszolnak a legtöbben: {focus}. Ezeket veszem előre.")
    try:
        for country, want in plan.items():
            got, attempts = 0, 0
            while got < want and attempts < 4:
                attempts += 1
                ask = min(BATCH, want - got + 2)
                try:
                    cands = llm.research(country, ask, store.known_domains(), focus)
                except Exception as e:  # noqa: BLE001 — egy hibás kör ne állítsa le a többit
                    log.say(f"{country}: a keresés hibára futott ({e}).")
                    continue
                if not cands:
                    log.say(f"{country}: ebben a körben nem talált jelöltet.")
                cands.sort(key=lambda c: _score(c.get("score")), reverse=True)
                for cand in cands:
                    if got >= want:
                        break
                    if _consider(store, cand, country, log, llm=llm, fetch=fetch, mailbox=mailbox):
                        got += 1
            log.say(f"{country}: {got}/{want} vázlat.")
    finally:
        if mailbox:
            mailbox.close()
    return log


def _consider(store, cand, country, log, *, llm, fetch, mailbox) -> bool:
    name = (cand.get("company") or "?").strip()
    cand["country"] = (cand.get("country") or country).upper()
    cand["email"] = (cand.get("email") or "").strip().lower()

    def reject(why: str) -> bool:
        log.rejected += 1
        log.say(f"  ✗ {name}: {why}")
        return False

    probs = verify.candidate_problems(cand)
    if probs:
        return reject(", ".join(probs))
    cand["score"] = _score(cand.get("score"))
    if cand["score"] < MIN_SCORE:
        return reject(f"gyenge illeszkedés ({cand['score']}/100)")
    cand["sector"] = cand.get("sector") if cand.get("sector") in SECTORS else None
    cand["signal"] = cand.get("signal") if cand.get("signal") in SIGNAL_TYPES else "none"
    known = store.is_known(cand["email"], cand.get("website"))
    if known:
        return reject(known)
    if mailbox:
        dom = domain_of(cand["email"])
        try:
            if mailbox.ever_contacted(cand["email"], None if dom in _free() else dom):
                store.block(cand["email"], "korábban már írtunk neki (Gmail)")
                return reject("a Gmail szerint már írtunk neki")
        except Exception as e:  # noqa: BLE001
            return reject(f"nem tudtam ellenőrizni a Gmailben ({e})")

    page = fetch(cand.get("email_url") or cand.get("website") or "")
    if not page or not verify.email_on_page(cand["email"], page):
        return reject("az e-mail cím nincs rajta a megadott oldalon")
    obs_page = page if cand.get("observation_url") == cand.get("email_url") else fetch(cand.get("observation_url") or "")
    if not obs_page or not verify.quote_on_page(cand["observation"], obs_page):
        return reject("az idézett mondat nincs rajta az oldalon")

    # A levél az ország nyelvén megy. Ha a hely oldala magyar (dél-szlovákiai,
    # erdélyi magyar vállalkozás), előtte egy teljes magyar változat is.
    country_lang = COUNTRIES[cand["country"]]["lang"]
    site_lang = verify.detect_lang(cand["observation"]) or verify.detect_lang((obs_page or "")[:3000])
    lead = {**cand, "lang": country_lang, "lang2": "hu" if site_lang == "hu" and country_lang != "hu" else None}
    langs = verify.letter_langs(lead)
    versions = {}
    try:
        for lang in langs:
            one = {**lead, "lang": lang, "lang2": None}
            for _ in range(2):
                one.update(llm.compose(one))
                if not verify.mixed_language(one):
                    break
            else:
                return reject(f"kétszer is vegyes nyelvű lett a(z) {lang} változat")
            one.update(_reviewed(llm, one))
            versions[lang] = one
    except Exception as e:  # noqa: BLE001
        return reject(f"a levélírás nem sikerült ({e})")
    lead["subject"] = " / ".join(versions[l]["subject"] for l in langs)
    lead["body"] = f"\n\n{verify.SEPARATOR}\n\n".join(versions[l]["body"] for l in langs)
    lead["critique"] = " | ".join(f"{l}: {versions[l]['critique']}" for l in langs) if len(langs) > 1 \
        else versions[langs[0]]["critique"]
    if verify.mixed_language(lead):
        return reject("vegyes nyelvű levél lett")
    lead["warnings"] = "; ".join(verify.check_letter(lead))
    if store.add_lead(lead) is None:
        return reject("közben már bekerült")
    log.added += 1
    log.say(f"  ✓ {name} ({cand.get('town') or country}) — {cand['email']}")
    return True


def _reviewed(llm, one: dict) -> dict:
    """A bíráló kör egy egynyelvű változatra. Az átírást csak akkor vesszük
    át, ha a gépi ellenőrzés szerint sem rosszabb, és nem lett vegyes nyelvű."""
    before = verify.check_letter(one)
    try:
        rev = llm.critique(one, one["subject"], one["body"])
    except Exception as e:  # noqa: BLE001 — a bírálat hiánya nem ok a vázlat eldobására
        return {"critique": f"a bírálat kimaradt ({e})"}
    cand = {**one, "subject": rev["subject"], "body": rev["body"]}
    out = {"critique": f"{rev['score']}/10" + (f" — {'; '.join(rev['issues'])}" if rev["issues"] else "")}
    if (rev["score"] < 9 and len(verify.check_letter(cand)) <= len(before)
            and OPT_OUT[one["lang"]] in rev["body"] and not verify.mixed_language(cand)):
        out.update(subject=rev["subject"], body=rev["body"])
    return out


def _score(v) -> int:
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return 50


def _free():
    from store import FREEMAIL
    return FREEMAIL


def send_one(store: Store, lead_id: int, *, mailer=mailer_mod) -> tuple[bool, str]:
    """Egy vázlat elküldése. Legfeljebb egyszer megy ki: ha a küldés és a
    naplózás között leáll a program, a levél 'sending' állapotban marad,
    és nem küldjük újra magától — azt ember nézi meg."""
    if store.sent_today() >= DAILY_CAP:
        return False, f"elérted a napi {DAILY_CAP} levelet"
    lead = store.get(lead_id)
    if not lead:
        return False, "nincs ilyen"
    if store.is_blocked(lead["email"]):
        store.skip(lead_id)
        return False, "tiltólistán van"
    if not (lead.get("subject") and lead.get("body")):
        return False, "hiányzik a tárgy vagy a szöveg"
    if verify.mixed_language(lead):
        return False, "vegyes nyelvű levél — javítsd, mielőtt kimegy"
    if not store.claim_for_send(lead_id):
        return False, "már küldés alatt vagy elküldve"
    try:
        msg = mailer.build_message(lead["email"], lead["subject"], lead["body"])
        mid = mailer.send(msg)
    except mailer.AuthError as e:
        store.mark_failed(lead_id, str(e))
        raise
    except Exception as e:  # noqa: BLE001
        store.mark_failed(lead_id, str(e))
        return False, str(e)
    store.mark_sent(lead_id, mid)
    return True, "elküldve"


def send_many(store: Store, ids: list[int], log: RunLog, *, mailer=mailer_mod, sleep=time.sleep) -> RunLog:
    for n, lead_id in enumerate(ids):
        try:
            ok, why = send_one(store, lead_id, mailer=mailer)
        except mailer.AuthError as e:
            log.say(f"Leálltam: {e}")
            break
        lead = store.get(lead_id) or {}
        log.say(f"{'✓' if ok else '✗'} {lead.get('company', lead_id)}: {why}")
        if not ok and "napi" in why:
            break
        if ok and n < len(ids) - 1:
            sleep(random.uniform(*SEND_GAP))
    return log


def workdays_between(start: datetime, end: datetime) -> int:
    d, n = start.date(), 0
    while d < end.date():
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def prepare_followups(store: Store, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    n = 0
    for lead in store.list("sent"):
        if lead["followup_status"] != "none" or lead["reply_kind"] != "none" or not lead["sent_at"]:
            continue
        if store.is_blocked(lead["email"]):
            continue
        if workdays_between(datetime.fromisoformat(lead["sent_at"]), now) >= FOLLOWUP_AFTER_WORKDAYS:
            langs = [lead["lang2"], lead["lang"]] if lead.get("lang2") else [lead["lang"]]
            store.set_followup_draft(lead["id"], f"\n\n{verify.SEPARATOR}\n\n".join(FOLLOW_UP[l] for l in langs))
            n += 1
    return n


def send_followup(store: Store, lead_id: int, *, mailer=mailer_mod) -> tuple[bool, str]:
    if store.sent_today() >= DAILY_CAP:
        return False, f"elérted a napi {DAILY_CAP} levelet"
    lead = store.get(lead_id)
    if not lead or lead["status"] != "sent":
        return False, "nincs elküldött első levél"
    if store.is_blocked(lead["email"]):
        store.drop_followup(lead_id)
        return False, "tiltólistán van"
    if not store.claim_followup(lead_id):
        return False, "már elment vagy közben válaszolt"
    try:
        subj = lead["subject"] if lead["subject"].lower().startswith("re:") else f"Re: {lead['subject']}"
        msg = mailer.build_message(lead["email"], subj, lead["followup_body"], in_reply_to=lead["message_id"])
        mailer.send(msg)
    except Exception as e:  # noqa: BLE001
        store.followup_done(lead_id, False, str(e))
        if isinstance(e, mailer.AuthError):
            raise
        return False, str(e)
    store.followup_done(lead_id, True)
    return True, "elküldve"


def prepare_answer(store: Store, lead_id: int, *, llm=llm_mod, slots_fn=calendar_slots.slots_for) -> dict:
    """Érdeklődőnek: 3 szabad időpont a naptárból, és a válasz megírva."""
    lead = store.get(lead_id)
    if not lead:
        raise ValueError("nincs ilyen")
    sl = slots_fn(lead["company"], lead["email"])
    try:
        text = llm.draft_reply(lead["body"], lead["reply_text"] or "", [s["label"] for s in sl["slots"]], lead["lang"])
    except Exception as e:  # noqa: BLE001
        text = f"(A válasz megírása nem sikerült: {e}. Az időpontok lent vannak.)"
    store.set_suggestion(lead_id, text, json.dumps(sl, ensure_ascii=False))
    return sl


def scan_replies(store: Store, log: RunLog, *, llm=llm_mod, mailbox_factory=mailer_mod.Mailbox,
                 slots_fn=calendar_slots.slots_for) -> RunLog:
    sent = [l for l in store.list("sent") if l["reply_kind"] in ("none", "auto")]
    with mailbox_factory() as mb:
        # Visszapattanók: a hibaüzenet szövegében ott a címzett címe.
        bounces = mb.bounces_since(21)
        for lead in sent:
            if any(lead["email"] in (b["text"] or "").lower() for b in bounces):
                store.set_reply(lead["id"], "bounce", "a levél nem kézbesíthető")
                log.say(f"✗ {lead['company']}: visszapattant, tiltólistára került")
        for lead in store.list("sent"):
            if lead["reply_kind"] not in ("none", "auto"):
                continue
            msgs = [m for m in mb.messages_from(lead["email"], 45) if m["from"] == lead["email"]]
            if not msgs and domain_of(lead["email"]) not in _free():
                msgs = [m for m in mb.messages_from(domain_of(lead["email"]), 45)
                        if lead["message_id"] and lead["message_id"] in (m["in_reply_to"] + m["references"])]
            if not msgs:
                continue
            latest = msgs[-1]
            reply = mailer_mod.strip_quoted(latest["text"]) or latest["text"]
            if lead["reply_kind"] == "auto" and reply[:4000] == (lead["reply_text"] or ""):
                continue  # ugyanaz az automatikus válasz, már láttuk
            try:
                kind = llm.classify(lead["body"], reply)
            except Exception as e:  # noqa: BLE001
                log.say(f"? {lead['company']}: válasz jött, de nem tudtam besorolni ({e})")
                store.set_reply(lead["id"], "other", reply)
                continue
            store.set_reply(lead["id"], kind, reply)
            if kind == "interested":
                prepare_answer(store, lead["id"], llm=llm, slots_fn=slots_fn)
            label = {"no": "nem kér — tiltólistára került", "interested": "ÉRDEKLŐDIK — válasz időpontokkal kész",
                     "auto": "automatikus válasz", "other": "válaszolt"}[kind]
            log.say(f"• {lead['company']}: {label}")
    return log

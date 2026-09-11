import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "./email-agent.css";

import { useDocumentMeta } from "../seo";
import { CONTACT, mailto } from "../contact";
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/agent/email`;

const ERRORS = {
  access_denied: "A Google-hozzáférést elutasítottad, vagy megszakadt a folyamat.",
  invalid_state: "Lejárt a folyamat. Indítsd újra a csatlakozást.",
  token_exchange: "A Google-lel való egyeztetés nem sikerült. Próbáld újra.",
  no_email: "A Google nem adta vissza a fiók e-mail címét.",
  busy: "Most túl sokan próbálják egyszerre. Gyere vissza pár perc múlva.",
};

const URGENCY = [
  { min: 5, label: "Azonnali", cls: "u5" },
  { min: 4, label: "Sürgős", cls: "u4" },
  { min: 3, label: "Közepes", cls: "u3" },
  { min: 0, label: "Ráér", cls: "u1" },
];

const urgencyOf = (n) => URGENCY.find((u) => (n || 0) >= u.min) || URGENCY[3];

// The token arrives in the callback URL and lives in sessionStorage, so it dies
// with the tab - and a cross-host cookie (which browsers would drop) is avoided.
const KEY = "aximbra:agent";
const token = () => { try { return sessionStorage.getItem(KEY) || ""; } catch { return ""; } };
const setToken = (v) => {
  try { v ? sessionStorage.setItem(KEY, v) : sessionStorage.removeItem(KEY); } catch { /* private mode */ }
};

const get = (path) => fetch(`${API}${path}`, {
  headers: token() ? { "X-Agent-Session": token() } : {},
}).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Hiba");
  return data;
});

const post = (path, body) => fetch(`${API}${path}`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    ...(token() ? { "X-Agent-Session": token() } : {}),
  },
  body: JSON.stringify(body),
}).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Hiba");
  return data;
});

const TONES = [["hivatalos", "Hivatalos"], ["kozvetlen", "Közvetlen"]];

/**
 * Reply draft for one email.
 *
 * Drafting is on demand rather than part of the run: it is the most expensive
 * call here, and most of a mailbox does not need an answer. Each panel owns its
 * own state so one email's draft cannot interfere with another's.
 *
 * The text is written on the page. Putting it into the visitor's Gmail Drafts is
 * a second, separate step, offered only when the session holds draft-writing
 * access, and it asks for an explicit confirmation first — that save is the one
 * action in the whole agent that changes the mailbox. Sending is never offered.
 */
const DraftPanel = ({ email, canDraft }) => {
  const [tone, setTone] = useState("hivatalos");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  // "save" and "send" are tracked separately on purpose: confirming a save must
  // never be mistaken for confirming a send, which cannot be undone.
  const [confirming, setConfirming] = useState(null); // null | "save" | "send"
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [sent, setSent] = useState(null);

  const write = async (nextTone) => {
    const useTone = nextTone || tone;
    setBusy(true); setErr(""); setCopied(false);
    try {
      setDraft(await post("/draft", { id: email.id, tone: useTone }));
      setTone(useTone);
      // A reworded draft is not the one that was saved; make the visitor confirm
      // again rather than leaving a stale "saved" badge next to new text.
      setSaved(null);
      setConfirming(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const saveToGmail = async () => {
    setSaving(true); setErr("");
    try {
      setSaved(await post("/draft/save", { id: email.id, tone, confirm: true }));
      setConfirming(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const sendNow = async () => {
    setSaving(true); setErr("");
    try {
      setSent(await post("/draft/send", { id: email.id, tone, confirm: true }));
      setConfirming(null);
      setSaved(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    const text = `${draft.targy}\n\n${draft.valasz}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard needs a secure context and permission; select the text instead
      setErr("A vágólap nem elérhető — jelöld ki a szöveget és másold ki kézzel.");
    }
  };

  return (
    <div className="agent-draft" data-testid={`agent-draft-${email.id}`}>
      <div className="agent-draft-bar">
        <button className="agent-draft-btn" onClick={() => write()} disabled={busy}
          data-testid={`agent-draft-go-${email.id}`}>
          {busy ? <><span className="spin" /> Fogalmazás…</>
                : draft ? "Újrafogalmazás" : "Megfogalmazom a választ"}
        </button>
        <div className="agent-draft-tones" role="group" aria-label="Hangnem">
          {TONES.map(([value, label]) => (
            <button key={value} type="button"
              className={`agent-tone ${tone === value ? "on" : ""}`}
              aria-pressed={tone === value}
              disabled={busy}
              onClick={() => (draft ? write(value) : setTone(value))}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="agent-draft-err">{err}</div>}

      {draft && (
        <div className="agent-draft-out">
          <div className="agent-draft-subj">
            <span className="k">Tárgy</span>
            <span>{draft.targy}</span>
          </div>
          {/* readOnly, not disabled: the text stays selectable and copyable. */}
          <textarea className="agent-draft-text" readOnly value={draft.valasz}
            rows={Math.min(18, draft.valasz.split("\n").length + 2)}
            data-testid={`agent-draft-text-${email.id}`} />
          <div className="agent-draft-foot">
            <button className="agent-draft-copy" onClick={copy}>
              {copied ? "Kimásolva" : "Másolás"}
            </button>
            {canDraft && !sent && !confirming && (
              <>
                {!saved && (
                  <button className="agent-draft-save" onClick={() => setConfirming("save")}
                    disabled={saving} data-testid={`agent-save-${email.id}`}>
                    Mentés a Gmail vázlatok közé
                  </button>
                )}
                <button className="agent-draft-send" onClick={() => setConfirming("send")}
                  disabled={saving} data-testid={`agent-send-${email.id}`}>
                  E-mail elküldése
                </button>
              </>
            )}
            <span className="agent-draft-note">
              {canDraft
                ? "Küldés előtt még egyszer rákérdezünk — elküldeni csak te tudod."
                : "Fogalmazvány — az agent nem küldi el, és a fiókodba sem írja be."}
            </span>
          </div>

          {/* Confirmations are a second click on a separate control, not a
              confirm() dialog, so what will happen and to whom is on screen when
              the decision is made. Save and send are separate states: confirming
              one must never send the other. */}
          {confirming === "save" && (
            <div className="agent-confirm" data-testid={`agent-confirm-${email.id}`}>
              <p>
                Vázlatot írok a Gmail-fiókodba <b>{email.sender}</b> levelére,
                a saját levelezőszálára. <b>Nem küldöm el</b> — a Vázlatok közt
                találod, és te döntöd el, elküldöd-e.
              </p>
              <div className="agent-confirm-row">
                <button className="agent-confirm-yes" onClick={saveToGmail} disabled={saving}
                  data-testid={`agent-confirm-yes-${email.id}`}>
                  {saving ? <><span className="spin" /> Mentés…</> : "Megerősítem, mentsd vázlatként"}
                </button>
                <button className="agent-confirm-no" onClick={() => setConfirming(null)}
                  disabled={saving}>
                  Mégsem
                </button>
              </div>
            </div>
          )}

          {/* Sending is the one thing here that cannot be undone, so its
              confirmation looks different, names the recipient and says so. */}
          {confirming === "send" && (
            <div className="agent-confirm danger" data-testid={`agent-confirm-send-${email.id}`}>
              <p>
                <b>Most tényleg elküldöm ezt a levelet.</b>
              </p>
              <ul className="agent-confirm-facts">
                <li><span>Címzett</span><b>{email.sender}</b></li>
                <li><span>Tárgy</span><b>{draft.targy}</b></li>
                <li><span>Feladó</span><b>a te Gmail-fiókod</b></li>
              </ul>
              <p className="agent-confirm-warn">
                Ez nem vonható vissza. Olvasd át a fenti szöveget — a
                szögletes zárójeles részeket ({"["}így{"]"}) neked kell kitöltened,
                mielőtt elküldöd.
              </p>
              <div className="agent-confirm-row">
                <button className="agent-confirm-send" onClick={sendNow} disabled={saving}
                  data-testid={`agent-confirm-send-yes-${email.id}`}>
                  {saving ? <><span className="spin" /> Küldés…</> : "Igen, küldd el most"}
                </button>
                <button className="agent-confirm-no" onClick={() => setConfirming(null)}
                  disabled={saving}>
                  Mégsem
                </button>
              </div>
            </div>
          )}

          {sent && (
            <div className="agent-sent" data-testid={`agent-sent-${email.id}`}>
              <b>Elküldve.</b> Címzett: {sent.to} · Tárgy: {sent.subject}
            </div>
          )}

          {saved && (
            <div className="agent-saved" data-testid={`agent-saved-${email.id}`}>
              <b>{saved.updated ? "Vázlat frissítve." : "Vázlat elmentve."}</b>{" "}
              Címzett: {saved.to}.{" "}
              <a href={saved.gmail_url} target="_blank" rel="noopener noreferrer">
                Megnyitom a Gmailben
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function EmailAgent({ embedded = false }) {
  // Only the standalone route owns the document title; the homepage embeds the
  // same component and must keep its own metadata.
  useDocumentMeta({
    title: embedded ? "" : "E-mail rendező agent — élő demó | AXIMBRA",
    description:
      "Élő demó: az agent átfutja a postafiókod elmúlt 30 napját, rangsorolja a " +
      "leveleket és megírja a válaszokat. Alapból csak olvas — küldeni nem tud.",
    path: "/demo/email-agent",
    // Az oldal szövege csak magyarul létezik.
    translated: false,
  });
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  // Off by default, and deliberately not remembered: handing over write access to
  // a mailbox is a decision to take each time, not one to inherit from last visit.
  const [allowDrafts, setAllowDrafts] = useState(false);
  const [starting, setStarting] = useState(false);
  // The Google route is real and works, but it puts an "unverified app" warning
  // in front of every visitor and asks a stranger for their mailbox. It stays,
  // one click away, for someone who actually wants it.
  const [showConnect, setShowConnect] = useState(false);
  const [onlyNeedsReply, setOnlyNeedsReply] = useState(false);
  const [openId, setOpenId] = useState(null);
  const timer = useRef(null);
  const retry = useRef(null);

  const poll = useCallback(async () => {
    try {
      const [p, r] = await Promise.all([get("/progress"), get("/results")]);
      setProgress(p);
      setResults(r);
      if (!p.running && timer.current) {
        clearInterval(timer.current);
        timer.current = null;
      }
    } catch {
      if (timer.current) { clearInterval(timer.current); timer.current = null; }
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const err = params.get("error");
    if (err) setError(ERRORS[err] || "Ismeretlen hiba.");
    const s = params.get("s");
    if (s) setToken(s);
    if (err || params.get("connected")) {
      // Drop the token from the address bar so it is not shared or bookmarked.
      window.history.replaceState({}, "", window.location.pathname);
    }
    let cancelled = false;

    // A failed status call used to render as "configured: false", which printed
    // "Az agent Google-hozzáférése nincs beállítva" — a confident claim about the
    // server's configuration made from a request that never arrived. The common
    // cause is the API restarting during a deploy, which resolves itself in
    // seconds, so retry a few times and then say what is actually known: the
    // agent could not be reached.
    const load = async (attempt = 0) => {
      try {
        const s = await get("/status");
        if (cancelled) return;
        setStatus(s);
        if (s.connected) {
          poll();
          timer.current = setInterval(poll, 3000);
        }
      } catch {
        if (cancelled) return;
        if (attempt < 3) {
          retry.current = setTimeout(() => load(attempt + 1), 1500 * (attempt + 1));
          return;
        }
        setStatus({ unreachable: true });
      }
    };
    load();

    return () => {
      cancelled = true;
      if (timer.current) clearInterval(timer.current);
      if (retry.current) clearTimeout(retry.current);
    };
  }, [poll]);

  // Leaving the page ends the run server-side, so returning starts from scratch.
  useEffect(() => {
    const end = () => {
      const t = token();
      if (t && navigator.sendBeacon) {
        navigator.sendBeacon(`${API}/disconnect?s=${encodeURIComponent(t)}`);
      }
    };
    window.addEventListener("pagehide", end);
    return () => window.removeEventListener("pagehide", end);
  }, []);

  const runSample = async () => {
    setStarting(true);
    setError("");
    try {
      const { session } = await post("/sample", {});
      setToken(session);
      const s = await get("/status");
      setStatus(s);
      poll();
      if (timer.current) clearInterval(timer.current);
      timer.current = setInterval(poll, 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  };

  const connect = async () => {
    setConnecting(true);
    setError("");
    try {
      // The wider grant is requested only when the visitor ticked the box. The
      // default path asks Google for read access and nothing else.
      const d = await get(allowDrafts ? "/connect?drafts=true" : "/connect");
      window.location.href = d.auth_url;
    } catch (e) {
      setConnecting(false);
      setError(e.message);
    }
  };

  const disconnect = async () => {
    await fetch(`${API}/disconnect`, {
      method: "POST",
      headers: token() ? { "X-Agent-Session": token() } : {},
    }).catch(() => {});
    setToken("");
    window.location.assign(window.location.pathname);
  };

  const done = progress && !progress.running && progress.total > 0;
  const pct = progress?.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <div className={embedded ? "agent-embed" : "agent-page"}>
      {!embedded && (
        <header className="agent-top">
          <Link to="/" className="agent-back">← AXIMBRA</Link>
          <span className={`agent-pill ${status?.connected ? "on" : ""}`}>
            {status?.connected ? status.email : "Nincs csatlakozva"}
          </span>
        </header>
      )}

      <main className="agent-main">
        {!status ? (
          <div className="agent-center"><span className="spin" /></div>
        ) : status.unreachable ? (
          /* What is actually known: the request did not arrive. Saying anything
             about the server's configuration from here would be a guess. */
          <div className="agent-intro">
            {!embedded && <h1>E-mail rendező agent</h1>}
            <div className="agent-closed" data-testid="agent-unreachable">
              <p>
                <b>Az agent most nem érhető el.</b> Nem tudtuk elérni a
                kiszolgálót — ez általában néhány másodperces frissítés, amíg új
                verzió indul.
              </p>
              <p>
                <button type="button" className="agent-retry"
                  onClick={() => window.location.reload()}>
                  Próbáld újra
                </button>
              </p>
            </div>
          </div>
        ) : !status.connected ? (
          <div className="agent-intro">
            {!embedded && <h1>E-mail rendező agent</h1>}
            <p className="agent-lead">
              Csatlakoztasd a Gmail-fiókod, és az agent végigmegy az elmúlt 30 nap
              levelein: kategóriába sorolja, sürgősséget állapít meg, és megmondja,
              melyikre kell válaszolnod. Amelyikre kéred, a választ is megfogalmazza.
            </p>

            <ul className="agent-guarantees">
              <li>
                <b>Alapból csak olvas.</b> A lenti pipa nélkül semmit nem ír a
                fiókodba, és a küldési jogot sem kéri.
              </li>
              <li>
                <b>A meglévő leveleidhez soha nem nyúl.</b> Nem címkéz, nem
                csillagoz, nem töröl — akkor sem, ha megadod az írási jogot.
              </li>
              <li>
                <b>Írni és küldeni csak a te engedélyeddel.</b> Ha bepipálod,
                akkor is levelenként külön rákérdezünk, mielőtt vázlatot írna
                vagy elküldene bármit.
              </li>
              <li>
                <b>Semmit nem tárolunk.</b> A futás <b>30 perc</b> után magától
                lejár, a lap bezárásával pedig azonnal törlődik.
              </li>
            </ul>

            {/* The specifics belong here, before the grant — not in a policy page
                the visitor would have to go looking for. Everything listed is what
                the code actually does; see backend/mail_agent.py. */}
            <details className="agent-disclosure" data-testid="agent-disclosure">
              <summary>Mit kérünk pontosan, és mi történik az adataiddal?</summary>
              <div className="agent-disclosure-body">
                <h3>A kért Google-jogosultságok</h3>
                <ul>
                  <li>
                    <code>gmail.readonly</code> — a leveleid olvasása. Ez mindig
                    kell, és alapesetben ez az egyetlen jog, amit kérünk.
                  </li>
                  <li><code>userinfo.email</code> és <code>openid</code> — hogy tudjuk, melyik fiókot nézzük.</li>
                  <li>
                    <code>gmail.compose</code> — <b>csak ha bepipálod a vázlatírást.</b>{" "}
                    Ettől tud vázlatot tenni a fiókodba. A Google-nak nincs „csak
                    vázlat” jogosultsága, ezért ez küldést is engedne — ez a kód
                    viszont soha nem küld, a küldés kódszinten tiltott. Pipa nélkül
                    ezt a jogot nem is kérjük.
                  </li>
                </ul>

                <h3>Mit olvasunk</h3>
                <ul>
                  <li>Az elmúlt <b>30 nap</b> legfeljebb <b>50 levele</b>. Semmi régebbi, semmi több.</li>
                  <li>Feladó, tárgy, dátum és a levél szövege.</li>
                  <li>
                    <b>Csatolmány csak akkor, ha a levél szövege önmagában kevés</b> —
                    egy „küldöm az anyagot, részletek csatolva” típusú levélnél a lényeg
                    a dokumentumban van. Ilyenkor levelenként legfeljebb két fájlból
                    olvassuk ki a <i>szöveget</i> (Word, Excel, PowerPoint, PDF, sima
                    szöveg; képekből és videókból nem). A fájlt nem tároljuk, csak a
                    kiolvasott szöveg megy tovább az osztályozáshoz.
                  </li>
                </ul>

                <h3>Mit írunk</h3>
                <ul>
                  <li>
                    Pipa nélkül: <b>semmit</b>. A fogalmazvány a lapon marad, te másolod ki.
                  </li>
                  <li>
                    Vázlatírással: egyetlen dolgot, levelenként, a te külön
                    megerősítésed után — egy <b>válaszvázlatot</b> a Gmail Vázlatok
                    közé. Meglévő levelet nem módosítunk: nem címkézünk, nem
                    csillagozunk, nem törlünk, és <b>nem küldünk el semmit</b>.
                  </li>
                </ul>

                <h3>Hová kerül</h3>
                <ul>
                  <li>
                    A levél szövegét egyetlen osztályozó hívásban elküldjük az{" "}
                    <b>OpenAI</b> API-jának. Az API-n beküldött adatot a szolgáltató
                    alapbeállítás szerint nem használja modelltanításra.
                  </li>
                  <li>Adatbázisba semmi nem kerül. A futás a szerver memóriájában él.</li>
                </ul>

                <h3>Meddig él, és hogyan törlöd</h3>
                <ul>
                  <li>A munkamenet <b>30 perc</b> után magától lejár.</li>
                  <li>
                    A „Kilépés” azonnal törli a futást és a hozzáférést. A lap
                    bezárása ugyanezt teszi.
                  </li>
                  <li>
                    A jogosultságot a Google-nál bármikor visszavonhatod:{" "}
                    <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">
                      myaccount.google.com/permissions
                    </a>
                  </li>
                </ul>

                <h3>Ki kéri</h3>
                <p>
                  AXIMBRA · Budapest · <a href={mailto()}>{CONTACT.email}</a> — kérdés
                  vagy törlési kérés esetén írj, és válaszolunk.
                </p>
              </div>
            </details>

            {error && <div className="agent-error">{error}</div>}

            {/* `public === false` is a deliberate setting, not a fault, so it reads
                as a status with a way forward rather than as an error. */}
            {status.public === false ? (
              <div className="agent-closed" data-testid="agent-closed">
                <p>
                  <b>Az agent jelenleg nem nyilvános.</b> A Gmail-hozzáférés kérése
                  előtt közzétesszük az adatkezelési tájékoztatót és a céges adatokat —
                  addig nem kérünk senkitől postafiók-hozzáférést.
                </p>
                <p>
                  Élőben szívesen megmutatjuk a saját fiókunkon:{" "}
                  <a href={mailto("Megnézném az e-mail agentet élőben")}>{CONTACT.email}</a>
                </p>
              </div>
            ) : !showConnect ? (
              /* The default way in. No Google account, no consent screen, no
                 warning — and nothing of the visitor's to hand over. The model
                 calls behind it are the real ones. */
              <div className="agent-start">
                <button className="agent-cta" onClick={runSample} disabled={starting}
                  data-testid="agent-sample">
                  {starting
                    ? <><span className="spin" /> Indítás…</>
                    : "Nézd meg egy példa postafiókon"}
                </button>
                <p className="agent-start-note">
                  10 valósághű magyar levél, azonnal, belépés nélkül. Ugyanaz az
                  agent fut rajtuk, mint egy éles postafiókon — a válaszokat is
                  megírja.
                </p>
                <button type="button" className="agent-start-alt"
                  onClick={() => setShowConnect(true)} data-testid="agent-show-connect">
                  Inkább a saját Gmail-fiókomon nézném meg →
                </button>
              </div>
            ) : (
              <>
                {status.configured === false && (
                  <div className="agent-error">Az agent Google-hozzáférése még nincs beállítva.</div>
                )}

                {/* Straight about what the visitor is walking into. Google shows an
                    "unverified app" warning for a restricted scope until the app
                    passes a security assessment; hiding that would waste their time
                    and look worse when it appears. */}
                <div className="agent-google-note" data-testid="agent-google-note">
                  <p>
                    <b>Amit a Google mutatni fog.</b> Mielőtt beenged, egy piros
                    „A Google nem ellenőrizte ezt az alkalmazást” képernyő jön. Ez
                    minden olyan alkalmazásnál megjelenik, amelyik postafiók-hozzáférést
                    kér és még nem esett át a Google biztonsági átvilágításán — nem a
                    fiókod állapotáról szól.
                  </p>
                  <p>
                    Továbblépni a <i>Speciális</i> → <i>Tovább…</i> linken lehet.
                    Ha ez most kényelmetlen, a példa postafiók mindent megmutat
                    belépés nélkül.
                  </p>
                  <button type="button" className="agent-start-alt"
                    onClick={() => setShowConnect(false)}>
                    ← Vissza a példa postafiókhoz
                  </button>
                </div>

                {/* Opt-in for mailbox writing. Unticked by default, and the text
                    says exactly what the wider grant means — including that
                    Google's own consent screen will mention sending, because
                    gmail.compose has no draft-only variant. */}
                <label className="agent-optin" data-testid="agent-optin">
                  <input type="checkbox" checked={allowDrafts} disabled={connecting}
                    onChange={(e) => setAllowDrafts(e.target.checked)}
                    data-testid="agent-optin-box" />
                  <span>
                    <b>Írhat vázlatot a postafiókomba.</b> Ha bepipálod, az agent a
                    megírt választ — a te külön megerősítésed után, levelenként —
                    beteszi a Gmail <i>Vázlatok</i> közé, a saját levelezőszálára.
                    Elküldeni akkor is csak te tudod.
                    <span className="agent-optin-warn">
                      Fontos: a Google-nak nincs „csak vázlat” jogosultsága, ezért a
                      beleegyező képernyő küldési jogot is említeni fog. Ez a kód
                      soha nem küld levelet — a küldés kódszinten tiltott —, de a
                      jogosultság, amit megadsz, ennél szélesebb. Ha ez nem
                      kényelmes, hagyd üresen: a fogalmazás pipa nélkül is működik,
                      csak kimásolni kell.
                    </span>
                  </span>
                </label>

                <button className="agent-cta" onClick={connect}
                  disabled={connecting || status.configured === false}>
                  {connecting ? <><span className="spin" /> Átirányítás…</>
                    : allowDrafts ? "Csatlakozás — olvasás és vázlatírás"
                    : "Csatlakozás a Google-fiókhoz"}
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="agent-run">
            {status.sample && (
              /* Said plainly: these results are real agent output on invented
                 mail, and must not read as the visitor's own inbox. */
              <div className="agent-sample-note" data-testid="agent-sample-note">
                <b>Példa postafiók.</b> A levelek kitaláltak — az osztályozás és a
                válaszok viszont most készültek, ugyanazzal az agenttel, ami egy
                éles fiókon futna.
              </div>
            )}
            {!done && (
              <div className="agent-progress">
                <div className="agent-progress-head">
                  <span className="spin" />
                  <span>{progress?.message || "Indulás…"}</span>
                  {progress?.total ? <span className="agent-count">{progress.done} / {progress.total}</span> : null}
                </div>
                <div className="agent-bar"><div className="agent-bar-fill" style={{ width: `${pct}%` }} /></div>
              </div>
            )}

            {results && results.total > 0 && (
              <>
                <div className="agent-tiles">
                  <div className="agent-tile">
                    <div className="k">Feldolgozott levél</div>
                    <div className="v">{results.total}</div>
                  </div>
                  {/* Clickable: filters the list below to the emails this number
                      counts. Disabled at zero — a filter that yields nothing is a
                      dead end, not a feature. */}
                  <button
                    type="button"
                    className={`agent-tile agent-tile-btn ${onlyNeedsReply ? "on" : ""}`}
                    onClick={() => setOnlyNeedsReply((v) => !v)}
                    disabled={results.needs_reply === 0}
                    aria-pressed={onlyNeedsReply}
                    data-testid="agent-tile-needs-reply">
                    <div className="k">Válasz szükséges</div>
                    <div className="v accent">{results.needs_reply}</div>
                    {results.needs_reply > 0 && (
                      <div className="agent-tile-hint">
                        {onlyNeedsReply ? "Mind a levél mutatása" : "Mutasd ezeket"}
                      </div>
                    )}
                  </button>
                  <div className="agent-tile wide">
                    <div className="k">Legsürgősebb</div>
                    <ul className="agent-top-list">
                      {results.top_urgent.map((e) => (
                        <li key={e.id}><span className={`dot-u ${urgencyOf(e.urgency).cls}`} />{e.subject}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="agent-cats">
                  <div className="k">Kategória-megoszlás</div>
                  {Object.entries(results.counts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([cat, n]) => (
                      <div className="agent-cat-row" key={cat}>
                        <span className="agent-cat-name">{cat}</span>
                        <span className="agent-cat-bar">
                          <span style={{ width: `${(n / results.total) * 100}%` }} />
                        </span>
                        <span className="agent-cat-n">{n}</span>
                      </div>
                    ))}
                </div>

                {onlyNeedsReply && (
                  <div className="agent-filter-note" data-testid="agent-filter-note">
                    Csak a válaszra váró levelek látszanak.{" "}
                    <button type="button" onClick={() => setOnlyNeedsReply(false)}>
                      Mutasd mind a {results.total} levelet
                    </button>
                  </div>
                )}

                <div className="agent-list">
                  {results.analyses
                    .filter((e) => !onlyNeedsReply || e.needs_reply === "igen")
                    .map((e) => {
                    const u = urgencyOf(e.urgency);
                    const open = openId === e.id;
                    const needs = e.needs_reply === "igen";
                    return (
                      // `needs` paints the row in the same cyan as the tile's
                      // number, so the count and the emails it refers to read as
                      // one thing.
                      <div className={`agent-row ${u.cls}${needs ? " needs" : ""}`} key={e.id}>
                        <button className="agent-row-head" onClick={() => setOpenId(open ? null : e.id)}>
                          <div className="agent-row-main">
                            <div className="agent-row-from">{e.sender}</div>
                            <div className="agent-row-subj">{e.subject}</div>
                            <div className="agent-row-sum">{e.summary}</div>
                            <div className="agent-row-tags">
                              <span className="tag-cat">{e.category}</span>
                              <span className={`tag-u ${u.cls}`}>{u.label}</span>
                              {e.needs_reply === "igen" && <span className="tag-reply">Válasz szükséges</span>}
                              {e.deadline && <span className="tag-date">{e.deadline}</span>}
                            </div>
                          </div>
                          <span className="agent-row-date">{(e.date || "").slice(0, 10)}</span>
                        </button>
                        {open && (
                          <div className="agent-row-body">
                            <div className="k">Miért ez a sürgősség</div>
                            <p>{e.urgency_reason || "—"}</p>
                            <div className="k">Javasolt következő lépés</div>
                            <p>{e.next_step || "—"}</p>
                            <div className="k">A levél</div>
                            <pre>{e.body || e.snippet || "(üres)"}</pre>
                            <DraftPanel email={e} canDraft={status.can_draft === true} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {done && results?.total === 0 && (
              <p className="agent-lead">Nem találtunk levelet az elmúlt 30 napból.</p>
            )}

            <button className="agent-cta ghost" onClick={disconnect}>
              Kilépés és lecsatlakozás
            </button>
            <p className="agent-foot">
              A kilépéssel a fiókod azonnal lecsatlakozik, és az elemzés törlődik a szerverről.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

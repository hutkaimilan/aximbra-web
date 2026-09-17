import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "./email-agent.css";

import { useDocumentMeta } from "../seo";
import { CONTACT, mailto } from "../contact";
import { useLang } from "../i18n";
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/agent/email`;

const URGENCY = [
  { min: 5, cls: "u5" },
  { min: 4, cls: "u4" },
  { min: 3, cls: "u3" },
  { min: 0, cls: "u1" },
];

const urgencyOf = (n) => URGENCY.find((u) => (n || 0) >= u.min) || URGENCY[3];

/** Egyszerű behelyettesítés: "{n} levél" → "12 levél". */
const fmt = (template, values) =>
  Object.entries(values).reduce((out, [k, v]) => out.split(`{${k}}`).join(v), template || "");

// The token arrives in the callback URL and lives in sessionStorage, so it dies
// with the tab - and a cross-host cookie (which browsers would drop) is avoided.
const KEY = "aximbra:agent";
const token = () => { try { return sessionStorage.getItem(KEY) || ""; } catch { return ""; } };
const setToken = (v) => {
  try { v ? sessionStorage.setItem(KEY, v) : sessionStorage.removeItem(KEY); } catch { /* private mode */ }
};

/** A kiszolgáló hibája lehet szöveg vagy `{code}`: a kód a lap nyelvén kap
 *  feliratot, a szöveg úgy megy tovább, ahogy van. */
const failure = (detail) => {
  const err = new Error(typeof detail === "string" ? detail : "");
  if (detail && typeof detail === "object" && detail.code) err.code = detail.code;
  return err;
};

const get = (path) => fetch(`${API}${path}`, {
  headers: token() ? { "X-Agent-Session": token() } : {},
}).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw failure(data.detail);
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
  if (!r.ok) throw failure(data.detail);
  return data;
});

const TONE_KEYS = ["hivatalos", "kozvetlen"];

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
  const { t } = useLang();
  const a = t.agent;
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
      setErr(a.draft.clipboardError);
    }
  };

  return (
    <div className="agent-draft" data-testid={`agent-draft-${email.id}`}>
      <div className="agent-draft-bar">
        <button className="agent-draft-btn" onClick={() => write()} disabled={busy}
          data-testid={`agent-draft-go-${email.id}`}>
          {busy ? <><span className="spin" /> {a.draft.writing}</>
                : draft ? a.draft.rewrite : a.draft.write}
        </button>
        <div className="agent-draft-tones" role="group" aria-label={a.tone.group}>
          {TONE_KEYS.map((value) => (
            <button key={value} type="button"
              className={`agent-tone ${tone === value ? "on" : ""}`}
              aria-pressed={tone === value}
              disabled={busy}
              onClick={() => (draft ? write(value) : setTone(value))}>
              {a.tone[value]}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="agent-draft-err">{err}</div>}

      {draft && (
        <div className="agent-draft-out">
          <div className="agent-draft-subj">
            <span className="k">{a.draft.subject}</span>
            <span>{draft.targy}</span>
          </div>
          {/* readOnly, not disabled: the text stays selectable and copyable. */}
          <textarea className="agent-draft-text" readOnly value={draft.valasz}
            rows={Math.min(18, draft.valasz.split("\n").length + 2)}
            data-testid={`agent-draft-text-${email.id}`} />
          <div className="agent-draft-foot">
            <button className="agent-draft-copy" onClick={copy}>
              {copied ? a.draft.copied : a.draft.copy}
            </button>
            {canDraft && !sent && !confirming && (
              <>
                {!saved && (
                  <button className="agent-draft-save" onClick={() => setConfirming("save")}
                    disabled={saving} data-testid={`agent-save-${email.id}`}>
                    {a.draft.save}
                  </button>
                )}
                <button className="agent-draft-send" onClick={() => setConfirming("send")}
                  disabled={saving} data-testid={`agent-send-${email.id}`}>
                  {a.draft.send}
                </button>
              </>
            )}
            <span className="agent-draft-note">
              {canDraft ? a.draft.noteWrite : a.draft.noteRead}
            </span>
          </div>

          {/* Confirmations are a second click on a separate control, not a
              confirm() dialog, so what will happen and to whom is on screen when
              the decision is made. Save and send are separate states: confirming
              one must never send the other. */}
          {confirming === "save" && (
            <div className="agent-confirm" data-testid={`agent-confirm-${email.id}`}>
              <p>
                {fmt(a.draft.saveText, { sender: email.sender })}{" "}
                <b>{a.draft.saveNotSend}</b> {a.draft.saveNotSendRest}
              </p>
              <div className="agent-confirm-row">
                <button className="agent-confirm-yes" onClick={saveToGmail} disabled={saving}
                  data-testid={`agent-confirm-yes-${email.id}`}>
                  {saving ? <><span className="spin" /> {a.draft.saving}</> : a.draft.saveYes}
                </button>
                <button className="agent-confirm-no" onClick={() => setConfirming(null)}
                  disabled={saving}>
                  {a.draft.cancel}
                </button>
              </div>
            </div>
          )}

          {/* Sending is the one thing here that cannot be undone, so its
              confirmation looks different, names the recipient and says so. */}
          {confirming === "send" && (
            <div className="agent-confirm danger" data-testid={`agent-confirm-send-${email.id}`}>
              <p>
                <b>{a.draft.sendTitle}</b>
              </p>
              <ul className="agent-confirm-facts">
                <li><span>{a.draft.to}</span><b>{email.sender}</b></li>
                <li><span>{a.draft.subject}</span><b>{draft.targy}</b></li>
                <li><span>{a.draft.from}</span><b>{a.draft.fromValue}</b></li>
              </ul>
              <p className="agent-confirm-warn">{a.draft.sendWarn}</p>
              <div className="agent-confirm-row">
                <button className="agent-confirm-send" onClick={sendNow} disabled={saving}
                  data-testid={`agent-confirm-send-yes-${email.id}`}>
                  {saving ? <><span className="spin" /> {a.draft.sending}</> : a.draft.sendYes}
                </button>
                <button className="agent-confirm-no" onClick={() => setConfirming(null)}
                  disabled={saving}>
                  {a.draft.cancel}
                </button>
              </div>
            </div>
          )}

          {sent && (
            <div className="agent-sent" data-testid={`agent-sent-${email.id}`}>
              <b>{a.draft.sent}</b> {a.draft.to}: {sent.to} · {a.draft.subject}: {sent.subject}
            </div>
          )}

          {saved && (
            <div className="agent-saved" data-testid={`agent-saved-${email.id}`}>
              <b>{saved.updated ? a.draft.savedUpdated : a.draft.savedNew}</b>{" "}
              {a.draft.to}: {saved.to}.{" "}
              <a href={saved.gmail_url} target="_blank" rel="noopener noreferrer">
                {a.draft.openGmail}
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
};


/**
 * Keresés a postafiókban.
 *
 * A futás az elmúlt 30 nap ötven levelét nézi; a keresés a Gmail saját
 * keresőjét kérdezi, tehát évekkel korábbi levél is előkerül. A találatokat
 * szándékosan nem osztályozzuk: az levelenként egy modellhívás, egy kereséstől
 * pedig azt várja az ember, hogy azonnal meglegyen — a lap ezt ki is írja,
 * hogy ne tűnjön hiányosságnak.
 */
const SearchPanel = ({ onResults, onClear, active }) => {
  const { t } = useLang();
  const a = t.agent;
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const run = async (e) => {
    e.preventDefault();
    const query = q.trim();
    if (query.length < 2 || busy) return;
    setBusy(true); setErr("");
    try {
      const data = await get(`/search?q=${encodeURIComponent(query)}`);
      onResults(data);
    } catch (e2) {
      setErr((e2.code && a.err[e2.code]) || e2.message || a.err.generic);
      onClear();
    } finally {
      setBusy(false);
    }
  };

  const clear = () => { setQ(""); setErr(""); onClear(); };

  return (
    <form className="agent-search" onSubmit={run} role="search" data-testid="agent-search">
      <label className="agent-search-label" htmlFor="agent-search-input">{a.search.label}</label>
      <div className="agent-search-row">
        <input id="agent-search-input" type="search" value={q} autoComplete="off"
          placeholder={a.search.placeholder} maxLength={120}
          onChange={(e2) => setQ(e2.target.value)} data-testid="agent-search-input" />
        <button type="submit" className="agent-search-go"
          disabled={busy || q.trim().length < 2} data-testid="agent-search-go">
          {busy ? <><span className="spin" /> {a.search.searching}</> : a.search.button}
        </button>
        {active && (
          <button type="button" className="agent-search-clear" onClick={clear}
            data-testid="agent-search-clear">
            {a.search.back}
          </button>
        )}
      </div>
      {err && <div className="agent-search-err" role="alert" data-testid="agent-search-err">{err}</div>}
    </form>
  );
};

export default function EmailAgent({ embedded = false }) {
  const { t, lang } = useLang();
  const a = t.agent;
  // Only the standalone route owns the document title; the homepage embeds the
  // same component and must keep its own metadata.
  useDocumentMeta({
    title: embedded ? "" : a.seo.title,
    description: a.seo.description,
    path: "/demo/email-agent",
    lang,
  });
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  // Off by default, and deliberately not remembered: handing over write access to
  // a mailbox is a decision to take each time, not one to inherit from last visit.
  const [allowDrafts, setAllowDrafts] = useState(false);
  // Same rule for the cleanup grant: moving mail out of the inbox is a wider
  // permission than reading it, so it is asked for only when it is wanted.
  const [allowCleanup, setAllowCleanup] = useState(false);
  const [starting, setStarting] = useState(false);
  // Cleanup state. `junkAsk` is the on-page confirmation for the bulk button:
  // one click must not empty a dozen rows out of someone's inbox.
  const [junkBusy, setJunkBusy] = useState(false);
  const [junkAsk, setJunkAsk] = useState(false);
  const [junkDone, setJunkDone] = useState(0);
  const [junkErr, setJunkErr] = useState("");
  // The Google route is real and works, but it puts an "unverified app" warning
  // in front of every visitor and asks a stranger for their mailbox. It stays,
  // one click away, for someone who actually wants it.
  const [showConnect, setShowConnect] = useState(false);
  const [onlyNeedsReply, setOnlyNeedsReply] = useState(false);
  const [openId, setOpenId] = useState(null);
  // A keresés találatai a futás eredménye helyett jelennek meg, nem mellette:
  // két lista egymás alatt csak kérdés lenne, hogy melyiket is nézem.
  const [search, setSearch] = useState(null);
  const timer = useRef(null);
  const retry = useRef(null);
  const pollRef = useRef(() => {});
  const intervalMs = useRef(0);

  // A futás alatt sűrűbben kérdezünk, mint utána. A levelek egyesével készülnek
  // el, és a lista már az első kész levéltől nő — háromemberes lekérdezéssel
  // viszont az első találat is állhat három másodpercig, ami egy húszmásodperces
  // futásnál az élmény hatoda. A válasz pár száz bájt, ez nem terhelés.
  const FAST_POLL_MS = 1000;
  const SLOW_POLL_MS = 3000;

  const restartTimer = useCallback((ms) => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => pollRef.current(), ms);
    intervalMs.current = ms;
  }, []);

  const poll = useCallback(async () => {
    try {
      const [p, r] = await Promise.all([get("/progress"), get("/results")]);
      setProgress(p);
      setResults(r);
      if (!p.running && timer.current) {
        clearInterval(timer.current);
        timer.current = null;
        return;
      }
      // Az első néhány levél után lassítunk: onnantól már van mit nézni.
      const enough = (r?.total || 0) >= 5;
      const want = p.running && !enough ? FAST_POLL_MS : SLOW_POLL_MS;
      if (timer.current && intervalMs.current !== want) restartTimer(want);
    } catch {
      if (timer.current) { clearInterval(timer.current); timer.current = null; }
    }
  }, [restartTimer]);

  // A setInterval a saját maga által hivatkozott poll-t fagyasztaná be az első
  // változatra; ez a ref mindig a friss függvényt adja.
  useEffect(() => { pollRef.current = poll; }, [poll]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const err = params.get("error");
    if (err) setError(a.err[err] || a.err.unknown);
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
          restartTimer(FAST_POLL_MS);
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
  }, [poll, restartTimer, a.err]);

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
      const { session } = await post(`/sample?lang=${lang}`, {});
      setToken(session);
      const s = await get("/status");
      setStatus(s);
      poll();
      restartTimer(FAST_POLL_MS);
    } catch (e) {
      setError(e.message || a.err.generic);
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
      const d = await get(
        `/connect?lang=${lang}` +
        (allowDrafts ? "&drafts=true" : "") +
        (allowCleanup ? "&cleanup=true" : "")
      );
      window.location.href = d.auth_url;
    } catch (e) {
      setConnecting(false);
      setError(e.message || a.err.generic);
    }
  };

  // Moves the given mail to Trash and reloads the run, so the list, the counts
  // and the junk block all come from the server rather than from a local guess
  // about what the server did. The server refuses anything outside the two junk
  // categories, so a wrong id here fails closed instead of deleting mail.
  const trash = async (ids) => {
    if (!ids || ids.length === 0 || junkBusy) return;
    setJunkBusy(true);
    setJunkErr("");
    try {
      const r = await post("/trash", { ids, confirm: true });
      setJunkDone((n) => n + (r.trashed || 0));
      setResults(await get("/results"));
      setOpenId(null);
    } catch (e) {
      setJunkErr(e.message || a.err.generic);
    } finally {
      setJunkBusy(false);
      setJunkAsk(false);
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
  // The server decides what counts as junk; the page only renders that list. The
  // sample mailbox can be tidied without any Google grant because there is no
  // mailbox behind it.
  const junkIds = (!search && results?.trashable) || [];
  const junkSet = new Set(junkIds);
  const canTrash = !!status && (status.sample === true || status.can_trash === true);

  return (
    <div className={embedded ? "agent-embed" : "agent-page"}>
      {!embedded && (
        <header className="agent-top">
          <Link to="/" className="agent-back">← AXIMBRA</Link>
          <span className={`agent-pill ${status?.connected ? "on" : ""}`}>
            {status?.connected ? status.email : a.notConnected}
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
            {!embedded && <h1>{a.title}</h1>}
            <div className="agent-closed" data-testid="agent-unreachable">
              <p>
                <b>{a.unreachable.title}</b> {a.unreachable.body}
              </p>
              <p>
                <button type="button" className="agent-retry"
                  onClick={() => window.location.reload()}>
                  {a.unreachable.retry}
                </button>
              </p>
            </div>
          </div>
        ) : !status.connected ? (
          <div className="agent-intro">
            {!embedded && <h1>{a.title}</h1>}
            <p className="agent-lead">{a.intro.lead}</p>

            <ul className="agent-guarantees">
              {a.intro.guarantees.map((g, i) => (
                <li key={i}><b>{g.t}</b> {g.d}</li>
              ))}
            </ul>

            {/* A demó korlátai szándékosak, és pont az ellenkezőjét mondják annak,
                amit a megrendelhető rendszer tud. Ha ez nincs kimondva, a látogató
                a demó korlátait hiszi a termék tulajdonságainak. */}
            <div className="agent-product" data-testid="agent-product">
              <h2>{a.product.title}</h2>
              <p>
                <b>{a.product.demoLead}</b> {a.product.demoText}
              </p>
              <p>
                <b>{a.product.yoursLead}</b> {a.product.yoursText}
              </p>
              <ul>
                {a.product.points.map((x, i) => <li key={i}>{x}</li>)}
              </ul>
              <p>
                <a href={mailto(a.product.cta)} className="agent-product-cta">{a.product.cta} →</a>
              </p>
            </div>

            {/* The specifics belong here, before the grant — not in a policy page
                the visitor would have to go looking for. Everything listed is what
                the code actually does; see backend/mail_agent.py. */}
            <details className="agent-disclosure" data-testid="agent-disclosure">
              <summary>{a.disclosure.summary}</summary>
              <div className="agent-disclosure-body">
                <h3>{a.disclosure.scopesTitle}</h3>
                <ul>
                  <li><code>gmail.readonly</code> — {a.disclosure.scopeRead}</li>
                  <li><code>userinfo.email</code> + <code>openid</code> — {a.disclosure.scopeIdentity}</li>
                  <li>
                    <code>gmail.compose</code> — <b>{a.disclosure.scopeComposeLead}</b>{" "}
                    {a.disclosure.scopeCompose}
                  </li>
                </ul>

                <h3>{a.disclosure.readTitle}</h3>
                <ul>
                  <li>{a.disclosure.read30}</li>
                  <li>{a.disclosure.readFields}</li>
                  <li><b>{a.disclosure.readAttachLead}</b> {a.disclosure.readAttach}</li>
                </ul>

                <h3>{a.disclosure.writeTitle}</h3>
                <ul>
                  <li>{a.disclosure.writeNoneLead} <b>{a.disclosure.writeNone}</b></li>
                  <li>{a.disclosure.writeDraft}</li>
                </ul>

                <h3>{a.disclosure.whereTitle}</h3>
                <ul>
                  <li>{a.disclosure.whereLlm}</li>
                  <li>{a.disclosure.whereNoDb}</li>
                </ul>

                <h3>{a.disclosure.lifeTitle}</h3>
                <ul>
                  <li>{a.disclosure.life30}</li>
                  <li>{a.disclosure.lifeExit}</li>
                  <li>
                    {a.disclosure.lifeRevoke}{" "}
                    <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">
                      myaccount.google.com/permissions
                    </a>
                  </li>
                </ul>

                <h3>{a.disclosure.whoTitle}</h3>
                <p>
                  AXIMBRA · Budapest · <a href={mailto()}>{CONTACT.email}</a>{" "}
                  {a.disclosure.whoText}
                </p>
              </div>
            </details>

            {error && <div className="agent-error">{error}</div>}

            {/* `public === false` is a deliberate setting, not a fault, so it reads
                as a status with a way forward rather than as an error. */}
            {status.public === false ? (
              <div className="agent-closed" data-testid="agent-closed">
                <p><b>{a.closed.title}</b> {a.closed.body}</p>
                <p>
                  {a.closed.live}{" "}
                  <a href={mailto(a.closed.liveSubject)}>{CONTACT.email}</a>
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
                    ? <><span className="spin" /> {a.start.starting}</>
                    : a.start.cta}
                </button>
                <p className="agent-start-note">{a.start.note}</p>
                <button type="button" className="agent-start-alt"
                  onClick={() => setShowConnect(true)} data-testid="agent-show-connect">
                  {a.start.alt}
                </button>
              </div>
            ) : (
              <>
                {status.configured === false && (
                  <div className="agent-error">{a.connect.notConfigured}</div>
                )}

                {/* Straight about what the visitor is walking into. Google shows an
                    "unverified app" warning for a restricted scope until the app
                    passes a security assessment; hiding that would waste their time
                    and look worse when it appears. */}
                <div className="agent-google-note" data-testid="agent-google-note">
                  <p><b>{a.connect.googleTitle}</b> {a.connect.googleBody}</p>
                  <p>{a.connect.googleHow}</p>
                  <button type="button" className="agent-start-alt"
                    onClick={() => setShowConnect(false)}>
                    {a.connect.back}
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
                    <b>{a.connect.optinTitle}</b> {a.connect.optinBody}
                    <span className="agent-optin-warn">{a.connect.optinWarn}</span>
                  </span>
                </label>

                {/* Second opt-in, separate from the first: tidying up moves mail
                    out of the inbox, which is a different decision from writing a
                    draft. Trash only - nothing is ever deleted for good. */}
                <label className="agent-optin" data-testid="agent-optin-cleanup">
                  <input type="checkbox" checked={allowCleanup} disabled={connecting}
                    onChange={(e) => setAllowCleanup(e.target.checked)}
                    data-testid="agent-optin-cleanup-box" />
                  <span>
                    <b>{a.connect.cleanupTitle}</b> {a.connect.cleanupBody}
                    <span className="agent-optin-warn">{a.connect.cleanupWarn}</span>
                  </span>
                </label>

                <button className="agent-cta" onClick={connect}
                  disabled={connecting || status.configured === false}>
                  {connecting ? <><span className="spin" /> {a.connect.redirecting}</>
                    : allowDrafts ? a.connect.ctaWrite
                    : allowCleanup ? a.connect.ctaClean
                    : a.connect.ctaRead}
                </button>

                {/* Google's verification asks for the Limited Use statement and the
                    privacy notice right where access is granted. The notice exists in
                    Hungarian and English only, so other languages get the English one. */}
                <p className="agent-start-note" data-testid="agent-limited-use">
                  {a.connect.privacyLead}{" "}
                  <Link to={lang === "hu" ? "/adatkezeles" : "/en/adatkezeles"}>{a.connect.privacyLink}</Link>
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="agent-run">
            {status.sample && (
              /* Said plainly: these results are real agent output on invented
                 mail, and must not read as the visitor's own inbox. */
              <div className="agent-sample-note" data-testid="agent-sample-note">
                <b>{a.run.sampleNoteTitle}</b> {a.run.sampleNote}
              </div>
            )}
            {!done && (
              <div className="agent-progress">
                <div className="agent-progress-head">
                  <span className="spin" />
                  {/* A kiszolgáló kulcsot küld, a feliratot a lap adja a saját
                      nyelvén. Ismeretlen kulcsnál a nyers érték marad, hogy egy
                      új állapot ne tűnjön el némán. */}
                  <span>{a.run[progress?.message] || progress?.message || a.run.starting}</span>
                  {progress?.total ? <span className="agent-count">{progress.done} / {progress.total}</span> : null}
                </div>
                <div className="agent-bar"><div className="agent-bar-fill" style={{ width: `${pct}%` }} /></div>
              </div>
            )}

            {(results?.total > 0 || search) && (
              <SearchPanel
                active={!!search}
                onResults={(d) => { setSearch(d); setOpenId(null); }}
                onClear={() => { setSearch(null); setOpenId(null); }} />
            )}

            {search && (
              <div className="agent-search-out" data-testid="agent-search-results">
                <div className="agent-search-head">
                  {/* Egyes szám külön: „1 results" minden nyelven hibásan szól. */}
                  {search.total === 1
                    ? fmt(a.search.results1, { q: search.query })
                    : search.total > 0
                      ? fmt(a.search.results, { n: search.total, q: search.query })
                      : fmt(a.search.none, { q: search.query })}
                </div>
                <p className="agent-search-note">{a.search.note}</p>
                <div className="agent-list">
                  {search.results.map((e) => {
                    const open = openId === `s:${e.id}`;
                    return (
                      <div className="agent-row" key={e.id} data-testid={`agent-hit-${e.id}`}>
                        <button className="agent-row-head"
                          onClick={() => setOpenId(open ? null : `s:${e.id}`)}>
                          <div className="agent-row-main">
                            <div className="agent-row-from">{e.sender}</div>
                            <div className="agent-row-subj">{e.subject || a.run.noSubject}</div>
                            <div className="agent-row-sum">{e.snippet}</div>
                          </div>
                          <span className="agent-row-date">{(e.date || "").slice(0, 10)}</span>
                        </button>
                        {open && (
                          <div className="agent-row-body">
                            <div className="k">{a.run.theEmail}</div>
                            <pre>{e.body || e.snippet || a.run.empty}</pre>
                            {!status.sample && (
                              <a className="agent-search-open" target="_blank" rel="noopener noreferrer"
                                href={`https://mail.google.com/mail/u/0/#all/${e.id}`}>
                                {a.search.openInGmail}
                              </a>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {!search && results && results.total > 0 && (
              <>
                <div className="agent-tiles">
                  <div className="agent-tile">
                    <div className="k">{a.run.processed}</div>
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
                    <div className="k">{a.run.needsReply}</div>
                    <div className="v accent">{results.needs_reply}</div>
                    {results.needs_reply > 0 && (
                      <div className="agent-tile-hint">
                        {onlyNeedsReply ? a.run.showAllShort : a.run.showThese}
                      </div>
                    )}
                  </button>
                  <div className="agent-tile wide">
                    <div className="k">{a.run.mostUrgent}</div>
                    <ul className="agent-top-list">
                      {results.top_urgent.map((e) => (
                        <li key={e.id}><span className={`dot-u ${urgencyOf(e.urgency).cls}`} />{e.subject || a.run.noSubject}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="agent-cats">
                  <div className="k">{a.run.categories}</div>
                  {Object.entries(results.counts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([cat, n]) => (
                      <div className="agent-cat-row" key={cat}>
                        <span className="agent-cat-name">{a.cat[cat] || cat}</span>
                        <span className="agent-cat-bar">
                          <span style={{ width: `${(n / results.total) * 100}%` }} />
                        </span>
                        <span className="agent-cat-n">{n}</span>
                      </div>
                    ))}
                </div>

                {/* Marks the mail nobody needs to read and offers one button for
                    all of it. Bulk deletion asks first, and the ids come from the
                    server's own junk list - the page never decides what is junk. */}
                {junkIds.length > 0 && (
                  <div className="agent-junk" data-testid="agent-junk">
                    <div className="agent-junk-head">
                      <div className="agent-junk-text">
                        <b>{a.run.junkTitle}</b>
                        <p>{a.run.junkNote}</p>
                      </div>
                      {!canTrash ? (
                        <p className="agent-junk-nogrant" data-testid="agent-junk-nogrant">
                          {a.run.junkNoGrant}
                        </p>
                      ) : junkAsk ? (
                        <div className="agent-junk-confirm" data-testid="agent-junk-confirm">
                          <span>{fmt(a.run.junkConfirm, { n: junkIds.length })}</span>
                          <button type="button" className="agent-junk-yes"
                            onClick={() => trash(junkIds)} disabled={junkBusy}
                            data-testid="agent-junk-yes">
                            {junkBusy ? a.run.junkBusy : a.run.junkYes}
                          </button>
                          <button type="button" className="agent-junk-no"
                            onClick={() => setJunkAsk(false)} disabled={junkBusy}>
                            {a.run.junkNo}
                          </button>
                        </div>
                      ) : (
                        <button type="button" className="agent-junk-all"
                          onClick={() => setJunkAsk(true)} disabled={junkBusy}
                          data-testid="agent-junk-all">
                          {fmt(a.run.junkAll, { n: junkIds.length })}
                        </button>
                      )}
                    </div>
                    {junkErr && <div className="agent-error">{junkErr}</div>}
                  </div>
                )}

                {junkDone > 0 && (
                  <div className="agent-junk-done" data-testid="agent-junk-done">
                    {fmt(a.run.junkDone, { n: junkDone })}
                  </div>
                )}

                {onlyNeedsReply && (
                  <div className="agent-filter-note" data-testid="agent-filter-note">
                    {a.run.filterNote}{" "}
                    <button type="button" onClick={() => setOnlyNeedsReply(false)}>
                      {fmt(a.run.showAllN, { n: results.total })}
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
                      <div className={`agent-row ${u.cls}${needs ? " needs" : ""}${junkSet.has(e.id) ? " junk" : ""}`} key={e.id}>
                        <button className="agent-row-head" onClick={() => setOpenId(open ? null : e.id)}>
                          <div className="agent-row-main">
                            <div className="agent-row-from">{e.sender}</div>
                            <div className="agent-row-subj">{e.subject || a.run.noSubject}</div>
                            <div className="agent-row-sum">{e.summary}</div>
                            <div className="agent-row-tags">
                              <span className="tag-cat">{a.cat[e.category] || e.category}</span>
                              <span className={`tag-u ${u.cls}`}>{a.urgency[u.cls]}</span>
                              {e.needs_reply === "igen" && <span className="tag-reply">{a.run.needsReply}</span>}
                              {junkSet.has(e.id) && <span className="tag-junk">{a.run.junkTag}</span>}
                              {e.deadline && <span className="tag-date">{e.deadline}</span>}
                            </div>
                          </div>
                          <span className="agent-row-date">{(e.date || "").slice(0, 10)}</span>
                        </button>
                        {/* Outside the row's own button: a button inside a button
                            is invalid markup and unreachable by keyboard. */}
                        {junkSet.has(e.id) && canTrash && (
                          <div className="agent-row-act">
                            <button type="button" onClick={() => trash([e.id])}
                              disabled={junkBusy}
                              data-testid={`agent-junk-one-${e.id}`}>
                              {junkBusy ? a.run.junkBusy : a.run.junkOne}
                            </button>
                          </div>
                        )}
                        {open && (
                          <div className="agent-row-body">
                            <div className="k">{a.run.whyUrgent}</div>
                            <p>{e.urgency_reason || "—"}</p>
                            <div className="k">{a.run.nextStep}</div>
                            <p>{e.next_step || "—"}</p>
                            <div className="k">{a.run.theEmail}</div>
                            <pre>{e.body || e.snippet || a.run.empty}</pre>
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
              <p className="agent-lead">{a.run.noEmails}</p>
            )}

            <button className="agent-cta ghost" onClick={disconnect}>
              {a.run.logout}
            </button>
            <p className="agent-foot">{a.run.foot}</p>
          </div>
        )}
      </main>
    </div>
  );
}

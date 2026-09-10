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
 * The text stays on the page. Nothing is written to the mailbox and nothing is
 * sent — copying it out is a deliberate step the visitor takes.
 */
const DraftPanel = ({ email }) => {
  const [tone, setTone] = useState("hivatalos");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  const write = async (nextTone) => {
    const useTone = nextTone || tone;
    setBusy(true); setErr(""); setCopied(false);
    try {
      setDraft(await post("/draft", { id: email.id, tone: useTone }));
      setTone(useTone);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
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
            <span className="agent-draft-note">
              Fogalmazvány — az agent nem küldi el, és a fiókodba sem írja be.
            </span>
          </div>
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
      "Élő demó: az AXIMBRA agentje átfutja a saját postafiókod elmúlt 30 napját, " +
      "kategorizálja és rangsorolja a leveleket. Csak olvas, semmit nem küld el és nem tárol.",
    path: "/demo/email-agent",
  });
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [openId, setOpenId] = useState(null);
  const timer = useRef(null);

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
    get("/status").then((s) => {
      setStatus(s);
      if (s.connected) {
        poll();
        timer.current = setInterval(poll, 3000);
      }
    }).catch(() => setStatus({ connected: false, configured: false }));
    return () => { if (timer.current) clearInterval(timer.current); };
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

  const connect = async () => {
    setConnecting(true);
    setError("");
    try {
      const d = await get("/connect");
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
        ) : !status.connected ? (
          <div className="agent-intro">
            {!embedded && <h1>E-mail rendező agent</h1>}
            <p className="agent-lead">
              Csatlakoztasd a Gmail-fiókod, és az agent végigmegy az elmúlt 30 nap
              levelein: kategóriába sorolja, sürgősséget állapít meg, és megmondja,
              melyikre kell válaszolnod.
            </p>

            <ul className="agent-guarantees">
              <li><b>Csak olvas.</b> Nem címkéz, nem csillagoz, nem töröl a fiókodban.</li>
              <li><b>Soha nem küld levelet.</b> A küldési jogot nem is kéri.</li>
              <li><b>Semmit nem tárolunk.</b> Az eredmény a böngésződ bezárásáig él.</li>
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
                    <code>gmail.readonly</code> — a leveleid olvasása.
                    Írási jogot nem kérünk: a Google-nál sincs módunk levelet
                    küldeni, címkézni vagy törölni a nevedben.
                  </li>
                  <li><code>userinfo.email</code> és <code>openid</code> — hogy tudjuk, melyik fiókot nézzük.</li>
                </ul>

                <h3>Mit olvasunk</h3>
                <ul>
                  <li>Az elmúlt <b>30 nap</b> legfeljebb <b>15 levele</b>. Semmi régebbi, semmi több.</li>
                  <li>Feladó, tárgy, dátum és a levél szövege — a mellékleteket nem nyitjuk meg.</li>
                </ul>

                <h3>Hová kerül</h3>
                <ul>
                  <li>
                    A levél szövegét egyetlen osztályozó hívásban elküldjük az
                    <b> OpenAI</b> API-jának. Az API-n beküldött adatot a szolgáltató
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
            ) : (
              <>
                {status.configured === false && (
                  <div className="agent-error">Az agent Google-hozzáférése még nincs beállítva.</div>
                )}
                <button className="agent-cta" onClick={connect}
                  disabled={connecting || status.configured === false}>
                  {connecting ? <><span className="spin" /> Átirányítás…</> : "Csatlakozás a Google-fiókhoz"}
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="agent-run">
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
                  <div className="agent-tile">
                    <div className="k">Válasz szükséges</div>
                    <div className="v accent">{results.needs_reply}</div>
                  </div>
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

                <div className="agent-list">
                  {results.analyses.map((e) => {
                    const u = urgencyOf(e.urgency);
                    const open = openId === e.id;
                    return (
                      <div className={`agent-row ${u.cls}`} key={e.id}>
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
                            <DraftPanel email={e} />
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

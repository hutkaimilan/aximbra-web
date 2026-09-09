import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "./email-agent.css";

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

const get = (path) => fetch(`${API}${path}`, { credentials: "include" }).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Hiba");
  return data;
});

export default function EmailAgent() {
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
    if (err || params.get("connected")) {
      window.history.replaceState({}, "", "/demo/email-agent");
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
    const end = () => navigator.sendBeacon && navigator.sendBeacon(`${API}/disconnect`);
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
    await fetch(`${API}/disconnect`, { method: "POST", credentials: "include" });
    window.location.assign("/demo/email-agent");
  };

  const done = progress && !progress.running && progress.total > 0;
  const pct = progress?.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <div className="agent-page">
      <header className="agent-top">
        <Link to="/" className="agent-back">← AXIMBRA</Link>
        <span className={`agent-pill ${status?.connected ? "on" : ""}`}>
          {status?.connected ? status.email : "Nincs csatlakozva"}
        </span>
      </header>

      <main className="agent-main">
        {!status ? (
          <div className="agent-center"><span className="spin" /></div>
        ) : !status.connected ? (
          <div className="agent-intro">
            <h1>E-mail rendező agent</h1>
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

            {error && <div className="agent-error">{error}</div>}
            {status.configured === false && (
              <div className="agent-error">Az agent Google-hozzáférése még nincs beállítva.</div>
            )}

            <button className="agent-cta" onClick={connect}
              disabled={connecting || status.configured === false}>
              {connecting ? <><span className="spin" /> Átirányítás…</> : "Csatlakozás a Google-fiókhoz"}
            </button>
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

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CONTACT, mailto } from "../contact";
import { useLang } from "../i18n";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/contact`;

/** A kiszolgáló a két másodpercnél gyorsabb beküldést robotnak veszi. Egy
 *  automatikus kitöltéssel dolgozó ember viszont tényleg végezhet ennyi alatt,
 *  és neki hibaüzenetet adni annyi, mint elveszíteni. Ezért nem hibázunk:
 *  kivárjuk a maradékot, és utána küldünk. A közvetlenül az API-nak beküldő
 *  robotot ez nem menti meg — az nem ezen a kódon megy keresztül. */
const MIN_FILL_MS = 2100;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Az űrlap csak akkor jelenik meg, ha a kiszolgáló tényleg tud levelet küldeni.
 *  Amíg nem tud, a régi — működő — levelezőprogramos út marad, mert egy űrlap,
 *  ami sikert ír ki a semmibe, csendben veszít el ügyfeleket. */
export function useContactFormEnabled() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    fetch(`${API}/status`)
      .then((r) => (r.ok ? r.json() : { configured: false }))
      .then((d) => alive && setEnabled(Boolean(d.configured)))
      .catch(() => alive && setEnabled(false));
    return () => { alive = false; };
  }, []);
  return enabled;
}

export function ContactForm() {
  const { t } = useLang();
  const f = t.contact.form;
  const openedAt = useRef(Date.now());
  const [values, setValues] = useState({ name: "", email: "", company: "", message: "", website: "" });
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState("idle");   // idle | sending | sent | error
  const [error, setError] = useState("");

  const set = (k) => (e) => setValues((v) => ({ ...v, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (state === "sending") return;
    setState("sending");
    setError("");
    try {
      const waited = Date.now() - openedAt.current;
      if (waited < MIN_FILL_MS) await sleep(MIN_FILL_MS - waited);
      const res = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...values, consent, elapsed_ms: Date.now() - openedAt.current }),
      });
      if (!res.ok) {
        // A kiszolgáló mondja meg, mi a baj — a mezőnkénti üzenet ott dől el,
        // és két helyen karbantartani ugyanazt a szabályt garantált eltérés.
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "");
        setState("error");
        return;
      }
      setState("sent");
    } catch (err) {
      setState("error");
    }
  };

  if (state === "sent") {
    return (
      <p className="contact-form-sent" role="status" data-testid="contact-form-sent">
        {f.sent}
      </p>
    );
  }

  return (
    <form className="contact-form" onSubmit={submit} noValidate data-testid="contact-form">
      <div className="cf-row">
        <label className="cf-field">
          <span className="cf-label">{f.name}</span>
          <input name="name" type="text" autoComplete="name" required maxLength={120}
            value={values.name} onChange={set("name")} data-testid="cf-name" />
        </label>
        <label className="cf-field">
          <span className="cf-label">{f.email}</span>
          <input name="email" type="email" autoComplete="email" required maxLength={200}
            value={values.email} onChange={set("email")} data-testid="cf-email" />
        </label>
      </div>

      <label className="cf-field">
        <span className="cf-label">{f.company}</span>
        <input name="company" type="text" autoComplete="organization" maxLength={160}
          value={values.company} onChange={set("company")} data-testid="cf-company" />
      </label>

      <label className="cf-field">
        <span className="cf-label">{f.message}</span>
        <textarea name="message" rows={5} required maxLength={4000} aria-describedby="cf-hint"
          value={values.message} onChange={set("message")} data-testid="cf-message" />
      </label>
      <p className="cf-hint" id="cf-hint">{f.messageHint}</p>

      {/* Csapdamező robotoknak. Nem `display:none`: azt a kitöltő szkriptek egy
          része felismeri; ez a képernyőolvasó elől is el van rejtve. */}
      <div className="cf-trap" aria-hidden="true">
        <label>
          Weboldal
          <input name="website" type="text" tabIndex={-1} autoComplete="off"
            value={values.website} onChange={set("website")} />
        </label>
      </div>

      <label className="cf-consent">
        <input type="checkbox" required checked={consent}
          onChange={(e) => setConsent(e.target.checked)} data-testid="cf-consent" />
        <span>
          {f.consent}{" "}
          <Link to="/adatkezeles" className="cf-link">{f.privacyLink}</Link>
        </span>
      </label>

      <div className="cf-actions">
        <button type="submit" className="cf-submit" disabled={state === "sending"} data-testid="cf-submit">
          {state === "sending" ? f.sending : f.send}
        </button>
      </div>

      {state === "error" && (
        <p className="cf-error" role="alert" data-testid="cf-error">
          {error || (
            <>
              {f.errorGeneric} <a href={mailto()}>{CONTACT.email}</a>{" "}
              {f.or} <a href={CONTACT.phoneHref}>{CONTACT.phone}</a>
            </>
          )}
        </p>
      )}
    </form>
  );
}

import { useState } from "react";
import { useLang } from "../i18n";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/voice/callback`;

/** A szerver `reason` kodja -> a nyelvi fajl uzenete. Ismeretlen kod eseten az
 *  altalanos hiba megy ki: egy nyers kulcsszo a kepernyon rosszabb, mint egy
 *  kicsit pontatlan magyar mondat. */
const MESSAGE_FOR = {
  number: "errNumber",
  country: "errCountry",
  repeat: "errRepeat",
  daily: "errDaily",
};

/**
 * "Hivjon vissza" - a latogato megadja a sajat szamat, es az agent hivja fel.
 *
 * Miert kell: a lap egy amerikai (+1) szamot hirdet. Egy magyar cegvezeto azt
 * nem tarcsazza fel elso talalkozasra, bejovo hivast viszont felvesz -
 * kulonosen azt, amit egy perce o maga kert. Igy a telefon-agent uj
 * telefonszam vasarlasa nelkul is kiprobalhato.
 *
 * Csak akkor jelenik meg, ha a szolgaltatas oldalan tenylegesen be van
 * kotve (`enabled`). Egy urlap, ami sose csorget vissza, tobbet art, mint
 * amennyit hasznal.
 */
export const CallbackForm = ({ enabled }) => {
  const { t, lang } = useLang();
  const c = t.hero.callback;

  const [phone, setPhone] = useState("");
  const [state, setState] = useState("idle"); // idle | sending | ok | error
  const [message, setMessage] = useState("");

  if (!enabled || !c) return null;

  const submit = async (e) => {
    e.preventDefault();
    // Dupla kattintas ne inditson ket hivast: a masodik ugyis a napi keretbe
    // utkozne, de a latogato egy zavaros hibauzenetet latna.
    if (state === "sending") return;

    const value = phone.trim();
    if (value === "") {
      setState("error");
      setMessage(c.errNumber);
      return;
    }

    setState("sending");
    setMessage("");
    try {
      const res = await fetch(API, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ phone: value, lang }),
      });
      let data = {};
      try {
        data = await res.json();
      } catch {
        // Ures vagy nem-JSON valasz: a statuszkod akkor is dont.
      }

      if (res.ok && data.ok) {
        setState("ok");
        setMessage(c.ok);
        setPhone("");
        return;
      }
      setState("error");
      setMessage(c[MESSAGE_FOR[data.reason]] || c.errFailed);
    } catch {
      // Halozati hiba: a hivas biztosan nem indult el.
      setState("error");
      setMessage(c.errFailed);
    }
  };

  return (
    <form className="callback" onSubmit={submit} data-testid="callback-form">
      <div className="callback-head">
        <h3 className="callback-title">{c.title}</h3>
        <p className="callback-lead">{c.lead}</p>
      </div>
      <div className="callback-row">
        <input
          className="callback-input"
          type="tel"
          name="phone"
          autoComplete="tel"
          inputMode="tel"
          maxLength={32}
          placeholder={c.placeholder}
          aria-label={c.cta}
          value={phone}
          onChange={(e) => {
            setPhone(e.target.value);
            // A korabbi uzenet ne maradjon ott egy mar atirt szam mellett.
            if (state !== "idle") { setState("idle"); setMessage(""); }
          }}
          disabled={state === "sending"}
          data-testid="callback-input"
        />
        <button
          type="submit"
          className="callback-btn"
          disabled={state === "sending"}
          data-testid="callback-submit"
        >
          {state === "sending" ? c.sending : c.cta}
        </button>
      </div>
      {message && (
        <p className={`callback-msg ${state}`} role="status" aria-live="polite" data-testid="callback-msg">
          {message}
        </p>
      )}
      <p className="callback-privacy">{c.privacy}</p>
    </form>
  );
};

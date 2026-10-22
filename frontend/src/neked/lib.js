/**
 * A /neked oldal kapcsolata a sales agenttel: az oldal adatának lekérése és a
 * megnyitás / kattintás jelzése. A komponensek az Emergent-féle demóoldalból
 * jönnek; ez a fájl köti őket a mi szerverünkhöz.
 */

export const SALES = process.env.REACT_APP_SALES_URL || "https://aximbra-sales-production.up.railway.app";

export const fmtNum = (n, lang) => {
  try {
    return new Intl.NumberFormat(lang || "hu").format(Math.round(n));
  } catch {
    return String(Math.round(n));
  }
};

export const fmtHuf = (n, lang) => `${fmtNum(n, lang)} Ft`;

export const mailtoHref = (email, company) =>
  `mailto:${email}?subject=${encodeURIComponent(company)}&body=${encodeURIComponent(window.location.href.split("?")[0] + "\n\n")}`;

let slug = null;
const sent = new Set();
const preview = () => new URLSearchParams(window.location.search).has("preview");

export const setTrackSlug = (s) => {
  slug = s;
};

// A komponensek eseménynevei -> a sales agent eseménytípusai.
const TYPES = { open: "open", demo_click: "demo", live_demo_click: "live", cta_click: "cta" };
const ONCE_PER_VIEW = new Set(["open", "demo_click"]);

/** Soha nem akaszthatja meg az oldalt: ha a kérés elszáll, elnyeljük. */
export const track = (event) => {
  const type = TYPES[event];
  if (!slug || !type || preview()) return;
  const key = `${slug}:${event}`;
  if (ONCE_PER_VIEW.has(event) && sent.has(key)) return;
  sent.add(key);
  try {
    fetch(`${SALES}/public/neked/${encodeURIComponent(slug)}/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* a számláló nem ronthatja el az oldalt */
  }
};

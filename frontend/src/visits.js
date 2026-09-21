/**
 * Oldalmegtekintés-jelzés a saját szerverünknek.
 *
 * Nincs süti, nincs localStorage, nincs harmadik fél — ezért nincs is
 * hozzájárulás-kérés. Amit elküld: melyik útvonalat nyitották meg, milyen
 * nyelven, és melyik oldalról érkeztek. A szerver a hivatkozóból csak a
 * domaint tartja meg (backend/visits.py).
 *
 * Soha nem állhat semminek az útjába: ha a kérés elszáll, elnyeljük. Egy
 * számláló nem ronthat el egy oldalbetöltést.
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/hit`;

export function useVisitBeacon(lang) {
  const { pathname } = useLocation();
  // Ugyanarra az útvonalra egyszer. A nyelvváltás nem új megtekintés:
  // ugyanaz az ember, ugyanazon a lapon — kétszer számolva a saját
  // számaidat hazudnád föl.
  const sent = useRef("");

  useEffect(() => {
    if (sent.current === pathname) return;
    sent.current = pathname;

    // A böngésző referrere csak az első betöltésnél van kitöltve; a lapon
    // belüli váltásnál üres, és az üres itt helyesen "közvetlen"-t jelent.
    const body = JSON.stringify({ path: pathname, ref: document.referrer || "", lang: lang || "" });

    fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  }, [pathname, lang]);
}

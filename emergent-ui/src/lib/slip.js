import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, errText } from "./api";

const Ctx = createContext(null);
export const useSlip = () => useContext(Ctx);

// A jobb oldali szelvény: tippek (ajánlat-azonosítóval), tét, és a TippmixPro ellenőrzése.
export function SlipProvider({ children, minStake = 100 }) {
  const [legs, setLegs] = useState([]);
  const [stake, setStake] = useState(1000);
  const [check, setCheck] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(null);
  const seq = useRef(0);

  const toggle = useCallback((leg) => {
    setLegs((ls) => (ls.some((l) => l.id === leg.id) ? ls.filter((l) => l.id !== leg.id) : [...ls, leg]));
  }, []);
  const replace = useCallback((newLegs, newStake) => {
    setLegs(newLegs);
    if (newStake) setStake(newStake);
  }, []);
  const clear = useCallback(() => setLegs([]), []);

  useEffect(() => {
    if (!legs.length) {
      setCheck(null);
      setError(null);
      return;
    }
    const my = ++seq.current;
    setChecking(true);
    const t = setTimeout(() => {
      api
        .check(legs.map((l) => l.id), Number(stake) || 0)
        .then((r) => my === seq.current && (setCheck(r), setError(null)))
        .catch((e) => my === seq.current && setError(errText(e)))
        .finally(() => my === seq.current && setChecking(false));
    }, 350);
    return () => clearTimeout(t);
  }, [legs, stake]);

  const value = { legs, stake, setStake, toggle, replace, clear, check, checking, error, minStake };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

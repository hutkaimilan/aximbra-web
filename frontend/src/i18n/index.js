import { createContext, useContext, useEffect, useState } from "react";
import hu from "./hu";
import en from "./en";
import de from "./de";
import es from "./es";
import fr from "./fr";
import it from "./it";
import ro from "./ro";
import sk from "./sk";
import demos from "./demos";

export const LANGS = [
  ["hu", "Magyar"], ["en", "English"], ["de", "Deutsch"], ["es", "Español"],
  ["fr", "Français"], ["it", "Italiano"], ["ro", "Română"], ["sk", "Slovenčina"],
];

const RAW = { hu, en, de, es, fr, it, ro, sk };

const isObj = (x) => x && typeof x === "object" && !Array.isArray(x);

function merge(base, over) {
  if (over === undefined) return base;
  if (Array.isArray(base) && Array.isArray(over)) {
    const out = base.slice();
    for (let i = 0; i < over.length; i++) out[i] = merge(base[i], over[i]);
    return out;
  }
  if (isObj(base) && isObj(over)) {
    const out = { ...base };
    for (const k of Object.keys(over)) out[k] = merge(base[k], over[k]);
    return out;
  }
  return over;
}

// Fallback chain per language: <lang> over English over Hungarian.
const resolved = {};
for (const code of Object.keys(RAW)) {
  const r = merge(merge(hu, en), RAW[code]);
  r.demos = merge(merge(demos.hu, demos.en), demos[code] || {});
  resolved[code] = r;
}

const LangCtx = createContext(null);
const STORAGE_KEY = "aximbra_lang";

export const LanguageProvider = ({ children }) => {
  const [lang, setLangState] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && resolved[saved]) return saved;
    } catch (e) {}
    return "hu";
  });

  useEffect(() => {
    document.documentElement.lang = lang;
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
  }, [lang]);

  const setLang = (l) => { if (resolved[l]) setLangState(l); };

  return (
    <LangCtx.Provider value={{ lang, setLang, t: resolved[lang] }}>
      {children}
    </LangCtx.Provider>
  );
};

export const useLang = () => useContext(LangCtx);

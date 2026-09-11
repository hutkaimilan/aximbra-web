import { createContext, useContext, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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

/** Hungarian is the primary market and owns the bare URLs; the rest are prefixed.
 *  Keeping /  unprefixed also means no existing link or share ever breaks. */
export const DEFAULT_LANG = "hu";
export const PREFIXED_LANGS = LANGS.map(([c]) => c).filter((c) => c !== DEFAULT_LANG);

/** Split "/en/impresszum" into { lang: "en", rest: "/impresszum" }. */
export function splitLangPath(pathname) {
  const m = /^\/([a-z]{2})(\/.*)?$/.exec(pathname || "/");
  if (m && PREFIXED_LANGS.includes(m[1])) {
    return { lang: m[1], rest: m[2] || "/" };
  }
  return { lang: DEFAULT_LANG, rest: pathname || "/" };
}

/** Build the URL for one page in one language. `rest` is the unprefixed path. */
export function pathFor(lang, rest = "/") {
  const clean = rest.startsWith("/") ? rest : `/${rest}`;
  if (lang === DEFAULT_LANG) return clean;
  return clean === "/" ? `/${lang}` : `/${lang}${clean}`;
}

export const LanguageProvider = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { lang, rest } = splitLangPath(location.pathname);

  // The URL is the source of truth, not component state: a language has to
  // survive a reload, a shared link and a crawler, and only the address can do
  // all three. localStorage is kept as a courtesy for the next bare visit.
  useEffect(() => {
    document.documentElement.lang = lang;
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
  }, [lang]);

  const setLang = (next) => {
    if (!resolved[next] || next === lang) return;
    navigate(pathFor(next, rest) + location.search, { replace: false });
  };

  return (
    <LangCtx.Provider value={{ lang, setLang, t: resolved[lang], path: rest }}>
      {children}
    </LangCtx.Provider>
  );
};

export const useLang = () => useContext(LangCtx);

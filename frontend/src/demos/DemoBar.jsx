import { Link } from "react-router-dom";
import { useLang, LANGS } from "../i18n";

export const DemoBar = ({ prefix }) => {
  const { t, lang, setLang } = useLang();
  return (
    <div className={`${prefix}-bar`}>
      <Link to="/" className={`${prefix}-back`} data-testid="demo-back">{t.demos.back}</Link>
      <select className={`${prefix}-lang`} data-testid="demo-lang" value={lang}
        onChange={(e) => setLang(e.target.value)} aria-label="Language">
        {LANGS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
      </select>
    </div>
  );
};

import { Link } from "react-router-dom";
import { useLang, LANGS } from "../i18n";

/**
 * Header shared by the four reference demo sites.
 *
 * The notice is not decoration: each of these pages looks like a real
 * business, with an address, opening hours and a contact form. A visitor who
 * lands on one from a shared link — rather than from the AXIMBRA homepage —
 * has nothing else telling them the business does not exist.
 */
export const DemoBar = ({ prefix }) => {
  const { t, lang, setLang } = useLang();
  const d = t.demos;
  // Notice and bar share one fixed wrapper, so the bar sits below the notice
  // whatever height the notice text wraps to — no measured offset to drift.
  return (
    <div className="demo-top">
      <div className="demo-notice" role="note" data-testid="demo-notice">
        <strong>{d.noticeTag}</strong>
        <span>{d.noticeText}</span>
      </div>
      <div className={`${prefix}-bar`}>
        <Link to="/" className={`${prefix}-back`} data-testid="demo-back">{d.back}</Link>
        <select className={`${prefix}-lang`} data-testid="demo-lang" value={lang}
          onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {LANGS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
        </select>
      </div>
    </div>
  );
};

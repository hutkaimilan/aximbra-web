import { Link } from "react-router-dom";
import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";
import { mailto } from "../contact";
import { useLang, pathFor } from "../i18n";
import { formatPrice, parseToken } from "../money";

/** A "900000+" alak nyitott ar: a nyelv sajat szokoszerkezete teszi ra a
 *  "-tol"-t, mert nemetul elol all ("ab 2 250 €"), magyarul hatul. */
const priceText = (token, lang, fromFmt) => {
  const text = formatPrice(token, lang, "full");
  if (!text) return "";
  const p = parseToken(token);
  return p && p.open ? String(fromFmt || "{p}").replace("{p}", text) : text;
};

/** A csomagok rácsa. A főoldalról a /weboldal oldalra költözött: egy AI-agent
 *  ügynökség főoldalának közepén három weboldalcsomag azt kérdezteti az
 *  olvasóval, hogy végül is mit árulunk. */
export const PricingPackages = () => {
  const { t, lang } = useLang();
  const p = t.pricing;
  return (
    <div className="pkg-grid">
      {p.packages.map((pkg, i) => {
        const featured = i === 1;
        const href = mailto(`${p.subjectPrefix} – ${pkg.name}`);
        return (
          <Reveal key={i} delay={i * 100}>
            <div className={`pkg-card ${featured ? "featured" : ""}`} data-testid={`pkg-card-${i}`}>
              {featured && <div className="pkg-badge" data-testid="pkg-popular">{p.popular}</div>}
              <div className="pkg-name">{pkg.name}</div>
              <div className="pkg-price">{priceText(pkg.price, lang, p.fromFmt)}</div>
              <div className="pkg-net">{p.netNote}</div>
              <ul className="pkg-features">
                {pkg.features.map((f, j) => <li key={j}>{f}</li>)}
              </ul>
              <LiquidButton as="a" href={href} ghost={!featured} className="pkg-btn" data-testid={`pkg-cta-${i}`}>
                {p.cta}
              </LiquidButton>
            </div>
          </Reveal>
        );
      })}
      {p.fxNote && <p className="pkg-fx" data-testid="pricing-fx-note">{p.fxNote}</p>}
    </div>
  );
};

/** Ami a főoldalon marad: egy sáv, ami kimondja, hogy weboldalt is készítünk,
 *  és átvisz oda. Az árak nem tűnnek el, csak nem szakítják félbe az agentekről
 *  szóló gondolatmenetet. */
export const Pricing = () => {
  const { t, lang } = useLang();
  const p = t.pricing;
  return (
    <section className="container" id="weboldal-sav" data-testid="pricing-teaser">
      <Reveal>
        <div className="web-band">
          <div>
            <span className="tag">{p.tag}</span>
            <h2 className="web-band-h">{p.heading}</h2>
            <p className="web-band-sub">{p.sub}</p>
          </div>
          <LiquidButton as={Link} to={pathFor(lang, "/weboldal")} data-testid="pricing-to-page">
            {p.bandCta}
          </LiquidButton>
        </div>
      </Reveal>
    </section>
  );
};

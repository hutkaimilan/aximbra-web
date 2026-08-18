import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";

export const Pricing = () => {
  const { t } = useLang();
  const p = t.pricing;
  return (
    <section className="container" id="arak" data-testid="pricing-section">
      <Reveal>
        <span className="tag">{p.tag}</span>
        <h2 className="h-sec">{p.heading}</h2>
        <p className="sub">{p.sub}</p>
      </Reveal>
      <div className="pkg-grid">
        {p.packages.map((pkg, i) => {
          const featured = i === 1;
          const href = `mailto:aximbra@gmail.com?subject=${encodeURIComponent(`${p.subjectPrefix} – ${pkg.name}`)}`;
          return (
            <Reveal key={i} delay={i * 100}>
              <div className={`pkg-card ${featured ? "featured" : ""}`} data-testid={`pkg-card-${i}`}>
                {featured && <div className="pkg-badge" data-testid="pkg-popular">{p.popular}</div>}
                <div className="pkg-name">{pkg.name}</div>
                <div className="pkg-price">{pkg.price}</div>
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
      </div>
    </section>
  );
};

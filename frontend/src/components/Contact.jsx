import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";

export const Contact = () => {
  const { t } = useLang();
  const c = t.contact;
  return (
    <section className="container" id="kapcsolat" data-testid="contact-section">
      <Reveal>
        <div className="contact-card">
          <h2>{c.heading}</h2>
          <p>{c.para}</p>
          <div className="contact-cta">
            <LiquidButton as="a" href="mailto:aximbra@gmail.com" data-testid="contact-email">
              aximbra@gmail.com
            </LiquidButton>
            <LiquidButton ghost disabled data-testid="contact-phone-disabled">
              {c.phoneDisabled}
            </LiquidButton>
          </div>
        </div>
      </Reveal>
    </section>
  );
};

export const Footer = () => {
  const { t } = useLang();
  return (
    <footer className="footer" data-testid="footer">
      <div className="container">
        <div>{t.footer.left}</div>
        <div>{t.footer.right}</div>
      </div>
    </footer>
  );
};

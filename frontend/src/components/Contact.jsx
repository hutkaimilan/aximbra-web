import { Link } from "react-router-dom";
import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";
import { CONTACT, mailto } from "../contact";
import { useLang } from "../i18n";
import { ContactForm, useContactFormEnabled } from "./ContactForm";

export const Contact = () => {
  const { t } = useLang();
  const c = t.contact;
  // Az űrlap csak akkor lép a gombok helyére, ha a kiszolgáló tud küldeni.
  const formEnabled = useContactFormEnabled();
  return (
    <section className="container" id="kapcsolat" data-testid="contact-section">
      <Reveal>
        <div className="contact-card">
          <h2>{c.heading}</h2>
          <p>{c.para}</p>
          {formEnabled && <ContactForm />}
          <div className={formEnabled ? "contact-cta secondary" : "contact-cta"}>
            <LiquidButton as="a" href={mailto()} data-testid="contact-email">
              {CONTACT.email}
            </LiquidButton>
            <LiquidButton ghost as="a" href={CONTACT.phoneHref} data-testid="contact-phone">
              {CONTACT.phone}
            </LiquidButton>
          </div>
          <p className="contact-phone-note" data-testid="contact-phone-note">{c.phoneNote}</p>
          <p className="contact-phone-origin" data-testid="contact-phone-origin">{c.phoneOrigin}</p>
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
        {/* A jogi oldalak a láblécben vannak, ahol keresni szokás őket — egy
            tájékoztató, amire nem lehet eljutni, semmit nem old meg. */}
        <div className="footer-legal">
          <Link to="/impresszum">{t.footer.imprint}</Link>
          <Link to="/adatkezeles">{t.footer.privacy}</Link>
        </div>
        <div>{t.footer.right}</div>
      </div>
    </footer>
  );
};

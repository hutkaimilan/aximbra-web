import { Link } from "react-router-dom";
import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER } from "../legal";
import { useLang, pathFor } from "../i18n";
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

/** A lábléc, ahol egy weboldal hitelessége eldől.
 *
 *  A Stanford háromévnyi, több mint négyezer emberrel végzett vizsgálata után
 *  kiadott hitelességi irányelvei közül négy pont ide szól: legyen látható,
 *  hogy valódi szervezet áll mögötte; legyen könnyű felvenni a kapcsolatot;
 *  legyen látható, hogy nevesített ember felel érte; és legyen könnyű
 *  ellenőrizni, amit állít. A lábléc eddig ennyit mondott: „AXIMBRA · Budapest
 *  · aximbra.hu” — abból egyik sem derült ki.
 *
 *  Az adatok a legal.js-ből és a contact.js-ből jönnek, nem ide írva: ugyanaz
 *  a név és cím áll itt, mint az impresszumban, és egy javítás mindkét helyen
 *  landol. Az adószám addig „bejegyzés alatt”, amíg tényleg nincs — kitalálni
 *  pont az a hiba lenne, amit ez a szakasz orvosolni hivatott. */
export const Footer = () => {
  const { t, lang } = useLang();
  const f = t.footerId;
  return (
    <footer className="footer" data-testid="footer">
      <div className="container footer-id">
        <div className="footer-col" data-testid="footer-who">
          <span className="footer-h">{f.who}</span>
          <strong>{CONTROLLER.name}</strong>
          <span className="footer-sub">{f.person}</span>
          <address>
            {CONTROLLER.postcode} {CONTROLLER.city}<br />
            {CONTROLLER.addressLine}<br />
            {CONTROLLER.country}
          </address>
          {/* Ha nincs adószám, a lábléc nem mond róla semmit. A „bejegyzés
              alatt” is állítás lenne, és nem tudom, igaz-e. */}
          {CONTROLLER.taxNumber && (
            <span className="footer-sub" data-testid="footer-tax">
              {f.taxLabel}: {CONTROLLER.taxNumber}
            </span>
          )}
        </div>

        <div className="footer-col" data-testid="footer-reach">
          <span className="footer-h">{f.reach}</span>
          <a href={mailto()} data-testid="footer-email">{CONTACT.email}</a>
          <a href={CONTACT.phoneHref} data-testid="footer-phone">{CONTACT.phone}</a>
          <span className="footer-sub">{f.phoneNote}</span>
          <p className="footer-reply">{f.replyNote}</p>
        </div>

        <div className="footer-col" data-testid="footer-legal">
          <span className="footer-h">{f.legalTag}</span>
          <div className="footer-legal">
            <Link to={pathFor(lang, "/impresszum")}>{t.footer.imprint}</Link>
            <Link to={pathFor(lang, "/adatkezeles")}>{t.footer.privacy}</Link>
          </div>
          <span className="footer-sub footer-note">{t.footer.right}</span>
        </div>
      </div>
      <div className="container footer-base">
        <span>{t.footer.left}</span>
      </div>
    </footer>
  );
};

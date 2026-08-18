import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";

export const Contact = () => (
  <section className="container" id="kapcsolat" data-testid="contact-section">
    <Reveal>
      <div className="contact-card">
        <h2>Melyik feladat viszi el a heted?</h2>
        <p>
          Írd meg egy mondatban. Két munkanapon belül megmondjuk, megéri-e agentet építeni rá — és ha nem, azt is.
        </p>
        <div className="contact-cta">
          <LiquidButton as="a" href="mailto:aximbra@gmail.com" data-testid="contact-email">
            aximbra@gmail.com
          </LiquidButton>
          <LiquidButton ghost disabled data-testid="contact-phone-disabled">
            Telefonos agent — hamarosan
          </LiquidButton>
        </div>
      </div>
    </Reveal>
  </section>
);

export const Footer = () => (
  <footer className="footer" data-testid="footer">
    <div className="container">
      <div>AXIMBRA · Budapest · aximbra.hu</div>
      <div>Az EPISTEME saját fejlesztésű bemutató rendszer, nem ügyfélmunka.</div>
    </div>
  </footer>
);

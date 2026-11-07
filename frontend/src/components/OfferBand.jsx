import { Reveal } from "./Reveal";
import { useLang } from "../i18n";
import { offerFor } from "../neked/lib";

/** Az ajánlat a főoldalon is, a nyitókép alatt: ugyanaz a mondat, mint a
 *  levelekben és a demóoldalakon (neked/lib.js), így sehol nem tér el. */
export const OfferBand = () => {
  const { lang } = useLang();
  const [title, text] = offerFor(lang);
  return (
    <section className="container" id="ajanlat" data-testid="offer-band">
      <Reveal>
        <div className="offer-band">
          <span className="tag">{title}</span>
          <p className="offer-band-text">{text}</p>
        </div>
      </Reveal>
    </section>
  );
};

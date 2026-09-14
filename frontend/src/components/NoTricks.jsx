import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

/** Amit ez az oldal nem fog megtenni.
 *
 *  Közvetlenül az árazás után áll, mert a nyomásgyakorlás szokásos helye pont
 *  ott van. Kimondani, hogy mi marad el, olcsóbb és ellenőrizhetőbb, mint egy
 *  újabb ígéret: a látogató két kattintással leellenőrizheti, hogy tényleg
 *  nincs itt visszaszámláló és tényleg ki van írva a bemutatóoldalakra, hogy
 *  kitaláltak. */
export const NoTricks = () => {
  const { t } = useLang();
  const n = t.noTricks;
  if (!n) return null;
  return (
    <section className="container" id="amit-nem" data-testid="notricks-section">
      <Reveal>
        <span className="tag">{n.tag}</span>
        <h2 className="h-sec">{n.heading}</h2>
        <p className="sub">{n.sub}</p>
      </Reveal>
      <Reveal delay={90}>
        <ul className="notricks">
          {n.items.map((it, i) => (
            <li key={i} data-testid={`notricks-${i}`}>
              <strong>{it.head}</strong>
              <span>{it.body}</span>
            </li>
          ))}
        </ul>
        <p className="notricks-close" data-testid="notricks-close">{n.close}</p>
      </Reveal>
    </section>
  );
};

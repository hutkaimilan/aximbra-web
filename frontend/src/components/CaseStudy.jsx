import { useState } from "react";
import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";

const MediaFallback = ({ big, sm }) => (
  <div className="media-box"><div className="big">{big}</div><div className="sm">{sm}</div></div>
);

export const CaseStudy = () => {
  const [videoOk, setVideoOk] = useState(true);
  const [audioOk, setAudioOk] = useState(true);
  return (
    <section className="container" id="eset" data-testid="case-section">
      <Reveal>
        <span className="tag">Működés közben</span>
        <h2 className="h-sec">Egy telefonáló agent, éles vonalon</h2>
      </Reveal>
      <Reveal>
        <div className="case">
          <div className="case-grid">
            <div>
              <h3>EPISTEME <span className="pill-amber">SAJÁT DEMÓ</span></h3>
              <p>
                Háromnyelvű étterem-asszisztens, ami felveszi a telefont, asztalt foglal, és ugyanazt a
                szabadhely-számlálót írja, amit a weboldal. Nem prototípus: valódi telefonszámon fut,
                valódi SMS-visszaigazolást küld.
              </p>
              <ul>
                <li>Magyar, angol és spanyol nyelven beszél, hívás közben vált</li>
                <li>Telefon és web ugyanazon a foglalási állapoton osztozik</li>
                <li>Félbeszakítható — nem kell végighallgatni</li>
                <li>Napi híváskeret és hívásidő-korlát a kiszámítható költségért</li>
              </ul>
              <LiquidButton ghost as="a" href="https://epistemebudapest.up.railway.app"
                target="_blank" rel="noopener noreferrer" data-testid="episteme-link">
                Weboldal megnyitása →
              </LiquidButton>
            </div>
            <div>
              {videoOk ? (
                <video className="demo-media" controls preload="metadata" poster="/media/episteme-poster.jpg"
                  data-testid="episteme-video" onError={() => setVideoOk(false)}>
                  <source src="/media/episteme-demo.mp4" type="video/mp4" />
                </video>
              ) : (
                <MediaFallback big="▶ Videó — hamarosan" sm="Képernyőfelvétel a webes foglalásról, elejétől a visszaigazolásig." />
              )}
              {audioOk ? (
                <audio className="demo-media" controls preload="metadata"
                  data-testid="episteme-audio" onError={() => setAudioOk(false)}>
                  <source src="/media/episteme-hivas.mp3" type="audio/mpeg" />
                </audio>
              ) : (
                <MediaFallback big="♪ Hangfelvétel — hamarosan" sm="Valódi hívás az agenttel, magyar nyelven." />
              )}
              <div className="phone-card" data-testid="phone-card">
                <div className="lbl">Hívd fel most</div>
                <div className="num">+1 949 810 7263</div>
                <div className="hint">Kérj asztalt bármelyik nyelven.<br />Napi keret: 20 hívás.</div>
              </div>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
};

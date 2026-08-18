import { useState } from "react";
import { Reveal } from "./Reveal";
import { LiquidButton } from "./LiquidButton";
import { useLang } from "../i18n";

const MediaFallback = ({ big, sm }) => (
  <div className="media-box"><div className="big">{big}</div><div className="sm">{sm}</div></div>
);

export const CaseStudy = () => {
  const { t } = useLang();
  const c = t.caseStudy;
  const [videoOk, setVideoOk] = useState(true);
  const [audioOk, setAudioOk] = useState(true);

  return (
    <section className="container" id="eset" data-testid="case-section">
      <Reveal>
        <span className="tag">{c.tag}</span>
        <h2 className="h-sec">{c.heading}</h2>
      </Reveal>
      <Reveal>
        <div className="case">
          <div className="case-grid">
            <div>
              <h3>EPISTEME <span className="pill-amber">{c.pill}</span></h3>
              <p>{c.para}</p>
              <ul>
                {c.bullets.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
              <LiquidButton ghost as="a" href="https://epistemebudapest.up.railway.app"
                target="_blank" rel="noopener noreferrer" data-testid="episteme-link">
                {c.link}
              </LiquidButton>
            </div>
            <div>
              {videoOk ? (
                <video className="demo-media" controls preload="metadata" poster="/media/episteme-poster.jpg"
                  data-testid="episteme-video" onError={() => setVideoOk(false)}>
                  <source src="/media/episteme-demo.mp4" type="video/mp4" />
                </video>
              ) : (
                <MediaFallback big={c.videoBig} sm={c.videoSm} />
              )}

              <div className="audio-block" data-testid="audio-block">
                <div className="audio-caption">{c.audioCaption}</div>
                {audioOk ? (
                  <audio className="demo-media" controls preload="none"
                    data-testid="episteme-audio" onError={() => setAudioOk(false)}>
                    <source src="/media/episteme-hivas.mp3" type="audio/mpeg" />
                  </audio>
                ) : (
                  <div className="audio-error" data-testid="episteme-audio-error">{c.audioError}</div>
                )}
              </div>

              <div className="phone-card" data-testid="phone-card">
                <div className="lbl">{c.phoneLabel}</div>
                <div className="num">+1 949 810 7263</div>
                <div className="hint">{c.phoneHint[0]}<br />{c.phoneHint[1]}</div>
              </div>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
};

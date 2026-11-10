import { useState } from "react";
import { Reveal } from "./Reveal";
import { useLang } from "../i18n";

/**
 * Our first project, kept only as a recording. The system behind it no longer
 * runs, so the section carries no name, link, phone number or audio — just the
 * screen recording and a line that says plainly it is not live any more.
 */
export const CaseStudy = () => {
  const { t } = useLang();
  const c = t.caseStudy;
  const [videoOk, setVideoOk] = useState(true);

  return (
    <section className="container" id="eset" data-testid="case-section">
      <Reveal>
        <span className="tag">{c.tag}</span>
        <h2 className="h-sec">{c.heading}</h2>
      </Reveal>
      <Reveal>
        <div className="case case-body">
          <p className="case-note" data-testid="case-note">{c.note}</p>
          {videoOk ? (
            <video className="demo-media" controls preload="metadata" poster="/media/episteme-poster.jpg"
              data-testid="case-video" onError={() => setVideoOk(false)}>
              <source src="/media/episteme-demo.mp4" type="video/mp4" />
            </video>
          ) : (
            <div className="media-box"><div className="big">{c.videoBig}</div></div>
          )}
        </div>
      </Reveal>
    </section>
  );
};

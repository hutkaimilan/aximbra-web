import { Reveal } from "./Reveal";
import EmailAgent from "@/demos/EmailAgent";

export const EmailAgentSection = () => (
  <section className="container" id="email-agent" data-testid="email-agent-section">
    <Reveal>
      <span className="tag">Próbáld ki a saját postafiókodon</span>
      <h2 className="h-sec">Az e-mail rendező agent, <span className="grad">élesben</span></h2>
      <p className="sub">
        Csatlakoztasd a Gmail-fiókod, és az agent itt, ezen az oldalon végigmegy az
        elmúlt 30 nap levelein. Csak olvas, semmit nem tárolunk, és amikor kilépsz,
        a fiókod azonnal lecsatlakozik.
      </p>
    </Reveal>
    <Reveal delay={90}>
      <EmailAgent embedded />
    </Reveal>
  </section>
);

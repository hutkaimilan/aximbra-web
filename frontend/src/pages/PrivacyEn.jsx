import { useEffect } from "react";
import { Link } from "react-router-dom";
import "./legal.css";
import { CONTACT, mailto } from "../contact";
import { CONTROLLER, CONTROLLER_ADDRESS_EN, LEGAL_UPDATED_EN, PROCESSORS } from "../legal";
import { useDocumentMeta } from "../seo";
import { pathFor } from "../i18n";

/**
 * English translation of the privacy notice (Adatkezeles.jsx).
 *
 * It exists for Google's OAuth verification: the reviewers read English, and
 * the consent screen links a privacy policy that has to state, in words they
 * can check, how Gmail data is used. The Hungarian page stays authoritative
 * and says so here. Every section mirrors the Hungarian one — change both, or
 * the two will promise different things.
 */
export default function PrivacyEn({ lang }) {
  useDocumentMeta({
    title: "Privacy notice | AXIMBRA",
    description:
      "What data the website and the demo agents process, for how long, who receives it, " +
      "and how to ask for it to be deleted.",
    path: "/adatkezeles",
    lang,
    // A translation of the Hungarian text, not a separate page: the canonical
    // stays on the Hungarian URL.
    translated: false,
  });
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="legal-page">
      <header className="legal-top">
        <Link to={pathFor(lang, "/")} className="legal-back">← AXIMBRA</Link>
      </header>

      <main className="legal-main">
        <h1>Privacy notice</h1>
        <p className="legal-lead">
          This notice describes what the system <i>actually</i> does — not in general
          terms. Where a number appears here, the code uses the same number.
        </p>
        <p className="legal-note">
          This is an English translation. The <Link to="/adatkezeles">Hungarian version</Link>{" "}
          is the authoritative one.
        </p>

        <section>
          <h2>1. Who processes your data</h2>
          <dl className="legal-dl">
            <div><dt>Controller</dt><dd>{CONTROLLER.name}</dd></div>
            <div><dt>Address</dt><dd>{CONTROLLER_ADDRESS_EN}</dd></div>
            <div><dt>Email</dt><dd><a href={mailto()}>{CONTACT.email}</a></dd></div>
          </dl>
          <p className="legal-note">
            AXIMBRA is a brand name, not a registered company. Appointing a data
            protection officer is not mandatory and has not been done.
          </p>
        </section>

        <section>
          <h2>2. Using the website</h2>
          <p>
            <b>No analytics and no tracking cookies.</b> We do not use Google
            Analytics, advertising pixels or any other tracker.
          </p>
          <p>
            Your browser's storage keeps four small items, only on your device, and
            they never reach us:
          </p>
          <p>
            <b>Traffic.</b> For each page view we record which page was opened, in
            which language, and which site the visitor came from — of that last one
            only the domain (for example <code>google.com</code>), never the search
            term or the full address. <b>We do not store IP addresses</b>, set no
            cookie for it, and build no identifier that would let a visitor be
            followed. The data stays aggregated on our own server; we use no
            third-party analytics service. That is why we do not ask for consent to
            it: this set of data is not personal data.
          </p>
          <ul>
            <li>the selected language (<code>aximbra_lang</code>),</li>
            <li>where you were on the page when you opened a demo, so you come back to the
              same place (<code>aximbra:return</code>, kept until the tab is closed),</li>
            <li>the email agent's session ID, if you connected your account
              (<code>aximbra:agent</code>, also until the tab is closed).</li>
          </ul>
          <p>
            To prevent abuse, for calls to the demo systems the server keeps the request's
            IP address and time in memory for <b>one hour</b>, so that it can enforce the
            hourly limit. This is not written to a database and expires without a trace
            after one hour.
          </p>
          <p>
            Separately, the <b>hosting provider</b> (Railway) keeps its own operational log
            of every request: the time of the request, the address called, the response
            code, the browser identifier and the request's IP address. The provider keeps
            this log under its own retention period; we can read it when debugging, but
            cannot delete it.
            Legal basis: legitimate interest (GDPR Art. 6(1)(f)) — keeping the service
            running and preventing abuse.
          </p>
        </section>

        <section>
          <h2>3. Contacting us</h2>
          <p>
            There are two ways to reach us, and they do not do the same thing.
          </p>
          <ul>
            <li>
              <b>Email and phone buttons:</b> these open your own email program or your
              phone. The website sees nothing of what you write.
            </li>
            <li>
              <b>Enquiry form:</b> the name, email address, optional company name and
              message you enter reach the controller in a single email, through our server
              and an email delivery provider (Resend). It is not written to a database and
              is not stored on the server; the log only records that a message arrived — not
              its content. The form filters out bots with a hidden field and the time taken
              to fill it in; neither is included in the email.
            </li>
          </ul>
          <p>
            What you send this way is kept as long as the matter requires, for at most{" "}
            <b>2 years</b>. Legal basis: for the form, your consent (GDPR Art. 6(1)(a)); for
            correspondence, steps taken before entering into a contract and legitimate
            interest (GDPR Art. 6(1)(b) and (f)).
          </p>
        </section>

        <section>
          <h2>4. Lead qualifier demo</h2>
          <p>
            What you type into the field (up to 4,000 characters) is sent to the OpenAI API
            in a single call, and the result is returned to the page.{" "}
            <b>Neither the text nor the result is stored</b> — there is no database behind
            it. Legal basis: consent (GDPR Art. 6(1)(a)), which you give by starting the demo.
          </p>
          <p className="legal-note">
            Please do not paste in real personal data — the demo does not need it.
          </p>
        </section>

        <section>
          <h2>5. Email triage agent</h2>
          <p>
            This system can be used in two ways, and there is a big difference between them.
          </p>

          <h3>With the sample inbox</h3>
          <p>
            This is the default. The emails are invented ones we put together.{" "}
            <b>We do not ask for Google access, and none of your data reaches us.</b>
          </p>

          <h3>With your own Gmail account</h3>
          <p>If you decide to connect your account:</p>
          <ul>
            <li>
              <b>What we read:</b> the sender, subject, date and text of at most{" "}
              <b>50</b> emails from the last <b>30 days</b>.
            </li>
            <li>
              <b>Attachments:</b> we only open an attachment when the text of the email is
              not enough on its own — then we extract the text of at most <b>two</b> files
              per email, up to <b>5 MB</b> per file (Word, Excel, PowerPoint, PDF, plain text
              and CSV). We do not open images, videos or other formats, and{" "}
              <b>we do not run OCR</b>: no text is extracted from a scanned document. The file
              itself goes nowhere; the extracted text reaches the OpenAI API together with the
              text of the email, and is gone when the run ends.
            </li>
            <li>
              <b>What access we ask for:</b> by default, read-only
              (<code>gmail.readonly</code>). If you separately tick draft writing, also{" "}
              <code>gmail.compose</code>. Google has no "drafts only" permission, so this
              permission would in itself also allow sending — but the system never sends on
              its own: it only sends when you separately confirm it for a specific email. If
              you tick the cleanup box, we also ask for <code>gmail.modify</code>: reading is
              not enough to move an existing message.
            </li>
            <li>
              <b>What we write:</b> without the tick, nothing. With draft writing, for one
              email at a time and always after your separate confirmation: a reply draft in
              your Gmail Drafts, and — if you confirm that too — sending that draft.
            </li>
            <li>
              <b>What we move:</b> without the tick, nothing. Even with cleanup, only the
              messages the agent classified as newsletters or unsolicited mail — which ones
              those are is decided by the server from the analysis currently open, so no
              other message can be reached by the button. Moving always happens on your
              click, with a separate confirmation for bulk deletion. Messages go to your
              Gmail Trash (<code>users.messages.trash</code>), where Gmail keeps them
              recoverable for about 30 days — we never delete anything permanently
              (<code>delete</code>, <code>batchDelete</code>). We do not label or star.
            </li>
            <li>
              <b>Where it goes:</b> the text of the emails is sent to the OpenAI API, one call
              per classification. Nothing is written to a database.
            </li>
            <li>
              <b>How long it lives:</b> the run lives in the server's memory and expires on
              its own after <b>30 minutes</b>. The "Log out and disconnect" button deletes it
              immediately. When you close the page, the browser signals the server and the run
              is deleted immediately then too — if that signal does not arrive (lost network,
              killed browser), the 30-minute limit ends it.
            </li>
            <li>
              <b>How to revoke access:</b> at any time — with the log out button on our side,
              and at Google here:{" "}
              <a href="https://myaccount.google.com/permissions"
                target="_blank" rel="noopener noreferrer">
                myaccount.google.com/permissions
              </a>
            </li>
          </ul>
          <p>
            Legal basis: consent (GDPR Art. 6(1)(a)), which you give on Google's consent
            screen and can withdraw at any time.
          </p>
        </section>

        <section>
          <h2>6. Limited use of Google user data</h2>
          <p>
            AXIMBRA's use and transfer of information received from Google APIs adheres to
            the{" "}
            <a href="https://developers.google.com/terms/api-services-user-data-policy"
              target="_blank" rel="noopener noreferrer">
              Google API Services User Data Policy
            </a>, including the Limited Use requirements.
          </p>
          <p>Data read from Gmail is used only to:</p>
          <ul>
            <li>categorise and rank your emails on the page,</li>
            <li>and — if you ask for it — write reply drafts to them.</li>
          </ul>
          <p>
            We <b>do not use</b> this data for advertising, do not sell it, do not transfer it
            to third parties beyond what providing the features above requires, and{" "}
            <b>do not use it to train any artificial intelligence model</b>. The only third
            party that receives email content is OpenAI, through its API, to produce the
            categorisation and the drafts shown to you; under OpenAI's API terms, data sent
            through the API is not used to train its models. No human reads the data unless
            you separately agree to it, or it is required for security reasons or by law.
          </p>
        </section>

        <section>
          <h2>7. Phone calls</h2>
          <p>
            On the phone number shown on the site, your caller ID decides who answers:
          </p>
          <ul>
            <li>
              <b>from a Hungarian (+36) number</b> the call is forwarded to the controller's
              mobile phone. No transcript or summary is made; your number and the time of the
              call are recorded in Twilio's call log and in the server log;
            </li>
            <li>
              <b>from any other country</b>, from a hidden number, or if the controller does
              not answer, the call is answered by an AI agent.
            </li>
          </ul>
          <p>When the AI agent answers the call, we process:</p>
          <ul>
            <li>your phone number, and the time and length of the call,</li>
            <li>a text transcript of the conversation,</li>
            <li>and a short summary made from it.</li>
          </ul>
          <p>
            <b>No audio is recorded.</b> The transcript and the summary reach the controller by
            email, so that we can call you back. We keep them for at most <b>2 years</b>.
            Legal basis: consent — the agent tells you about it at the start of the call, and
            you can stop at any time by hanging up.
          </p>
        </section>

        <section>
          <h2>8. Who receives the data</h2>
          <p>Our processors, and what for:</p>
          <div className="legal-table-wrap">
            <table className="legal-table">
              <thead>
                <tr><th>Provider</th><th>Purpose</th><th>Location</th></tr>
              </thead>
              <tbody>
                {PROCESSORS.map((p) => (
                  <tr key={p.name}>
                    <td>{p.name}</td><td>{p.roleEn}</td><td>{p.whereEn}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="legal-note">
            For providers operating in the United States, the transfer relies on the
            safeguards each provider commits to in its own data processing terms (standard
            contractual clauses, and the EU–US Data Privacy Framework where applicable).
            Beyond these, we do not pass your data to anyone, and we do not sell it.
          </p>
        </section>

        <section>
          <h2>9. Your rights</h2>
          <p>Under the GDPR you can ask for:</p>
          <ul>
            <li>a copy of the data we hold about you (access),</li>
            <li>inaccurate data to be corrected,</li>
            <li>your data to be deleted,</li>
            <li>processing to be restricted,</li>
            <li>your data in a portable format,</li>
            <li>and you can object to processing based on legitimate interest.</li>
          </ul>
          <p>
            Write to <a href={mailto("Privacy request")}>{CONTACT.email}</a>, and we will
            reply <b>within 30 days</b>. For most of the demos the answer will be that there is
            nothing to delete, because we store nothing — but we will still answer the request
            properly.
          </p>
        </section>

        <section>
          <h2>10. Complaints</h2>
          <p>
            If you think your data is being processed unlawfully, you can turn to the
            supervisory authority:
          </p>
          <dl className="legal-dl">
            <div><dt>Authority</dt><dd>Hungarian National Authority for Data Protection and Freedom of Information (NAIH)</dd></div>
            <div><dt>Address</dt><dd>Falk Miksa utca 9-11, 1055 Budapest, Hungary</dd></div>
            <div><dt>Website</dt><dd>
              <a href="https://naih.hu" target="_blank" rel="noopener noreferrer">naih.hu</a>
            </dd></div>
          </dl>
          <p>You can also go to court, at the regional court of your place of residence.</p>
        </section>

        <section>
          <h2>11. Changes</h2>
          <p>
            When the system changes, this notice changes too. The bottom of the page always
            shows when it was last updated.
          </p>
        </section>

        <p className="legal-updated">Effective: {LEGAL_UPDATED_EN}</p>
      </main>
    </div>
  );
}

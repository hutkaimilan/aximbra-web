/**
 * One source of truth for every AXIMBRA contact detail on the site.
 *
 * The site previously carried AXIMBRA's address in some places and EPISTEME's
 * (a separate demo project) in others, which read as two different companies.
 * Import from here instead of writing an address inline, so a change lands
 * everywhere at once.
 */
export const CONTACT = {
  email: "aximbra@gmail.com",
  // Voice-agent test line. EPISTEME's own number lives in the case study and is
  // deliberately not reused here.
  phone: "+1 802 424 9852",
  phoneHref: "tel:+18024249852",
  city: "Budapest",
  domain: "aximbra.hu",
};

/** mailto: link to AXIMBRA with a prefilled subject. */
export const mailto = (subject) =>
  subject
    ? `mailto:${CONTACT.email}?subject=${encodeURIComponent(subject)}`
    : `mailto:${CONTACT.email}`;

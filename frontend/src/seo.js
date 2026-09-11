import { useEffect } from "react";
import { CONTACT } from "./contact";

/**
 * Per-route document metadata.
 *
 * Every route previously inherited one hardcoded Hungarian <title> and
 * description from index.html — the four demo sites and all eight languages
 * included. This sets them per route and per language instead, and fills in the
 * canonical and social tags that were missing entirely.
 *
 * The canonical origin is read from REACT_APP_SITE_URL when set, and otherwise
 * from the browser. Falling back to the live origin is deliberate: hardcoding a
 * domain the deployment does not actually serve would point canonical at a page
 * that does not exist.
 */
const ORIGIN =
  process.env.REACT_APP_SITE_URL?.replace(/\/+$/, "") ||
  (typeof window !== "undefined" ? window.location.origin : "");

const JSONLD_ID = "aximbra-jsonld";

function setMeta(selector, attr, value) {
  if (!value) return;
  let el = document.head.querySelector(selector);
  if (!el) {
    el = document.createElement("meta");
    const [, kind, name] = selector.match(/\[(property|name)="([^"]+)"\]/) || [];
    if (!kind) return;
    el.setAttribute(kind, name);
    document.head.appendChild(el);
  }
  el.setAttribute(attr, value);
}

function setLink(rel, href) {
  if (!href) return;
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

/**
 * @param {object} meta
 * @param {string} meta.title     full <title> text
 * @param {string} meta.description meta description, ~150-160 chars
 * @param {string} [meta.path]    route path, for the canonical URL (default "/")
 * @param {string} [meta.lang]    BCP-47 code, for og:locale
 * @param {boolean} [meta.noindex] keep the page out of search results
 * @param {object} [meta.jsonLd]  structured data to publish for this route
 */
export function useDocumentMeta({ title, description, path = "/", lang, noindex, jsonLd }) {
  // Serialised, because callers build the object inline: a fresh object every
  // render would tear the script tag down and rebuild it on every render.
  const jsonLdText = jsonLd ? JSON.stringify(jsonLd) : "";
  useEffect(() => {
    // An empty title means "this render is not the page owner" — the email agent
    // renders both as its own route and embedded in the homepage, and the
    // embedded copy must not overwrite the homepage's canonical or title.
    if (!title) return;
    const url = ORIGIN ? `${ORIGIN}${path}` : "";
    document.title = title;
    setMeta('meta[name="description"]', "content", description);
    setLink("canonical", url);

    setMeta('meta[property="og:type"]', "content", "website");
    setMeta('meta[property="og:site_name"]', "content", "AXIMBRA");
    setMeta('meta[property="og:title"]', "content", title);
    setMeta('meta[property="og:description"]', "content", description);
    setMeta('meta[property="og:url"]', "content", url);
    if (lang) setMeta('meta[property="og:locale"]', "content", lang);
    // Absolute, because social scrapers do not resolve relative URLs.
    const image = ORIGIN ? `${ORIGIN}/media/og-cover.png` : "";
    setMeta('meta[property="og:image"]', "content", image);
    setMeta('meta[name="twitter:card"]', "content", "summary_large_image");
    setMeta('meta[name="twitter:image"]', "content", image);
    setMeta('meta[name="twitter:title"]', "content", title);
    setMeta('meta[name="twitter:description"]', "content", description);

    // The demo sites are inventions; they must not compete with the real site
    // in search results, or be mistaken for the businesses they portray.
    setMeta('meta[name="robots"]', "content", noindex ? "noindex, follow" : "index, follow");

    const prev = document.getElementById(JSONLD_ID);
    if (prev) prev.remove();
    if (jsonLdText) {
      const el = document.createElement("script");
      el.type = "application/ld+json";
      el.id = JSONLD_ID;
      el.textContent = jsonLdText;
      document.head.appendChild(el);
    }
  }, [title, description, path, lang, noindex, jsonLdText]);
}

/** Organization + WebSite data for the homepage. Only facts already on the page. */
export const organizationJsonLd = (description) => ({
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${ORIGIN}/#organization`,
      name: "AXIMBRA",
      url: ORIGIN || undefined,
      description,
      email: CONTACT.email,
      telephone: CONTACT.phone,
      areaServed: { "@type": "City", name: CONTACT.city },
    },
    {
      "@type": "WebSite",
      "@id": `${ORIGIN}/#website`,
      url: ORIGIN || undefined,
      name: "AXIMBRA",
      publisher: { "@id": `${ORIGIN}/#organization` },
    },
  ],
});

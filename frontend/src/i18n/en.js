const CALLBAR = "mailto:epistemebudapest@gmail.com?subject=" + encodeURIComponent("How many calls are we missing?");

const en = {
  nav: {
    links: [["Agents", "agentek"], ["Process", "folyamat"], ["Pricing", "arak"], ["Case study", "eset"]],
    contact: "CONTACT",
    callbar: "How many calls does your venue miss?",
    callbarHref: CALLBAR,
  },
  hero: {
    eyebrow: "Budapest · AI agency",
    h1: ["We don't build", "chatbots. We build", "coworkers."],
    sub: "We build AI agents for Hungarian companies that do one concrete job — sort emails, qualify leads, answer the phone. We don't hand over a demo, but a working system that we keep alive.",
    ctaPrimary: "See the agents",
    ctaGhost: "See it live",
    stats: [["2–4 weeks", "the first agent"], ["3 languages", "HU · EN · ES"], ["100%", "human approval"]],
  },
  agentsSection: {
    tag: "What we build",
    heading: "Twelve agents, one building logic",
    sub: "Each is built from the same module set, so the second is always faster than the first. You can try the ones marked live — a real model runs behind them.",
    tryOpen: "Try it live ↓",
    tryClose: "Close",
  },
  agents: [
    { title: "Email sorter", badge: "Live", live: true, demo: "email", desc: "Reads incoming emails, sorts them into categories, assesses urgency, and tells you who they belong to.", price: "150–400 eFt", lead: "2–4 weeks" },
    { title: "Lead qualifier", badge: "Live", live: true, demo: "lead", desc: "Reviews incoming leads, scores them, and tells you what to do with each — today or in three months.", price: "400 eFt – 1.2 MFt", lead: "3–5 weeks" },
    { title: "Internal admin agent", badge: "Demo", live: false, desc: "Moves data between systems, compiles reports, fills out forms. The invisible work no one misses.", price: "150–400 eFt", lead: "2–4 weeks" },
    { title: "Research monitor", badge: "Demo", live: false, desc: "Watches competitors, regulation or the market, and only speaks up when something actually happened.", price: "150–400 eFt", lead: "2–4 weeks" },
    { title: "Customer support agent", badge: "Demo", live: false, desc: "Answers from your own documents, with sources. What it doesn't know, it hands to a human — it doesn't make things up.", price: "1.5–4 MFt", lead: "6–10 weeks" },
    { title: "Content agent", badge: "Demo", live: false, desc: "Trained on one voice: newsletter, product copy, social post. Approval stays with you.", price: "400 eFt – 1.2 MFt", lead: "2–3 weeks" },
    { title: "Webshop assistant", badge: "Demo", live: false, desc: "Recommends products, checks stock, tracks orders. It works against cart abandonment, not against the visitor.", price: "600 eFt – 1.5 MFt", lead: "3–5 weeks" },
    { title: "Document analyzer", badge: "Demo", live: false, desc: "Reads contracts, invoices and quotes, and pulls out the seven fields someone used to read the whole thing for.", price: "2–4 MFt", lead: "6–8 weeks" },
    { title: "Financial assistant", badge: "Demo", live: false, desc: "Categorizes costs, flags anomalies, compiles reports. Every statement has a source line behind it.", price: "2–4 MFt", lead: "6–8 weeks" },
    { title: "Recruitment agent", badge: "Demo", live: false, desc: "Pre-screens CVs by structured criteria. Because of the EU AI Act, it includes an audit log and human override.", price: "1.7–3.9 MFt", lead: "3–4 weeks + legal" },
    { title: "IT operations agent", badge: "Demo", live: false, desc: "Watches logs, classifies alerts, runs the fix for known issues. What it doesn't recognize, it wakes you for.", price: "600 eFt – 2 MFt", lead: "3–6 weeks" },
    { title: "Multi-agent system", badge: "Demo", live: false, desc: "Several agents in one process, with handoffs and checkpoints. Worth it only when the process is genuinely complex.", price: "6–15 MFt", lead: "10–16 weeks" },
  ],
  process: {
    tag: "How we work",
    heading: "Six steps, one human gate",
    sub: "Most agents are built by agents. What doesn't change: a human is the one who approves — not because the model is bad, but because responsibility can't be delegated.",
    steps: [
      { n: "01", title: "Workflow mapping", desc: "We look at where time goes. We don't ask what you'd like to automate, but which task repeats fifty times a week." },
      { n: "02", title: "Specification, with a schema", desc: "The agreement is recorded in machine-readable form: what the input is, what the output is, what counts as an error. This document later becomes the basis of the test." },
      { n: "03", title: "Build in an isolated environment", desc: "Every project gets its own sealed runtime. One error can't spill over into another client's system." },
      { n: "04", title: "Independent review", desc: "Finished work isn't reviewed by whoever wrote it. A separate reviewer runs on it, with empty context and read-only access — so it can't defend its own decisions." },
      { n: "05", title: "Human approval", desc: "Nothing ships without approval. The gate isn't a formality: this is where it turns out if something is technically correct but wrong for the business.", amber: "◆ A human decides, not AI" },
      { n: "06", title: "Handover and operation", desc: "The agent runs on your infrastructure, with your keys. The monthly fee covers supervision and fixes, not access." },
    ],
  },
  pricing: {
    tag: "Pricing",
    heading: "Website design and development",
    sub: "Modern, fast, mobile-optimized sites — with real content, in live operation.",
    netNote: "net price, excluding hosting and domain",
    popular: "Most popular",
    cta: "Request a quote",
    subjectPrefix: "Quote request",
    packages: [
      { name: "One-page presence", price: "120 000 Ft", features: ["single-page, mobile-optimized site", "contact, opening hours, Google Maps", "ready in 3–5 days"] },
      { name: "Multi-page business", price: "290 000 Ft", features: ["multiple subpages, gallery, contact form", "basic SEO and Google indexing", "ready in 1–2 weeks"] },
      { name: "Custom / AI-integrated", price: "from 900 000 Ft", features: ["booking system or AI chat / voice agent", "custom features on request", "quote-based, with an agreed deadline"] },
    ],
  },
  caseStudy: {
    tag: "In action",
    heading: "A calling agent, on a live line",
    pill: "OUR OWN DEMO",
    para: "A three-language restaurant assistant that answers the phone, books a table, and writes to the same free-seat counter as the website. Not a prototype: it runs on a real phone number and sends a real SMS confirmation.",
    bullets: [
      "Speaks Hungarian, English and Spanish, switching mid-call",
      "Phone and web share the same booking state",
      "Interruptible — you don't have to hear it out",
      "Daily call quota and call-time limit for predictable cost",
    ],
    link: "Open the website →",
    audioCaption: "A real phone call with the AI receptionist — about 50 seconds.",
    audioError: "The audio is currently unavailable.",
    videoBig: "▶ Video — coming soon",
    videoSm: "Screen recording of the web booking, from start to confirmation.",
    phoneLabel: "Call now",
    phoneHint: ["Ask for a table in any language.", "Daily quota: 20 calls."],
  },
  contact: {
    heading: "Which task eats up your week?",
    para: "Write it in one sentence. Within two working days we'll tell you whether it's worth building an agent for it — and if not, that too.",
    phoneDisabled: "Phone agent — coming soon",
  },
  footer: {
    left: "AXIMBRA · Budapest · aximbra.hu",
    right: "EPISTEME is our own in-house demo system, not client work.",
  },
  marquee: ["AGENTS, NOT CHATBOTS", "HUMAN APPROVAL", "BUDAPEST", "HU · EN · ES", "WORKING SYSTEM"],
  demo: {
    run: "Run", loading: "Analyzing…", sample: "Example", error: "Couldn't reach the service. Please try again later.",
    email: {
      placeholder: "Paste the text of an incoming email…",
      samples: [
        "Dear Support Team, the product I ordered last week arrived damaged, the box was torn. Please arrange a replacement as soon as possible, I'm very disappointed. I await your urgent reply.",
        "Hello! I'd like a quote for 200 custom-printed t-shirts for a company event. We'd plan delivery for June. What prices and lead time can you offer?",
        "Hi! The amount on my invoice doesn't match the order, I see a duplicate item. Could you check and correct it? Not urgent, but it'd be good to settle by the end of the month.",
      ],
      fields: [["kategoria", "Category"], ["surgosseg", "Urgency"], ["felelos", "Owner"], ["valaszhatarido", "Response deadline"], ["osszefoglalo", "Summary", true], ["javasolt_lepes", "Suggested step", true]],
    },
    lead: {
      placeholder: "Describe the incoming lead in a few sentences…",
      samples: [
        "The managing director of a 40-person Budapest accounting firm reached out. They process hundreds of incoming invoices manually each month and want to automate it. They have budget, want to start this year, and he makes the purchasing decision.",
        "A student wrote asking for a free AI agent for their thesis. No company, no budget, just curious how the technology works.",
        "A marketer at a mid-size webshop is interested in a customer-support agent. They don't know exactly what they want yet, the owner makes the decision, timing is uncertain, but the problem is real.",
      ],
      fields: [["minosites", "Rating"], ["igeny", "Need"], ["koltsegvetes", "Budget"], ["donteshozo", "Decision maker"], ["hatarido", "Timeline"], ["indoklas", "Reasoning", true], ["javasolt_lepes", "Suggested step", true]],
    },
  },
};

export default en;

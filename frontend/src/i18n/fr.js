import { mailto } from "../contact";
const CALLBAR = mailto("Combien d'appels manquons-nous ?");

// Per-language search/social copy. Previously every language served the
// Hungarian, unaccented title and description from index.html.
const SEO = {
  title: "AXIMBRA — Agence IA à Budapest | Agents IA sur mesure",
  description: "Nous construisons des agents IA qui font un vrai travail : tri des e-mails, qualification des leads, accueil téléphonique. Démos en direct sur le site.",
};

const fr = {
  seo: SEO,
  nav: {
    links: [["Agents", "agentek"], ["Processus", "folyamat"], ["Sites web", "weboldal", "/weboldal"], ["Étude de cas", "eset"]],
    contact: "CONTACT",
    callbar: "Combien d'appels votre établissement manque-t-il ?",
    callbarHref: CALLBAR,
    menu: "Menu",
    intro: "AGENTS IA · BUDAPEST",
  },
  hero: {
    phoneCta: { badge: "IA", note: "Répondu par un agent IA · en anglais et en hongrois", origin: "Numéro américain (Twilio) — les appels de numéros non hongrois sont pris par l'agent IA ; au début, vous choisissez le hongrois ou l'anglais" },
    // A "hivjon vissza" urlap. A lap egy amerikai szamot hirdet; egy
    // magyar cegvezeto azt nem tarcsazza, bejovo hivast viszont felvesz.
    callback: {
      title: "Ou nous vous appelons, tout de suite",
      lead: "Indiquez votre numéro et l'agent vous appelle en 10 secondes. C'est gratuit, et vous pouvez raccrocher à tout moment.",
      placeholder: "+33 6 12 34 56 78",
      cta: "Rappelez-moi",
      sending: "Numérotation…",
      ok: "C'est parti — l'agent appelle. Votre téléphone sonnera dans 10 secondes.",
      errNumber: "Je ne reconnais pas ce numéro. Essayez ainsi : +33 6 12 34 56 78",
      errCountry: "Nous ne pouvons pas appeler cet indicatif pays, désolé.",
      errRepeat: "Nous avons déjà appelé ce numéro aujourd'hui. Réessayez demain.",
      errDaily: "Le quota du jour est épuisé. Réessayez demain, ou écrivez-nous.",
      errFailed: "L'appel n'a pas pu être lancé. Réessayez dans quelques minutes.",
      privacy: "Le numéro sert uniquement à cet appel et n'est jamais transmis.",
    },
    eyebrow: "Budapest · agence IA",
    h1: ["Nous ne créons pas", "de chatbots. Mais un", "collaborateur."],
    sub: "Nous créons des agents IA pour les entreprises qui accomplissent une tâche concrète — trier les e-mails, qualifier les demandes, répondre au téléphone. Nous ne livrons pas une démo, mais un système qui fonctionne et que nous maintenons en vie.",
    ctaPrimary: "Voir les agents",
    ctaGhost: "Voir en direct",
    stats: [["2–4 semaines", "le premier agent"], ["3 langues", "parlées par l'agent téléphonique"], ["100%", "validation humaine"]],
  },
  agentsSection: {
    tag: "Ce que nous construisons",
    heading: "Douze agents, une logique de construction",
    sub: "Chacun est construit à partir du même jeu de modules, c'est pourquoi le deuxième est toujours plus rapide que le premier. Ceux marqués en direct sont à essayer — un vrai modèle tourne derrière.",
    tryOpen: "Essayer en direct ↓",
    tryClose: "Fermer",
    simOpen: "Le voir en action",
    skip: "Aller à la fin →",
    approve: "Valider",
    rewrite: "Demander une réécriture",
    approved: "Validé — cela part.",
    rewritten: "Renvoyé pour réécriture.",
    again: "↻ Recommencer",
    sampleNote: "Une illustration avec des données d'exemple en hongrois — les e-mails sont inventés.",
  },
  agents: [
    { title: "Trieur d'e-mails", badge: "En direct", desc: "Lit les e-mails entrants, les classe par catégorie, évalue l'urgence et indique à qui ils reviennent.", lead: "2–4 semaines" },
    { title: "Qualificateur de leads", badge: "En direct", desc: "Examine les demandes entrantes, les note et indique quoi en faire — aujourd'hui ou dans trois mois.", lead: "3–5 semaines" },
    { title: "Agent d'administration interne", badge: "Démo", desc: "Transfère des données entre systèmes, compile des rapports, remplit des formulaires. Le travail invisible qui ne manque à personne.", lead: "2–4 semaines" },
    { title: "Moniteur de veille", badge: "Démo", desc: "Surveille les concurrents, la réglementation ou le marché, et n'intervient que quand il s'est vraiment passé quelque chose.", lead: "2–4 semaines" },
    { title: "Agent de support client", badge: "Démo", desc: "Répond à partir de vos propres documents, avec les sources. Ce qu'il ne sait pas, il le transmet à un humain — il n'invente pas.", lead: "6–10 semaines" },
    { title: "Agent de contenu", badge: "Démo", desc: "Entraîné sur un ton : newsletter, fiche produit, publication sociale. La validation reste chez vous.", lead: "2–3 semaines" },
    { title: "Assistant e-commerce", badge: "Démo", desc: "Recommande des produits, vérifie les stocks, suit les commandes. Il agit contre l'abandon de panier, pas contre le visiteur.", lead: "3–5 semaines" },
    { title: "Analyseur de documents", badge: "Démo", desc: "Lit contrats, factures et devis, et en extrait les sept champs pour lesquels quelqu'un lisait tout jusqu'ici.", lead: "6–8 semaines" },
    { title: "Assistant financier", badge: "Démo", desc: "Catégorise les coûts, signale les écarts, compile des rapports. Derrière chaque affirmation, une ligne de source.", lead: "6–8 semaines" },
    { title: "Agent de recrutement", badge: "Démo", desc: "Présélectionne les CV selon des critères structurés. En raison de l'AI Act de l'UE, avec journal d'audit et contrôle humain.", lead: "3–4 semaines + juridique" },
    { title: "Agent d'exploitation IT", badge: "Démo", desc: "Surveille les logs, classe les alertes, exécute le correctif pour les incidents connus. Ce qu'il ne connaît pas, il vous réveille pour.", lead: "3–6 semaines" },
    { title: "Système multi-agent", badge: "Démo", desc: "Plusieurs agents dans un même processus, avec passations et points de contrôle. Utile seulement si le processus est vraiment complexe.", lead: "10–16 semaines" },
  ],
  process: {
    tag: "Comment nous travaillons",
    heading: "Six étapes, une porte humaine",
    sub: "La plupart des agents sont construits par des agents. Ce qui ne change pas : c'est un humain qui valide — non parce que le modèle est mauvais, mais parce que la responsabilité ne se délègue pas.",
    steps: [
      { n: "01", title: "Cartographie du flux de travail", desc: "Nous regardons où part le temps. Nous ne demandons pas ce que vous voulez automatiser, mais quelle tâche se répète cinquante fois par semaine." },
      { n: "02", title: "Spécification, avec schéma", desc: "L'accord est consigné sous forme lisible par machine : quelle est l'entrée, quelle est la sortie, ce qui compte comme erreur. Ce document servira ensuite de base au test." },
      { n: "03", title: "Construction en environnement isolé", desc: "Chaque projet reçoit son propre environnement d'exécution cloisonné. Une erreur ne peut pas déborder sur le système d'un autre client." },
      { n: "04", title: "Contrôle indépendant", desc: "Le travail terminé n'est pas contrôlé par celui qui l'a écrit. Un contrôleur distinct s'exécute dessus, avec un contexte vide et un accès en lecture seule — il ne peut donc pas défendre ses propres décisions." },
      { n: "05", title: "Validation humaine", desc: "Rien ne sort sans validation. La porte n'est pas une formalité : c'est là qu'on découvre si quelque chose est techniquement correct mais mauvais pour l'entreprise.", amber: "◆ Un humain décide, pas l'IA" },
      { n: "06", title: "Remise et exploitation", desc: "L'agent tourne sur votre infrastructure, avec vos clés. L'abonnement mensuel couvre la supervision et les corrections, pas l'accès." },
    ],
  },
  pricing: {
    tag: "Tarifs",
    heading: "Création et développement de sites web",
    sub: "Des sites modernes, rapides et optimisés pour mobile — avec du vrai contenu, en exploitation réelle.",
    netNote: "prix net, hors hébergement et domaine",
    // A "{p}" helyere a money.js teszi be a kesz arat; a szorend
    // nyelvenkent mas, ezert nem a formazo dolga.
    fromFmt: "à partir de {p}",
    fxNote: "Les prix sont convertis depuis le forint hongrois à un taux approximatif de 1 € ≈ 400 Ft. Le montant exact est fixé dans le devis.",
    popular: "Le plus populaire",
    cta: "Demander un devis",
    subjectPrefix: "Demande de devis",
    packages: [
      { name: "Présence une page", price: "120000", features: ["site d'une page, optimisé mobile", "contact, horaires, Google Maps", "prêt en 3–5 jours"] },
      { name: "Entreprise multipage", price: "290000", features: ["plusieurs sous-pages, galerie, formulaire de contact", "SEO de base et indexation Google", "prêt en 1–2 semaines"] },
      { name: "Sur mesure / avec IA", price: "900000+", features: ["système de réservation ou chat / agent vocal IA", "fonctions sur mesure selon les besoins", "sur devis, avec un délai convenu"] },
    ],
  },
  caseStudy: {
    tag: "En action",
    heading: "Un agent qui appelle, sur une ligne réelle",
    pill: "NOTRE DÉMO",
    para: "Un assistant de restaurant en trois langues qui répond au téléphone, réserve une table et écrit sur le même compteur de places libres que le site. Pas un prototype : il tourne sur un vrai numéro et envoie une vraie confirmation par SMS.",
    bullets: [
      "Parle hongrois, anglais et espagnol, et change en cours d'appel",
      "Téléphone et web partagent le même état de réservation",
      "Interruptible — pas besoin d'écouter jusqu'au bout",
      "Quota d'appels quotidien et limite de durée pour un coût prévisible",
    ],
    link: "Ouvrir le site web →",
    audioCaption: "Un vrai appel avec la réception IA — environ 50 secondes.",
    audioError: "L'audio n'est pas disponible pour le moment.",
    videoBig: "▶ Vidéo — bientôt",
    videoSm: "Capture d'écran de la réservation web, du début à la confirmation.",
    phoneLabel: "Appelez maintenant",
    phoneHint: ["Demandez une table dans n'importe quelle langue.", "Quota quotidien : 20 appels."],
  },
  contact: {
    phoneOrigin: "Numéro américain (Twilio). Les appels de numéros non hongrois sont pris par l'agent IA, en anglais.",
    heading: "Quelle tâche dévore votre semaine ?",
    para: "Écrivez-la en une phrase. Sous deux jours ouvrés, nous vous dirons s'il vaut la peine de créer un agent pour ça — et sinon, aussi.",
    phoneDisabled: "Agent téléphonique — bientôt",
  },
  footer: {
    imprint: "Mentions légales",
    privacy: "Confidentialité",
    left: "AXIMBRA · Budapest · aximbra.hu",
    right: "EPISTEME est notre propre système de démonstration, pas un travail client.",
  },
  marquee: ["DES AGENTS, PAS DES CHATBOTS", "VALIDATION HUMAINE", "BUDAPEST", "HU · EN · ES", "SYSTÈME QUI FONCTIONNE"],
};

export default fr;

/**
 * A /neked oldal betöltés közbeni szövegei, mielőtt az oldal adata (és vele
 * a felület szövegei) megjönne. A nyelvet a böngészőből vesszük.
 */

const T = {
  hu: { loading: "Az oldal betöltése…", slow: "Mindjárt kész, a szerver épp ébred.", goneTitle: "Ez az oldal már nem érhető el", goneText: "A személyre szabott oldalak 90 napig élnek. Írj nekünk, és készítünk újat.", errorText: "Nem sikerült betölteni az oldalt.", retry: "Újra" },
  en: { loading: "Loading your page…", slow: "Almost there, the server is waking up.", goneTitle: "This page is no longer available", goneText: "Personal pages stay up for 90 days. Write to us and we'll make you a new one.", errorText: "The page could not be loaded.", retry: "Try again" },
  de: { loading: "Ihre Seite wird geladen…", slow: "Gleich fertig, der Server wacht gerade auf.", goneTitle: "Diese Seite ist nicht mehr verfügbar", goneText: "Persönliche Seiten bleiben 90 Tage online. Schreiben Sie uns, wir erstellen eine neue.", errorText: "Die Seite konnte nicht geladen werden.", retry: "Erneut versuchen" },
  es: { loading: "Cargando su página…", slow: "Casi listo, el servidor se está despertando.", goneTitle: "Esta página ya no está disponible", goneText: "Las páginas personales duran 90 días. Escríbanos y le preparamos una nueva.", errorText: "No se pudo cargar la página.", retry: "Reintentar" },
  fr: { loading: "Chargement de votre page…", slow: "Presque prêt, le serveur se réveille.", goneTitle: "Cette page n'est plus disponible", goneText: "Les pages personnalisées restent en ligne 90 jours. Écrivez-nous, nous en préparerons une nouvelle.", errorText: "La page n'a pas pu être chargée.", retry: "Réessayer" },
  it: { loading: "Caricamento della pagina…", slow: "Quasi pronto, il server si sta svegliando.", goneTitle: "Questa pagina non è più disponibile", goneText: "Le pagine personalizzate restano online 90 giorni. Scriveteci e ne prepariamo una nuova.", errorText: "Impossibile caricare la pagina.", retry: "Riprova" },
  ro: { loading: "Se încarcă pagina…", slow: "Aproape gata, serverul se trezește.", goneTitle: "Această pagină nu mai este disponibilă", goneText: "Paginile personalizate rămân online 90 de zile. Scrieți-ne și pregătim una nouă.", errorText: "Pagina nu a putut fi încărcată.", retry: "Reîncearcă" },
  sk: { loading: "Načítava sa stránka…", slow: "O chvíľu, server sa práve prebúdza.", goneTitle: "Táto stránka už nie je dostupná", goneText: "Osobné stránky sú online 90 dní. Napíšte nám a pripravíme novú.", errorText: "Stránku sa nepodarilo načítať.", retry: "Skúsiť znova" },
  zh: { loading: "正在加载页面…", slow: "马上就好，服务器正在唤醒。", goneTitle: "此页面已失效", goneText: "个性化页面保留 90 天。给我们写信，我们会为您重新制作。", errorText: "页面加载失败。", retry: "重试" },
};

export const stateText = (lang) => ({ ...T.en, ...(T[(lang || "").slice(0, 2)] || {}) });

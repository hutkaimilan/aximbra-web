/**
 * Végigjárja az oldal minden útvonalát valódi böngészőben, és összeszedi,
 * ami egy felhasználónál hibaként jelentkezik: konzolhiba, elbukott kérés,
 * hiányzó alt, címke nélküli űrlapmező, duplikált id, üres link, túl kicsi
 * érintőfelület mobilon.
 */
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://127.0.0.1:8099';
const EXEC = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const ROUTES = [
  '/', '/demo/etterem', '/demo/szalon', '/demo/rendelo', '/demo/ugyvedi',
  '/demo/email-agent', '/impresszum', '/adatkezeles',
  '/en', '/de', '/es', '/fr', '/it', '/ro', '/sk',
  '/en/demo/etterem', '/en/demo/rendelo', '/nemletezik',
];

const AUDIT = () => {
  const out = [];
  const text = (el) => ((el && el.textContent) || '').replace(/\s+/g, ' ').trim();

  document.querySelectorAll('img').forEach((img) => {
    if (!img.hasAttribute('alt')) out.push(`img alt hiányzik: ${img.getAttribute('src')}`);
    if (img.complete && img.naturalWidth === 0) out.push(`kép nem töltődött be: ${img.currentSrc || img.src}`);
  });

  document.querySelectorAll('form input, form select, form textarea').forEach((f) => {
    if (f.type === 'hidden' || f.type === 'submit') return;
    const id = f.getAttribute('id');
    const labelled = (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) ||
      f.closest('label') || f.getAttribute('aria-label') || f.getAttribute('aria-labelledby');
    if (!labelled) out.push(`címke nélküli mező: <${f.tagName.toLowerCase()} name=${f.getAttribute('name')}>`);
    if (!f.getAttribute('name') && f.type !== 'checkbox') out.push(`name nélküli mező: ${text(f.closest('label')) || f.placeholder}`);
  });

  const ids = new Map();
  document.querySelectorAll('[id]').forEach((el) => {
    ids.set(el.id, (ids.get(el.id) || 0) + 1);
  });
  ids.forEach((n, id) => { if (n > 1) out.push(`duplikált id: #${id} (${n}x)`); });

  document.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href');
    if (href === '#' || href === '') out.push(`üres link: "${text(a).slice(0, 40)}"`);
    if (href.startsWith('#') && href.length > 1 && !document.querySelector(CSS.escape(href).replace('\\#', '#'))) {
      out.push(`horgony nem létező elemre: ${href}`);
    }
    if (a.target === '_blank' && !(a.rel || '').includes('noopener')) out.push(`_blank rel=noopener nélkül: ${href}`);
    if (!text(a) && !a.getAttribute('aria-label') && !a.querySelector('img[alt]:not([alt=""])')) {
      out.push(`névtelen link: ${href}`);
    }
  });

  document.querySelectorAll('button').forEach((b) => {
    if (!text(b) && !b.getAttribute('aria-label')) out.push('névtelen gomb');
  });

  // A nyelvi váltó és a fő hivatkozások érinthető mérete telefonon.
  document.querySelectorAll('a, button, select').forEach((el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'inline' && el.closest('p, li, dd, span')) return;  // folyó szövegben álló link
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && (r.height < 24 || r.width < 24)) {
      out.push(`túl kicsi érintőfelület (${Math.round(r.width)}x${Math.round(r.height)}): ${text(el).slice(0, 30) || el.tagName}`);
    }
  });

  const html = document.documentElement;
  if (!html.getAttribute('lang')) out.push('a <html> elemnek nincs lang attribútuma');
  if (!document.querySelector('h1')) out.push('nincs h1 az oldalon');
  if (document.querySelectorAll('h1').length > 1) out.push(`több h1 (${document.querySelectorAll('h1').length})`);
  if (document.title.length > 65) out.push(`hosszú title (${document.title.length} karakter)`);
  const desc = document.querySelector('meta[name="description"]');
  if (!desc || !desc.content) out.push('nincs meta description');
  else if (desc.content.length > 165) out.push(`hosszú description (${desc.content.length})`);

  // Vízszintes túlcsordulás: ez a "mobilon szétesik" leggyakoribb oka.
  if (document.documentElement.scrollWidth > window.innerWidth + 1) {
    let worst = null;
    document.querySelectorAll('*').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.right > window.innerWidth + 1 && (!worst || r.right > worst.right)) {
        worst = { right: r.right, sel: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '') };
      }
    });
    out.push(`vízszintes túlcsordulás: ${document.documentElement.scrollWidth}px > ${window.innerWidth}px${worst ? ` — legszélső: ${worst.sel} (${Math.round(worst.right)}px)` : ''}`);
  }
  return out;
};

(async () => {
  const browser = await chromium.launch({ executablePath: EXEC, args: ['--no-sandbox'] });
  const findings = [];
  for (const viewport of [{ width: 1280, height: 900, label: 'asztali' }, { width: 390, height: 844, label: 'mobil' }]) {
    const ctx = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
    await ctx.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
    for (const route of ROUTES) {
      if (viewport.label === 'mobil' && route.length > 4 && !['/', '/demo/etterem', '/demo/email-agent', '/adatkezeles', '/impresszum'].includes(route)) continue;
      const page = await ctx.newPage();
      const errs = [];
      page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push(`konzol: ${m.text().slice(0, 200)}`); });
      page.on('pageerror', (e) => errs.push(`kivétel: ${String(e).slice(0, 200)}`));
      const EXTERNAL = (u) => /fonts\.(googleapis|gstatic)\.com|google-analytics|googletagmanager/.test(u);
      page.on('requestfailed', (r) => !EXTERNAL(r.url()) && errs.push(`kérés elbukott: ${r.url().slice(0, 120)} (${r.failure()?.errorText})`));
      page.on('response', (r) => { if (r.status() >= 400 && !EXTERNAL(r.url())) errs.push(`HTTP ${r.status()}: ${r.url().slice(0, 120)}`); });
      try {
        await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 20000 });
        await page.waitForTimeout(2500);
        const audit = await page.evaluate(AUDIT);
        const all = [...errs, ...audit];
        if (all.length) findings.push({ route, viewport: viewport.label, issues: all });
      } catch (e) {
        findings.push({ route, viewport: viewport.label, issues: [`betöltés sikertelen: ${String(e).slice(0, 150)}`] });
      }
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();

  let n = 0;
  for (const f of findings) {
    console.log(`\n=== ${f.route}  [${f.viewport}] ===`);
    const seen = new Set();
    for (const i of f.issues) {
      if (seen.has(i)) continue;
      seen.add(i); n++;
      console.log('  - ' + i);
    }
  }
  console.log(`\nÖSSZESEN ${n} egyedi észrevétel ${findings.length} oldal-nézetben.`);
})();

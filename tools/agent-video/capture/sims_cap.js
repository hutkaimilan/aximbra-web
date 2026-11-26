// Minden szimulacios agent kartyajarol allapotkepek + elemkeretek (CSS px, a kivagas origojahoz kepest).
const { chromium } = require('playwright');
const fs = require('fs');
const SLUGS = ["email-rendezo","erdeklodo-minosito","belso-admin","kutatasi-monitor","ugyfelszolgalat","tartalom","webshop","dokumentum-elemzo","penzugyi","toborzas","it-uzemelteto","multi-agent","nis2","ertekesito","egyedi"];
const WHICH = (process.argv[2]||"2,3,4,5,8,9,10,11,12,13").split(",").map(Number);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport:{width:540,height:1170}, deviceScaleFactor:2, isMobile:true, hasTouch:true,
    userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    colorScheme:'dark' });
  const all = fs.existsSync('sims.json') ? JSON.parse(fs.readFileSync('sims.json')) : {};
  for (const k of WHICH) {
    const slug = SLUGS[k];
    const p = await ctx.newPage();
    await p.goto(`https://aximbra.hu/agent/${slug}`, {waitUntil:'networkidle', timeout:90000});
    await p.waitForTimeout(2500);
    const hideFixed = () => p.evaluate(() => {
      for (const e of document.querySelectorAll('body *')) {
        const cs = getComputedStyle(e);
        if ((cs.position === 'fixed' || cs.position === 'sticky') && !e.closest('.card')) e.style.visibility = 'hidden';
      }
    });
    await hideFixed();
    const cardSel = `#agent-${slug}`;
    const origin = await p.evaluate(s => { const r = document.querySelector(s).getBoundingClientRect(); return {x:0, y:Math.round(r.y + scrollY) - 30}; }, cardSel);
    const rects = (spec) => p.evaluate(({spec, cardSel, oy}) => {
      const card = document.querySelector(cardSel); const o = {};
      const R = e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y + scrollY - oy), Math.round(r.right), Math.round(r.bottom + scrollY - oy)]; };
      for (const [name, sel] of Object.entries(spec)) {
        const els = [...card.querySelectorAll(sel)];
        if (els.length === 1) o[name] = R(els[0]); else if (els.length > 1) o[name] = els.map(R);
      }
      const cr = card.getBoundingClientRect(); o.card = R(card); o.h = Math.round(cr.bottom + scrollY - oy) + 30;
      return o; }, {spec, cardSel, oy: origin.y});
    const texts = (sel) => p.evaluate(({sel, cardSel}) => [...document.querySelector(cardSel).querySelectorAll(sel)].map(e => e.innerText.trim()), {sel, cardSel});
    const shot = async (name) => { const r = await rects({}); await p.waitForTimeout(150);
      await p.screenshot({path:`s${k}_${name}.png`, fullPage:true, clip:{x:0, y:origin.y, width:540, height:r.h}}); };
    const SPEC = {title:'.card-title', badge:'.badge', desc:'.card-desc', meta:'.card-meta', note:'[data-testid="sim-sample-note"]',
      head:'.sim-head', grid:'.sim-grid', chips:'.sim-chip', start:'[data-testid="sim-start"]', skip:'[data-testid="sim-skip"]',
      afterHead:'.sim-after-head', bar:'[data-testid="sim-bar"]', approveBox:'.sim-approve', approve:'[data-testid="sim-approve"]',
      rewrite:'[data-testid="sim-rewrite"]', apprMsg:'.sim-appr-msg', picks:'.sim-pick', audit:'[data-testid="sim-audit"]',
      auditLines:'.sim-audit-l', closing:'[data-testid="sim-closing"]', again:'[data-testid="sim-again"]'};
    const info = {slug, origin, states:{}};
    // I: kartya + szimulacio, inditas elott
    await p.evaluate(s => window.scrollTo(0, document.querySelector(s).getBoundingClientRect().y + scrollY - 40), cardSel);
    await p.waitForTimeout(600); await hideFixed();
    info.states.I = await rects(SPEC); await shot('I');
    info.text = { title: (await texts('.card-title'))[0], desc: (await texts('.card-desc'))[0], meta: (await texts('.card-meta'))[0],
      head: (await texts('.sim-head'))[0], chips: await texts('.sim-chip'), start: (await texts('[data-testid="sim-start"]'))[0] };
    const n = info.text.chips.length;
    const stepMs = Math.max(280, Math.floor(6500 / n));
    // R: futas kozben, kb. a felenel
    await p.locator('[data-testid="sim-start"]').click();
    info.runStepMs = stepMs; info.runItems = n; info.runFrames = [];
    // futas kozben minden lepesnel egy kep: a csempek egyenkent gyulladnak ki
    for (let i = 1; i <= n; i++) {
      try {
        await p.waitForFunction(({cardSel, i}) => document.querySelector(cardSel).querySelectorAll('.sim-chip:not(.sim-pending)').length >= i
          || !!document.querySelector(cardSel).querySelector('[data-testid="sim-after"]'), {cardSel, i}, {timeout: 8000, polling: 40});
      } catch (e) { break; }
      if (await p.locator(cardSel + ' [data-testid="sim-after"]').count()) break;
      const got = await p.evaluate(s => document.querySelector(s).querySelectorAll('.sim-chip:not(.sim-pending)').length, cardSel);
      if (info.runFrames.includes(got)) continue;
      await p.screenshot({path:`s${k}_R${got}.png`, fullPage:true, clip:{x:0, y:origin.y, width:540, height:info.states.I.h + 2}});
      info.runFrames.push(got);
      if (got === Math.ceil(n / 2)) info.states.R = await rects(SPEC);
    }
    if (!info.states.R) info.states.R = await rects(SPEC);
    // D: kesz
    await p.waitForSelector('[data-testid="sim-after"]', {timeout:30000});
    await p.waitForTimeout(900); await hideFixed();
    info.states.D = await rects(SPEC); await shot('D');
    info.text.afterHead = (await texts('.sim-after-head'))[0];
    info.text.bar = (await texts('[data-testid="sim-bar"]'))[0] || null;
    info.text.picks = await texts('.sim-pick');
    info.text.audit = await texts('.sim-audit-l');
    info.text.closing = (await texts('[data-testid="sim-closing"]'))[0];
    // P: jovahagyva
    if (await p.locator('[data-testid="sim-approve"]').count()) {
      await p.locator('[data-testid="sim-approve"]').click(); await p.waitForTimeout(700); await hideFixed();
      info.states.P = await rects(SPEC); await shot('P');
      info.text.apprMsg = (await texts('.sim-appr-msg'))[0];
    }
    all[k] = info;
    console.log(k, slug, JSON.stringify(info.text).slice(0, 300));
    await p.close();
  }
  fs.writeFileSync('sims.json', JSON.stringify(all, null, 1));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });

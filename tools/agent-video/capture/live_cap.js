// Az elo demok allapotkepei: erdeklodo-minosito (1), webshop (6), dokumentum-elemzo (7).
const { chromium } = require('playwright');
const fs = require('fs');
const WHICH = (process.argv[2] || "1,6,7").split(",").map(Number);
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport:{width:540,height:1170}, deviceScaleFactor:2, isMobile:true, hasTouch:true,
    userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    colorScheme:'dark' });
  const all = fs.existsSync('live.json') ? JSON.parse(fs.readFileSync('live.json')) : {};

  const mk = async (url, rootSel) => {
    const p = await ctx.newPage();
    await p.goto(url, {waitUntil:'networkidle', timeout:90000});
    await p.waitForTimeout(2500);
    const hideFixed = () => p.evaluate(() => {
      for (const e of document.querySelectorAll('body *')) {
        const cs = getComputedStyle(e);
        if (cs.position === 'fixed' || cs.position === 'sticky') e.style.visibility = 'hidden';
      } });
    await p.evaluate(s => window.scrollTo(0, document.querySelector(s).getBoundingClientRect().y + scrollY - 40), rootSel);
    await p.waitForTimeout(900); await hideFixed();
    const oy = await p.evaluate(s => Math.round(document.querySelector(s).getBoundingClientRect().y + scrollY) - 30, rootSel);
    const rects = (spec) => p.evaluate(({spec, rootSel, oy}) => {
      const root = document.querySelector(rootSel); const o = {};
      const R = e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y + scrollY - oy), Math.round(r.right), Math.round(r.bottom + scrollY - oy)]; };
      for (const [name, sel] of Object.entries(spec)) {
        const els = [...root.querySelectorAll(sel)].filter(e => e.getBoundingClientRect().height > 0);
        if (els.length === 1) o[name] = R(els[0]); else if (els.length > 1) o[name] = els.map(R);
      }
      const cr = root.getBoundingClientRect(); o.root = R(root); o.h = Math.round(cr.bottom + scrollY - oy) + 30;
      return o; }, {spec, rootSel, oy});
    const texts = (sel) => p.evaluate(({sel, rootSel}) => [...document.querySelector(rootSel).querySelectorAll(sel)].map(e => e.innerText.trim()), {sel, rootSel});
    const shot = async (file, spec, maxH) => { await hideFixed(); await p.waitForTimeout(250); const r = await rects(spec);
      await p.screenshot({path:file, fullPage:true, clip:{x:0, y:oy, width:540, height:Math.min(r.h, maxH || 99999)}}); return r; };
    return {p, rects, texts, shot, hideFixed};
  };

  if (WHICH.includes(1)) {
    const slug = 'erdeklodo-minosito', root = `#agent-${slug}`;
    const {p, texts, shot} = await mk(`https://aximbra.hu/agent/${slug}?demo=1`, root);
    const SPEC = {title:'.card-title', badge:'.badge', desc:'.card-desc', meta:'.card-meta', input:'[data-testid="demo-input-lead"]',
      samples:'.sample-btn', run:'[data-testid="demo-run-lead"]', result:'[data-testid="demo-result-lead"]', fields:'.result-field', error:'.demo-error'};
    const info = {slug, states:{}, runs:[]};
    info.states.I = await shot('l1_I.png', SPEC);
    for (const [si, tag] of [[0, 'A'], [1, 'B']]) {
      await p.locator(`[data-testid="demo-sample-lead-${si}"]`).click(); await p.waitForTimeout(500);
      info.states['S' + tag] = await shot(`l1_S${tag}.png`, SPEC);
      await p.locator('[data-testid="demo-run-lead"]').click(); log('lead run', si);
      await p.waitForTimeout(700); info.states['W' + tag] = await shot(`l1_W${tag}.png`, SPEC);
      await p.waitForSelector('[data-testid="demo-result-lead"], [data-testid="demo-error-lead"]', {timeout:240000});
      await p.waitForTimeout(1200);
      info.states['R' + tag] = await shot(`l1_R${tag}.png`, SPEC);
      info.runs.push({sample: si, input: await p.locator('[data-testid="demo-input-lead"]').inputValue(),
        fields: await texts('.result-field'), error: await texts('.demo-error')});
      log('lead result', JSON.stringify(info.runs.at(-1).fields).slice(0, 400));
    }
    all[1] = info; await p.close();
  }

  if (WHICH.includes(7)) {
    const slug = 'dokumentum-elemzo', root = `#agent-${slug}`;
    const {p, texts, shot} = await mk(`https://aximbra.hu/agent/${slug}?demo=1`, root);
    const SPEC = {title:'.card-title', badge:'.badge', desc:'.card-desc', meta:'.card-meta', intro:'.doc-intro', privacy:'.doc-privacy',
      upload:'[data-testid="doc-upload"]', samples:'.sample-btn', run:'[data-testid="doc-run"]', result:'[data-testid="doc-result"]',
      fields:'.result-field', keys:'.result-field > .k', srcs:'.doc-src', risks:'.doc-risk', sev:'.doc-sev', missing:'.doc-missing', copy:'[data-testid="doc-copy"]'};
    const info = {slug, states:{}, runs:[]};
    info.states.I = await shot('l7_I.png', SPEC);
    await p.locator('[data-testid="doc-sample-contract_hu"]').click(); await p.waitForTimeout(400);
    // A modellszolgaltato tulterheltsegenel a mezos kor elbukhat; olyankor a mezok
    // "nem talalhato"-t irnak. Ilyen eredmenyt nem rogzitunk: ujrafuttatjuk.
    for (let attempt = 1; attempt <= 5; attempt++) {
      await p.locator('[data-testid="doc-run"]').click(); log('doc run', attempt);
      await p.waitForTimeout(800); info.states.W = await shot('l7_W.png', SPEC);
      await p.waitForSelector('[data-testid="doc-result"], [data-testid="doc-error"]', {timeout:240000});
      await p.waitForTimeout(1500);
      const missing = await p.locator('[data-testid="doc-result"] .doc-missing').count();
      log('missing fields', missing);
      if (missing <= 1 && await p.locator('[data-testid="doc-result"]').count()) break;
      await p.waitForTimeout(20000);
    }
    info.states.R = await shot('l7_R.png', SPEC);
    info.runs.push({fields: await texts('.result-field'), error: await texts('[data-testid="doc-error"]')});
    log('doc result', JSON.stringify(info.runs[0]).slice(0, 600));
    all[7] = info; await p.close();
  }

  if (WHICH.includes(6)) {
    const root = '#ugyfelszolgalat';
    const {p, texts, shot} = await mk('https://aximbra.hu/demo/webshop#ugyfelszolgalat', root);
    const SPEC = {tag:'.shop-tag', h2:'.shop-h2', lead:'.shop-lead', step1:'.shop-live-f label', chips:'.shop-chip', inputs:'input', textarea:'textarea',
      send:'button[type="submit"].shop-btn:not(.sm)', hint:'.shop-note', out:'.shop-live-out', tags:'.shop-live-tags span', draftH:'.shop-live-h', pre:'.shop-live-out pre', err:'.shop-track-no'};
    const info = {slug:'webshop', states:{}, runs:[]};
    info.states.I = await shot('l6_I.png', SPEC);
    for (const [ci, tag] of [[0, 'A'], [1, 'B']]) {
      await p.locator('#ugyfelszolgalat .shop-chip').nth(ci).click(); await p.waitForTimeout(500);
      info.states['S' + tag] = await shot(`l6_S${tag}.png`, SPEC);
      await p.locator('#ugyfelszolgalat .shop-live button[type="submit"].shop-btn:not(.sm)').click(); log('shop send', ci);
      await p.waitForTimeout(700); info.states['W' + tag] = await shot(`l6_W${tag}.png`, SPEC);
      await p.waitForSelector('.shop-live-out, .shop-track-no', {timeout:240000});
      await p.waitForTimeout(1200);
      info.states['R' + tag] = await shot(`l6_R${tag}.png`, SPEC);
      info.runs.push({chip: ci, from: await p.locator(`${root} input`).nth(1).inputValue().catch(() => ''),
        tags: await texts('.shop-live-tags span'), body: await texts('.shop-live-out pre'), err: await texts('.shop-track-no')});
      log('shop result', JSON.stringify(info.runs.at(-1)).slice(0, 500));
    }
    all[6] = info; await p.close();
  }
  fs.writeFileSync('live.json', JSON.stringify(all, null, 1));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });

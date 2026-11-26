const { chromium } = require('playwright');
const fs = require('fs');
const log=(...a)=>console.log(new Date().toISOString().slice(14,19),...a);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport:{width:540,height:1170}, deviceScaleFactor:2, isMobile:true, hasTouch:true,
    userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    colorScheme:'dark' });
  const p = await ctx.newPage();
  const box = async (sel) => p.evaluate(s=>{const e=document.querySelector(s); if(!e) return null;
    const r=e.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y+window.scrollY),w:Math.round(r.width),h:Math.round(r.height)};}, sel);
  const byText = async (t) => p.evaluate(tx=>{const e=[...document.querySelectorAll('div,section,p,pre')].find(x=>x.textContent.trim().startsWith(tx)&&x.getBoundingClientRect().height<900);
    if(!e) return null; const r=e.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y+window.scrollY),w:Math.round(r.width),h:Math.round(r.height)};}, t);
  const out = {};

  await p.goto('https://aximbra.hu/demo/email-agent',{waitUntil:'networkidle',timeout:90000});
  await p.waitForTimeout(2200);
  await p.locator('[data-testid="agent-sample"]').click(); log('sample');
  await p.waitForSelector('[data-testid="agent-tile-needs-reply"]',{state:'attached',timeout:120000});
  await p.waitForTimeout(5000); log('eredmeny');
  await p.evaluate(()=>window.scrollTo(0,0)); await p.waitForTimeout(500);
  await p.screenshot({path:'st_A.png', fullPage:true});
  out.A = { h: await p.evaluate(()=>document.documentElement.scrollHeight),
    processed: await byText('FELDOLGOZOTT') || await byText('Feldolgozott'),
    needs: await box('[data-testid="agent-tile-needs-reply"]'),
    junk: await box('[data-testid="agent-tile-junk"]'),
    urgent: await byText('LEGSÜRGŐSEBB') || await byText('Legsürgősebb'),
    cats: await byText('KATEGÓRIA') || await byText('Kategória') };

  // az elso "Valasz szukseges" levelet nyitjuk ki
  const rowSel = await p.evaluate(()=>{
    const rows=[...document.querySelectorAll('.agent-row')];
    const i=rows.findIndex(r=>r.className.includes('needs'));
    return i<0?null:i; });
  log('sor index', rowSel);
  const rows = p.locator('.agent-row');
  const head = rows.nth(rowSel ?? 0).locator('.agent-row-head');
  out.A.row = await p.evaluate(i=>{const r=[...document.querySelectorAll('.agent-row')][i].getBoundingClientRect();
    return {x:Math.round(r.x),y:Math.round(r.y+window.scrollY),w:Math.round(r.width),h:Math.round(r.height)};}, rowSel ?? 0);
  await head.click(); await p.waitForTimeout(1200); log('kinyitva');
  await p.evaluate(()=>window.scrollTo(0,0)); await p.waitForTimeout(400);
  await p.screenshot({path:'st_B.png', fullPage:true});
  out.B = { h: await p.evaluate(()=>document.documentElement.scrollHeight),
    body: await box('.agent-row-body'),
    why: await byText('Miért ez a sürgősség'),
    next: await byText('Javasolt következő lépés'),
    mail: await byText('A levél'),
    draftBtn: await box('[data-testid^="agent-draft-go-"]'),
    tones: await box('.agent-draft-tones') };

  // valasz iratasa
  const go = p.locator('[data-testid^="agent-draft-go-"]').first();
  await go.click(); log('valasz keszul');
  await p.waitForTimeout(1100);
  await p.evaluate(()=>window.scrollTo(0,0)); await p.waitForTimeout(300);
  await p.screenshot({path:'st_W.png', fullPage:true});
  await p.waitForSelector('[data-testid^="agent-draft-text-"]',{state:'attached',timeout:120000});
  await p.waitForTimeout(2500); log('valasz kesz');
  await p.evaluate(()=>window.scrollTo(0,0)); await p.waitForTimeout(400);
  await p.screenshot({path:'st_C.png', fullPage:true});
  out.C = { h: await p.evaluate(()=>document.documentElement.scrollHeight),
    out_: await box('.agent-draft-out'),
    subj: await box('.agent-draft-subj'),
    text: await box('[data-testid^="agent-draft-text-"]'),
    foot: await box('.agent-draft-foot'),
    note: await box('.agent-draft-note'),
    draftText: await p.evaluate(()=>{const t=document.querySelector('[data-testid^="agent-draft-text-"]'); return t?t.value.slice(0,600):null;}),
    subject: await p.evaluate(()=>{const t=document.querySelector('.agent-draft-subj'); return t?t.innerText:null;}) };
  fs.writeFileSync('states.json', JSON.stringify(out,null,1));
  log('kesz'); await b.close();
})().catch(e=>{console.error('ERR',e.message);process.exit(1);});

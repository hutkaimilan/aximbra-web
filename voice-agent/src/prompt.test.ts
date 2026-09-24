import { test } from 'node:test';
import assert from 'node:assert/strict';

import { buildFactsBlock, buildSystemPrompt } from './prompt.js';
import { emptyFacts, mergeFacts, looksLikeEmail, type CallFacts } from './llm.js';

function facts(over: Partial<CallFacts> = {}): CallFacts {
  return { ...emptyFacts(), ...over };
}

const turns = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
    content: i % 2 === 0 ? 'kerdes' : 'valasz',
  }));

test('nehany fordulo utan ott all, hogy a nev es a ceg hianyzik', () => {
  // Eles hivas, 2026-09-23: az agent vegigvitt egy teljes erdeklodest,
  // ajanlatot igert, es a hivas vegen nem tudtuk, ki hivott. A szabaly
  // ott volt a promptban, csak husz fordulo utan elhalvanyult.
  const block = buildFactsBlock(facts(), '+36301300242', turns(6));
  assert.match(block, /AMI MÉG HIÁNYZIK/);
  assert.match(block, /NEVE/);
  assert.match(block, /CÉG/);

  // A hianylista a prompt ELEJEN all, az "amit mar tudsz" elott.
  assert.ok(
    block.indexOf('AMI MÉG HIÁNYZIK') < block.indexOf('AMIT MÁR TUDSZ'),
    'a hianyzo adatok elol alljanak',
  );
});

test('ha mindketto megvan, a hianylista eltunik', () => {
  const block = buildFactsBlock(facts({ nev: 'Kovács Péter', ceg: 'Pelda Kft.' }), '', turns(6));
  assert.doesNotMatch(block, /AMI MÉG HIÁNYZIK/);
});

test('kulon jelzi, ha csak az egyik hianyzik', () => {
  const csakNev = buildFactsBlock(facts({ nev: 'Kovács Péter' }), '', turns(6));
  assert.match(csakNev, /AMI MÉG HIÁNYZIK/);
  assert.match(csakNev, /CÉG/);
  assert.doesNotMatch(csakNev, /a hívó NEVE/);

  const csakCeg = buildFactsBlock(facts({ ceg: 'Pelda Kft.' }), '', turns(6));
  assert.match(csakCeg, /a hívó NEVE/);
});

test('a hivasbol ismert szamot nem kell elkerni', () => {
  // Visszahivasnal a szamot a telefonhalozattol kapjuk. Elkerni azt, amit
  // mar tudunk, ugy hangzik, mintha nem figyeltunk volna.
  const block = buildFactsBlock(facts(), '+36301300242');
  assert.match(block, /\+36301300242/);
  assert.match(block, /nem ő mondta/);
});

test('ismeretlen hivoszambol nem lesz kitalalt adat', () => {
  const block = buildFactsBlock(facts(), '<ismeretlen>');
  assert.doesNotMatch(block, /Telefonszám \(a hívásból/);
});

test('a rendszerprompt kimondja, hogy nev nelkul nem igerunk ajanlatot', () => {
  const prompt = buildSystemPrompt(0, facts(), '+36301300242');
  assert.match(prompt, /NE ÍGÉRJ SEMMIT NÉV ÉS CÉG NÉLKÜL/);
  // ...es azt is, hogy a mar ismert szamot ne kerje el ujra.
  assert.match(prompt, /HA A TELEFONSZÁM MÁR MEGVAN/);
});

test('a sajat e-mail cimunket nem ajanlhatja fel a hivo cimekent', () => {
  // Teszthivas, 2026-09-24: az agent ketszer is felajanlotta, hogy az
  // ajanlatot az "aximbra kukac gmail pont com" cimre kuldi - a sajat
  // cimunkre -, es a hivonak kellett kijavitania.
  const prompt = buildSystemPrompt(0, facts(), '+36301300242');
  assert.match(prompt, /AZ AXIMBRA CÍME A MIÉNK, NEM A HÍVÓÉ/);
  assert.match(prompt, /NE ERŐSÍTS MEG OLYAN E-MAIL CÍMET/);
});

test('a kiejtesi pelda nem a sajat cimunk', () => {
  // Korabban a formazasi szabaly peldaja maga az AXIMBRA cime volt, es a
  // modell ezt hasznalta "a" cimkent, amikor cimet kellett mondania.
  const prompt = buildSystemPrompt(0, facts(), '');
  const rule = prompt.slice(prompt.indexOf('E-mail címet betűzve'));
  const firstLine = rule.slice(0, rule.indexOf('\n'));
  assert.doesNotMatch(firstLine, /aximbra/i, 'a pelda ne a sajat cimunk legyen');
});

test('a felismeres altal osszetort cim nem valik ismert tennye', () => {
  // Eles teszthivas: a hivo cime "kovacsopka kukac hu"-kent erkezett, es az
  // agent magabiztosan vissza is olvasta. Pont nelkuli domain nem letezhet.
  assert.equal(looksLikeEmail('kovacsopka@hu'), false);
  assert.equal(looksLikeEmail('kovacsopka kukac hu'), false);
  assert.equal(looksLikeEmail('@kovacsoptika.hu'), false);
  assert.equal(looksLikeEmail('petr@@kovacsoptika.hu'), false);
  assert.equal(looksLikeEmail('kovacs.peter@kovacsoptika.hu'), true);
  assert.equal(looksLikeEmail('sarah@bennett-design.co.uk'), true);

  // ...es a hibas cim tenyleg nem kerul be a tenyek koze.
  const merged = mergeFacts(facts(), { email: 'kovacsopka@hu', nev: 'Kovács Péter' });
  assert.equal(merged.email, null, 'a hasznalhatatlan cim nem lehet "mar tudjuk"');
  assert.equal(merged.nev, 'Kovács Péter', 'a tobbi adat viszont bekerul');

  const good = mergeFacts(facts(), { email: 'kovacs.peter@kovacsoptika.hu' });
  assert.equal(good.email, 'kovacs.peter@kovacsoptika.hu');
});

test('ha a szam megvan es ervenyes cim nincs, az SMS-utat ajanlja', () => {
  const block = buildFactsBlock(facts({ nev: 'K P', ceg: 'K Kft.' }), '+36301300242', turns(6));
  assert.match(block, /HA KÜLDENED KELL VALAMIT/);
  assert.match(block, /SMS/);
});

test('ervenyes cim mellett nem eroltetjuk az SMS-t', () => {
  const block = buildFactsBlock(
    facts({ nev: 'K P', ceg: 'K Kft.', email: 'k@pelda.hu' }),
    '+36301300242',
    turns(6),
  );
  assert.doesNotMatch(block, /HA KÜLDENED KELL VALAMIT/);
});

test('szam nelkul nincs mit SMS-ben kuldeni', () => {
  const block = buildFactsBlock(facts({ nev: 'K P', ceg: 'K Kft.' }), '<ismeretlen>', turns(6));
  assert.doesNotMatch(block, /HA KÜLDENED KELL VALAMIT/);
});

test('minden arnak van kimondott alakja, hogy ne kelljen atvaltania', () => {
  // Eles teszthivas, 2026-09-24: az arlista csak szamjeggyel allt, egy masik
  // szabaly meg azt mondta, betuvel kell kimondani. A modellnek menet kozben
  // kellett atvaltania, es a "szazotvenezer"-bol "szaztizenotezer" lett - egy
  // ar, ami sehol nem letezik. Azota mindket alak ott all: a szam a
  // gondolkodashoz, az idezojeles alak a kimondashoz.
  const prompt = buildSystemPrompt(0, facts(), '');
  const prices = prompt.slice(
    prompt.indexOf('## Árak és határidők'),
    prompt.indexOf('## Elérhetőség'),
  );
  assert.match(prices, /"százötvenezer és négyszázezer forint között"/);
  assert.match(prices, /"hatmillió és tizenötmillió forint között"/);
  assert.match(prices, /"kétszázkilencvenezer forint"/);
  assert.match(prices, /Számjegyet SOHA ne olvass fel/);
});

test('a telefonszamot nem olvassa vissza szamjegyenkent', () => {
  const prompt = buildSystemPrompt(0, facts(), '+36301300242');
  assert.match(prompt, /SOHA NE OLVASD VISSZA SZÁMJEGYENKÉNT/);
});

/* ------------------------------------------------------------------ */
/* A prompt sajat helyessege                                           */
/* ------------------------------------------------------------------ */

test('a szabalyok szamozasa folytonos', () => {
  // Ket kulonbozo szabaly futott "9."-kent, es a rajuk valo hivatkozas
  // igy ketertelmu volt.
  const prompt = buildSystemPrompt(0, facts(), '');
  const block = prompt.slice(
    prompt.indexOf('# AMIT SOHA NE CSINÁLJ'),
    prompt.indexOf('# A BESZÉLGETÉS MENETE'),
  );
  const numbers = [...block.matchAll(/^(\d+)\. /gm)].map((m) => Number(m[1]));
  assert.ok(numbers.length >= 15, 'legyen meg minden szabaly');
  numbers.forEach((n, i) => {
    assert.equal(n, i + 1, `a ${i + 1}. helyen "${n}." all - elcsuszott a szamozas`);
  });
});

test('nem igerunk olyan nyelvet, amit a vonal nem tud', () => {
  // A relay csak hu-HU es en-US <Language> elemet kap (server.ts ALL_LANGS).
  // A spanyolra valtas ervenytelen nyelvre mutatna es BONTANA a hivast -
  // a prompt megis ezt igerte, es az ugyfelnek is ezt mondta volna.
  const prompt = buildSystemPrompt(0, facts(), '');
  assert.doesNotMatch(prompt, /spanyol/i, 'a spanyol nyelv nincs bekotve');
});

test('az angol hivas sem a sajat cimunket adja a hivonak', () => {
  // Ugyanaz a hiba, mint a 16. szabalyban - csak az angol blokkban, ahol
  // kifejezetten utasitas volt ra.
  const en = buildSystemPrompt(0, facts(), '', 'en');
  const enBlock = en.slice(0, en.indexOf('# HOGYAN BESZÉLSZ'));
  assert.doesNotMatch(
    enBlock,
    /aximbra at gmail dot com/i,
    'ne a sajat cimunket mondassuk ki cimkent',
  );
});

test('az angol hivasnak is van kimondhato arlistaja', () => {
  // A magyar arlista kimondott magyar alakra allt at; anelkul egy angol
  // hivason nem lenne mibol arat mondani.
  const en = buildSystemPrompt(0, facts(), '', 'en');
  assert.match(en, /between one hundred fifty thousand and four hundred thousand forints/);
  assert.match(en, /between six and fifteen million forints/);
  assert.match(en, /two to four weeks/);
});

test('a prompt nem tartalmaz nem letezo arat peldakent', () => {
  // A javitas indoklasa maga is bekerult a promptba, benne azzal a hibas
  // arral, amit kerulni akartunk. A modell minden fordulonal elolvassa.
  const prompt = buildSystemPrompt(0, facts(), '');
  assert.doesNotMatch(prompt, /sztizenotezer|száztizenötezer/i);
});

/* ------------------------------------------------------------------ */
/* A nevkerdes idozitese                                               */
/* ------------------------------------------------------------------ */

test('az elso fordulokban nem surgeti a nevet', () => {
  // Eles hivas, 2026-09-24, 20:10: az agent a hivo LEGELSO mondataba vagott
  // bele ("Azt szeretnem megkerdezni, hogy az oldalon lathato...") azzal,
  // hogy "Elnezest, meg tudna mondani, kihez cimezzem". 55 masodperc, D
  // minosites, es a nev igy sem hangzott el - a hivo letette.
  // turns(1) = egy hivoi mondat, turns(2) = hivo + agent: itt meg csendben marad.
  assert.doesNotMatch(buildFactsBlock(facts(), '', turns(1)), /AMI MÉG HIÁNYZIK/);
  assert.doesNotMatch(buildFactsBlock(facts(), '', turns(2)), /AMI MÉG HIÁNYZIK/);
  // turns(3)-tol a hivo mar masodszor beszelt: innentol helyenvalo.
  assert.match(buildFactsBlock(facts(), '', turns(3)), /AMI MÉG HIÁNYZIK/);
});

test('nem kerdezi meg ketszer egymas utan', () => {
  // Ugyanabban az 55 masodperces hivasban ketszer hangzott el.
  const asked = [
    ...turns(4),
    { role: 'assistant' as const, content: 'Rendben. Kihez címezzem, és melyik cégnél?' },
    { role: 'user' as const, content: 'es mennyibe kerul?' },
  ];
  assert.doesNotMatch(buildFactsBlock(facts(), '', asked), /AMI MÉG HIÁNYZIK/);
});

test('ket fordulo utan ujra felhozhatja', () => {
  const asked = [
    { role: 'assistant' as const, content: 'Kihez címezzem, és melyik cégnél?' },
    ...turns(6),
  ];
  assert.match(buildFactsBlock(facts(), '', asked), /AMI MÉG HIÁNYZIK/);
});

/* ------------------------------------------------------------------ */
/* Arak: osszehasonlithatosag                                          */
/* ------------------------------------------------------------------ */

test('a legdragabb agent a tobb-agentes rendszer', () => {
  // Eles hivas, 2026-09-24, 20:10: a kerdesre ("a legdragabb agent milyen
  // arkategoriaban mozog?") az agent az ugyfelszolgalati agentet mondta
  // (masfel-negymillio) a tobb-agentes rendszer helyett (hat-tizenotmillio).
  // Az ok: az arlistabol kivettem minden szamjegyet, es ezzel elvettem azt
  // is, amivel a modell sorba tudta volna rendezni oket.
  const prompt = buildSystemPrompt(0, facts(), '');
  assert.match(prompt, /A LEGDRÁGÁBB a több-agentes rendszer/);
  assert.match(prompt, /nem az ügyfélszolgálati agent/);
  // A szam is ott van a gondolkodashoz, a kimondott alak az idezethez.
  assert.match(prompt, /6 000 000–15 000 000 Ft/);
  assert.match(prompt, /"hatmillió és tizenötmillió forint között"/);
});

test('minden ar-sorhoz tartozik kimondott alak', () => {
  const prompt = buildSystemPrompt(0, facts(), '');
  const block = prompt.slice(
    prompt.indexOf('Olcsótól a legdrágábbig'),
    prompt.indexOf('## Weboldal-készítés'),
  );
  const rows = block.split('\n').filter((l) => /^\d+\. /.test(l));
  assert.equal(rows.length, 13, 'mind a tizenharom agent legyen bent');
  for (const row of rows) {
    assert.match(row, /Ft — "/, `hianyzik a kimondott alak: ${row.slice(0, 40)}`);
  }
});

test('a NIS2-agent nem vedelemkent van leirva', () => {
  // Biztonsagi terméknel a tulvallalas kartéritési per: nem vedunk, bizonyitunk.
  const hu = buildSystemPrompt(0, facts(), '');
  assert.match(hu, /NIS2-megfelelési agent — 600 000–2 000 000 Ft/);
  assert.match(hu, /NEM véd a támadások ellen/);

  const en = buildSystemPrompt(0, facts(), '', 'en');
  assert.match(en, /NIS2 compliance agent/);
  assert.match(en, /does NOT protect against attacks/);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { buildFactsBlock, buildSystemPrompt } from './prompt.js';
import { emptyFacts, mergeFacts, looksLikeEmail, type CallFacts } from './llm.js';

function facts(over: Partial<CallFacts> = {}): CallFacts {
  return { ...emptyFacts(), ...over };
}

test('amig nincs nev es ceg, minden fordulo elejen ott all, hogy hianyzik', () => {
  // Eles hivas, 2026-09-23: az agent vegigvitt egy teljes erdeklodest,
  // ajanlatot igert, es a hivas vegen nem tudtuk, ki hivott. A szabaly
  // ott volt a promptban, csak husz fordulo utan elhalvanyult.
  const block = buildFactsBlock(facts(), '+36301300242');
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
  const block = buildFactsBlock(facts({ nev: 'Kovács Péter', ceg: 'Pelda Kft.' }), '');
  assert.doesNotMatch(block, /AMI MÉG HIÁNYZIK/);
});

test('kulon jelzi, ha csak az egyik hianyzik', () => {
  const csakNev = buildFactsBlock(facts({ nev: 'Kovács Péter' }), '');
  assert.match(csakNev, /AMI MÉG HIÁNYZIK/);
  assert.match(csakNev, /CÉG/);
  assert.doesNotMatch(csakNev, /a hívó NEVE/);

  const csakCeg = buildFactsBlock(facts({ ceg: 'Pelda Kft.' }), '');
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
  const block = buildFactsBlock(facts({ nev: 'K P', ceg: 'K Kft.' }), '+36301300242');
  assert.match(block, /HA KÜLDENED KELL VALAMIT/);
  assert.match(block, /SMS/);
});

test('ervenyes cim mellett nem eroltetjuk az SMS-t', () => {
  const block = buildFactsBlock(
    facts({ nev: 'K P', ceg: 'K Kft.', email: 'k@pelda.hu' }),
    '+36301300242',
  );
  assert.doesNotMatch(block, /HA KÜLDENED KELL VALAMIT/);
});

test('szam nelkul nincs mit SMS-ben kuldeni', () => {
  const block = buildFactsBlock(facts({ nev: 'K P', ceg: 'K Kft.' }), '<ismeretlen>');
  assert.doesNotMatch(block, /HA KÜLDENED KELL VALAMIT/);
});

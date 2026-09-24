import { test } from 'node:test';
import assert from 'node:assert/strict';

import { buildFactsBlock, buildSystemPrompt } from './prompt.js';
import { emptyFacts, type CallFacts } from './llm.js';

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

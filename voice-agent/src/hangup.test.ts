import { test } from 'node:test';
import assert from 'node:assert/strict';

import { END_CALL_MARKER, MarkerFilter, hangupDelayMs, stripMarker } from './hangup.js';
import { buildSystemPrompt } from './prompt.js';

function run(deltas: string[]): { said: string; found: boolean } {
  const f = new MarkerFilter();
  let said = '';
  for (const d of deltas) said += f.push(d);
  said += f.flush();
  return { said, found: f.found };
}

test('a jel nem hangzik el, de eszrevesszuk', () => {
  const r = run(['Köszönöm a hívást, ', 'viszonthallásra! ', END_CALL_MARKER]);
  assert.equal(r.said, 'Köszönöm a hívást, viszonthallásra! ');
  assert.equal(r.found, true);
});

test('kettevagott jel is jel', () => {
  const r = run(['Viszonthallásra! [[', 'BO', 'NT]]']);
  assert.equal(r.said, 'Viszonthallásra! ');
  assert.equal(r.found, true);
});

test('ami a jel utan jon, az sem hangzik el', () => {
  const r = run(['Szia! [[BONT]] meg valami']);
  assert.equal(r.said, 'Szia! ');
  assert.equal(r.found, true);
});

test('jel nelkul minden elhangzik, a szogletes zarojel is', () => {
  const r = run(['Az ár [', '[nettó] kétszázezer']);
  assert.equal(r.said, 'Az ár [[nettó] kétszázezer');
  assert.equal(r.found, false);
});

test('a stream vegen visszatartott felig-jel kimondodik', () => {
  const r = run(['Rendben [[BO']);
  assert.equal(r.said, 'Rendben [[BO');
  assert.equal(r.found, false);
});

test('a tortenetbe jel nelkul kerul', () => {
  assert.equal(stripMarker(`Viszonthallásra! ${END_CALL_MARKER}`), 'Viszonthallásra!');
});

test('a varakozas eleg a bucsura, de nem orokke', () => {
  assert.ok(hangupDelayMs('Viszonthallásra!') >= 2_500);
  assert.ok(hangupDelayMs('x'.repeat(1_000)) <= 12_000);
  assert.ok(hangupDelayMs('x'.repeat(100)) > hangupDelayMs('x'.repeat(20)));
});

test('a rendszerprompt tanitja a jelet, mindket nyelven', () => {
  for (const lang of ['hu', 'en'] as const) {
    const p = buildSystemPrompt(0, undefined, '', lang);
    assert.ok(p.includes(END_CALL_MARKER), `${lang}: a jel hianyzik a promptbol`);
  }
});

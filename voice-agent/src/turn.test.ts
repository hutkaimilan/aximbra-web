import { test } from 'node:test';
import assert from 'node:assert/strict';

import { looksUnfinished } from './turn.js';

test('az eles hivas felmondatai befejezetlennek szamitanak', () => {
  // Eles hivas, 2026-11-10: ezekre valaszolt az agent, belevagva a hivoba.
  assert.equal(looksUnfinished('A'), true);
  assert.equal(looksUnfinished('Megjön a termék. Teszem azt,'), true);
  assert.equal(looksUnfinished('Úgy néz ki a folyamatunk, hogy így csak itt a magyarországi, amiről jelenleg beszélek, Megjön a termék. Teszem azt'), true);
  assert.equal(looksUnfinished('Mi egy olyan logisztikai cég vagyunk, ami a'), true);
  assert.equal(looksUnfinished('Ööö'), true);
  assert.equal(looksUnfinished('So we have, um'), true);
});

test('a teljes mondatokra es rovid valaszokra nem varunk', () => {
  assert.equal(looksUnfinished('Egy ilyen logisztikai cégnek mit ajánlanál?'), false);
  assert.equal(looksUnfinished('Naponta tizenöt-húsz hívás jön.'), false);
  assert.equal(looksUnfinished('Igen'), false);
  assert.equal(looksUnfinished('Nem.'), false);
  assert.equal(looksUnfinished('Rendben'), false);
  assert.equal(looksUnfinished('Köszönöm, viszonthallásra!'), false);
  assert.equal(looksUnfinished('Kiss István vagyok'), false);
  assert.equal(looksUnfinished('Yes'), false);
  assert.equal(looksUnfinished(''), false);
});

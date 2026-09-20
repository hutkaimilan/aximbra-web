/**
 * A koszono SMS cimzettje.
 *
 * Egyetlen dolgot orzunk: a beepitett hivastesztelo sajat szamara nem megy
 * SMS. Az onnan erkezo hivas egy robot, es a Twilio ugyis elutasitja a
 * kuldest (Error 21408) - minden teszthivas egy hibastack-et hagyott a
 * naplokban.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { isTestHarnessNumber } from './sms.js';

const HARNESS = '+19498107263';

test('a tesztelo sajat szama nem kap SMS-t', () => {
  process.env['TEST_AGENT_FROM'] = HARNESS;
  assert.equal(isTestHarnessNumber(HARNESS), true);
});

test('a formazas nem szamit: ugyanaz a szam ugyanaz marad', () => {
  process.env['TEST_AGENT_FROM'] = '+1 (949) 810-7263';
  assert.equal(isTestHarnessNumber(HARNESS), true);
});

test('valodi hivo kap SMS-t', () => {
  process.env['TEST_AGENT_FROM'] = HARNESS;
  assert.equal(isTestHarnessNumber('+36209876543'), false);
});

test('beallitatlan TEST_AGENT_FROM nem nemit el mindenkit', () => {
  // Ez a veszelyes ag: ha az ures ertek "egyezne", egyetlen hivo sem kapna
  // SMS-t azokban a kornyezetekben, ahol nincs tesztelo beallitva.
  delete process.env['TEST_AGENT_FROM'];
  assert.equal(isTestHarnessNumber('+36209876543'), false);
  assert.equal(isTestHarnessNumber(''), false);
});

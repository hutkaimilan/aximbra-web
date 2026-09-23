import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  toE164,
  isAllowedDestination,
  admitCallback,
  refundCallback,
  callbackStats,
  resetCallbackState,
  ALLOWED_PREFIXES,
} from './callback.js';

/* ---------------- szam-normalizalas ---------------- */

test('a magyar felhasznalo negyfelekeppen irja le ugyanazt a szamot', () => {
  for (const written of [
    '+36301234567',
    '+36 30 123 4567',
    '0036301234567',
    '06 30 123 4567',
    '06-30-123-4567',
    '(06) 30/123-4567',
    '30 123 4567',
  ]) {
    assert.equal(toE164(written), '+36301234567', `nem jo: ${written}`);
  }
});

test('a hibas szam nem valik ervenyesse', () => {
  for (const bad of ['', '   ', 'hivj fel', '+36', '123', '+0123456789', 'tel:+36301234567']) {
    assert.equal(toE164(bad), null, `atcsuszott: ${bad}`);
  }
});

test('a 06-os elotag nem ragad egy mar nemzetkozi szamra', () => {
  // A +3630... nem lehet +36 36 30...
  assert.equal(toE164('+36301234567'), '+36301234567');
  // A 0049 nemet szamot nem irjuk at magyarra.
  assert.equal(toE164('004915112345678'), '+4915112345678');
});

test('csak magyar mobil-korzet egeszul ki orszaghivo nelkul', () => {
  // A 30 magyar mobil-korzet -> kiegeszul.
  assert.equal(toE164('301234567'), '+36301234567');
  // Az 1-es budapesti vezetekes NEM: kilenc jegy nelkul nem talalgatunk.
  assert.equal(toE164('12345678'), null);
});

/* ---------------- orszag-szures ---------------- */

test('a lap nyelveinek orszagaiba hivhatunk', () => {
  for (const ok of [
    '+36301234567',   // HU
    '+4915112345678', // DE
    '+33612345678',   // FR
    '+34612345678',   // ES
    '+393331234567',  // IT
    '+40721234567',   // RO
    '+421901234567',  // SK
    '+447700900123',  // GB
    '+14155550123',   // US
  ]) {
    assert.equal(isAllowedDestination(ok), true, `nem engedte: ${ok}`);
  }
});

test('draga es egzotikus iranyokba nem hivunk', () => {
  // Muholdas (+882), Kuba, Szomalia, Eszaki-Mariana - ezek a klasszikus
  // szamlacsapdak. Egy tiltolista elfelejtene oket; az engedelyezo lista nem.
  for (const bad of ['+88212345678', '+5312345678', '+252612345678', '+6701234567']) {
    assert.equal(isAllowedDestination(bad), false, `atengedte: ${bad}`);
  }
});

test('az engedelyezett elotagok mind ervenyes alakuak', () => {
  for (const p of ALLOWED_PREFIXES) {
    assert.match(p, /^\+[1-9]\d{0,2}$/, `rossz elotag: ${p}`);
  }
});

/* ---------------- keretek ---------------- */

test('egy szamot naponta egyszer hivunk vissza', () => {
  resetCallbackState();
  assert.deepEqual(admitCallback('+36301234567', 10), { ok: true, to: '+36301234567' });

  const second = admitCallback('+36301234567', 10);
  assert.equal(second.ok, false);
  assert.equal(second.ok === false && second.reason, 'repeat');

  // Ugyanaz a szam mas alakban irva sem masodik hivas.
  const third = admitCallback('06 30 123 4567', 10);
  assert.equal(third.ok === false && third.reason, 'repeat');
});

test('a napi keret felulrol zarja a koltseget', () => {
  resetCallbackState();
  for (let i = 0; i < 3; i++) {
    assert.equal(admitCallback(`+3630123456${i}`, 3).ok, true, `${i}. hivas`);
  }
  const over = admitCallback('+36309999999', 3);
  assert.equal(over.ok, false);
  assert.equal(over.ok === false && over.reason, 'daily');
});

test('nulla napi kerettel a funkcio ki van kapcsolva', () => {
  resetCallbackState();
  const v = admitCallback('+36301234567', 0);
  assert.equal(v.ok, false);
  assert.equal(v.ok === false && v.reason, 'daily');
});

test('a hibas szam nem fogyaszt a keretbol', () => {
  resetCallbackState();
  admitCallback('nem szam', 2);
  admitCallback('+88212345678', 2); // tiltott irany
  assert.equal(callbackStats().total, 0);

  // A keret tehat erintetlen: ket valodi hivas meg belefer.
  assert.equal(admitCallback('+36301111111', 2).ok, true);
  assert.equal(admitCallback('+36302222222', 2).ok, true);
});

test('a sikertelen hivasindítás visszaadja a keretet', () => {
  resetCallbackState();
  const v = admitCallback('+36301234567', 1);
  assert.equal(v.ok, true);
  assert.equal(callbackStats().total, 1);

  // Twilio-hiba: nem tortent hivas.
  refundCallback('+36301234567');
  assert.equal(callbackStats().total, 0);

  // ...es a latogato ujra probalkozhat ugyanarrol a szamrol.
  assert.equal(admitCallback('+36301234567', 1).ok, true);
});

test('a visszaadas nem tud a nulla ala vinni', () => {
  resetCallbackState();
  refundCallback('+36301234567');
  refundCallback('+36301234567');
  assert.equal(callbackStats().total, 0);
  assert.equal(callbackStats().numbers, 0);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { checkTranscript, type SimTurn } from './sim.js';

const A = (text: string): SimTurn => ({ who: 'agent', text });
const C = (text: string): SimTurn => ({ who: 'caller', text });
const GREET = A('Jó napot kívánok! Az Aximbrától keresem. Miben segíthetek?');
const checks = (turns: SimTurn[], key = 'alap'): string[] => checkTranscript(turns, key).map((i) => i.check);

test('az eles hivas hibait elkapja: kereteln ar es siettetett zaras', () => {
  // Eles hivas, 2026-11-10 13:27.
  const got = checks([
    GREET,
    C('Azt szeretném kérdezni, hogy multiagent rendszert milyen vállalatoknak ajánlja?'),
    A('Olyan cégeknek, ahol a folyamatok összetettek. Hatmillió és tizenötmillió forint között mozog az ára. Kihez címezzem az ajánlatot, és melyik cégnél?'),
  ]);
  assert.ok(got.includes('ar_kerdes_nelkul'), got.join(','));
  assert.ok(got.includes('zaras_kerdes_kozben'), got.join(','));
});

test('a tegezest elkapja, a hivo tegezeset nem rojja fel', () => {
  const got = checks([
    GREET,
    C('Szia, mondd, mit tudnátok nekünk ajánlani?'),
    A('Önöknél az e-mail rendezőt kezdeném. Hány ember foglalkozik ezzel nálatok?'),
  ]);
  assert.deepEqual(got.filter((c) => c === 'tegezes'), ['tegezes']);
  const clean = checks([GREET, C('Szia, mondd, mit tudnátok ajánlani?'), A('Önöknél az e-mail rendezőt kezdeném.')]);
  assert.ok(!clean.includes('tegezes'), clean.join(','));
});

test('a "folytassam" es a hianyos felsorolas hiba', () => {
  const got = checks(
    [
      GREET,
      C('Sorolja fel az összes agentet, kérem.'),
      A('Az e-mail rendező a leveleket rendezi, az adminisztrációs agent adatot mozgat, a kutatás-monitor figyel. Folytassam?'),
    ],
    'lista',
  );
  assert.ok(got.includes('folytassam'), got.join(','));
  assert.ok(got.includes('lista_hianyos'), got.join(','));
});

test('a "van meg kerdese" masodszor es a nev masodszor hiba', () => {
  const got = checks([
    GREET,
    C('Mennyibe kerül?'),
    A('Százötvenezer forinttól. Van még kérdése, amiben segíthetek?'),
    C('Nincs több kérdésem.'),
    A('Kihez címezzem, és melyik cégnél?'),
    C('Ezt most nem mondanám.'),
    A('Rendben. Van még kérdése? Kihez címezzem?'),
  ]);
  assert.ok(got.includes('van_meg_kerdese_tobbszor'), got.join(','));
  assert.ok(got.includes('nev_tobbszor'), got.join(','));
});

test('egy szabalyos hivas tiszta', () => {
  const got = checks([
    GREET,
    C('Az e-mailek kezelése miatt keresem, napi ötven levél jön.'),
    A('Értem, erre az e-mail rendező való: beolvassa és kategóriákba rendezi a leveleket. Most kézzel osztják szét őket?'),
    C('Igen, kézzel. És ez mennyibe kerül?'),
    A('Az e-mail rendező százötvenezer és négyszázezer forint között van, két-három hét alatt elkészül.'),
    C('Értem, köszönöm, ennyi lenne.'),
    A('Van még kérdése, amiben segíthetek?'),
    C('Nincs, köszönöm.'),
    A('Szívesen küldök írásos ajánlatot. Kihez címezzem, és melyik cégnél?'),
  ]);
  assert.deepEqual(got, []);
});

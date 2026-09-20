import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  routeCall,
  ownerDialTwiml,
  screenTwiml,
  screenDoneTwiml,
  takeAccepted,
  markAccepted,
  languageSwitchMessage,
  langFromDigits,
  languageMenuTwiml,
  RELAY_LANG_CODE,
} from './routing.js';

const OWNER = '+36301234567';
const SID = 'CA0123456789abcdef0123456789abcdef';

test('magyar mobil a tulajdonoshoz megy', () => {
  assert.deepEqual(routeCall('+36209876543', OWNER), { to: 'owner' });
});

test('magyar vezetekes is a tulajdonoshoz megy', () => {
  assert.deepEqual(routeCall('+3612345678', OWNER), { to: 'owner' });
});

test('kulfoldi szam az agenthez megy, angolul', () => {
  assert.deepEqual(routeCall('+14155550123', OWNER), { to: 'agent', lang: 'en' });
  assert.deepEqual(routeCall('+4915112345678', OWNER), { to: 'agent', lang: 'en' });
});

test('a hasonlo orszagkodok nem csusznak at magyarkent', () => {
  // +353 Irorszag, +370 Litvania.
  assert.deepEqual(routeCall('+35312345678', OWNER), { to: 'agent', lang: 'en' });
  assert.deepEqual(routeCall('+37012345678', OWNER), { to: 'agent', lang: 'en' });
});

test('rejtett vagy hibas szam: agent, magyarul', () => {
  for (const from of ['', null, undefined, 'anonymous', '+266696687x', 'client:web']) {
    assert.deepEqual(routeCall(from, OWNER), { to: 'agent', lang: 'hu' }, String(from));
  }
});

test('a tulajdonos a sajat telefonjarol az agentet eri el', () => {
  assert.deepEqual(routeCall(OWNER, OWNER), { to: 'agent', lang: 'hu' });
});

test('beallitott tulajdonosi szam nelkul nincs atkapcsolas', () => {
  assert.deepEqual(routeCall('+36209876543', ''), { to: 'agent', lang: 'hu' });
  assert.deepEqual(routeCall('+14155550123', ''), { to: 'agent', lang: 'en' });
});

test('szokozos, kotojeles szam is felismerheto', () => {
  assert.deepEqual(routeCall('+36 20 987-6543', OWNER), { to: 'owner' });
});

test('az atkapcsolas a Twilio-szamot mutatja, szures-URL-lel es fallback-kel', () => {
  const xml = ownerDialTwiml({
    host: 'voice.example',
    ownerPhone: OWNER,
    ringSeconds: 20,
    callSid: SID,
    calledNumber: '+18024249852',
  });
  assert.match(xml, /<Dial timeout="20" answerOnBridge="true" callerId="\+18024249852"/);
  assert.match(xml, /action="https:\/\/voice\.example\/twiml\/owner-done"/);
  assert.match(xml, new RegExp(`url="https://voice\\.example/twiml/screen\\?parent=${SID}"`));
  assert.match(xml, />\+36301234567<\/Number>/);
});

test('hibas hivott szamnal nincs callerId', () => {
  const xml = ownerDialTwiml({
    host: 'voice.example',
    ownerPhone: OWNER,
    ringSeconds: 20,
    callSid: SID,
    calledNumber: '',
  });
  assert.doesNotMatch(xml, /callerId/);
});

test('a szures egy gombot var, es utana bont', () => {
  const xml = screenTwiml('voice.example', SID, 'Google.hu-HU-Wavenet-A', 'hu-HU');
  assert.match(xml, /<Gather numDigits="1"/);
  assert.match(xml, new RegExp(`action="https://voice\\.example/twiml/screen-done\\?parent=${SID}"`));
  assert.match(xml, /<\/Gather>\s*<Hangup\/>/);
});

test('1-es gomb: osszekapcsol es megjegyzi, hogy fogadta', () => {
  const xml = screenDoneTwiml('1', SID);
  assert.match(xml, /<Response\/>/);
  assert.equal(takeAccepted(SID), true);
  // Egy hivasra egyszer kerdezunk.
  assert.equal(takeAccepted(SID), false);
});

test('mas gomb vagy hibas azonosito: bont, es nem fogadottkent jegyzi', () => {
  assert.match(screenDoneTwiml('2', SID), /<Hangup\/>/);
  assert.equal(takeAccepted(SID), false);
  assert.match(screenDoneTwiml('1', 'CAnemjo'), /<Hangup\/>/);
  assert.equal(takeAccepted('CAnemjo'), false);
});

test('a regi fogadasok kiesnek a nyilvantartasbol', () => {
  const old = 'CAffffffffffffffffffffffffffffffff';
  markAccepted(old, 0);
  markAccepted(SID, 4 * 60 * 60 * 1000);
  assert.equal(takeAccepted(old), false);
  assert.equal(takeAccepted(SID), true);
});

/* ------------------------------------------------------------------ */
/* Nyelvvaltas hivas kozben                                             */
/* ------------------------------------------------------------------ */

test('a nyelvvaltas uzenete mindket iranyt egyutt allitja', () => {
  // Ez a lenyeg: ha csak az egyiket allitanank at, pontosan az az allapot
  // allna elo, ami ketszer is eltorte elesben a hivasokat - a hivo egyik
  // nyelven beszel, a felismero a masikat varja.
  const hu = JSON.parse(languageSwitchMessage('hu')) as Record<string, string>;
  assert.equal(hu['type'], 'language');
  assert.equal(hu['ttsLanguage'], 'hu-HU');
  assert.equal(hu['transcriptionLanguage'], 'hu-HU');

  const en = JSON.parse(languageSwitchMessage('en')) as Record<string, string>;
  assert.equal(en['type'], 'language');
  assert.equal(en['ttsLanguage'], 'en-US');
  assert.equal(en['transcriptionLanguage'], 'en-US');
});

test('csak olyan nyelvre valthatunk, amit a TwiML deklaral', () => {
  // A relayTwiml `<Language code=...>` gyerekei pontosan ezek. Ha ez a ket
  // ertek elcsuszik a TwiML-tol, a valtas a hivas kozben ervenytelen lesz,
  // es a hivo nemasagot kap - ezert all itt, teszt ala kotve.
  assert.deepEqual(Object.keys(RELAY_LANG_CODE).sort(), ['en', 'hu']);
  assert.equal(RELAY_LANG_CODE.hu, 'hu-HU');
  assert.equal(RELAY_LANG_CODE.en, 'en-US');
});

/* ------------------------------------------------------------------ */
/* Nyelvvalaszto menu                                                   */
/* ------------------------------------------------------------------ */

test('a gomb dont, es a dontes jelolve van', () => {
  assert.deepEqual(langFromDigits('1'), { lang: 'hu', chosen: true });
  assert.deepEqual(langFromDigits('2'), { lang: 'en', chosen: true });
});

test('gomb nelkul magyar, de nem a hivo dontesekent', () => {
  // A kulonbseg nem kozomboS: a `chosen: false` engedi, hogy a
  // beszedfelismeres kesobb korrigaljon. Egy megnyomott gombot viszont
  // semmi nem irhat felul.
  for (const d of [null, undefined, '', '0', '9', '#', '*', '12', 'egy']) {
    assert.deepEqual(langFromDigits(d), { lang: 'hu', chosen: false }, String(d));
  }
});

test('a menu mindket nyelven felkinalja mindket gombot', () => {
  const xml = languageMenuTwiml({
    host: 'voice.example',
    huVoice: 'Google.hu-HU-Wavenet-A',
    enVoice: 'Google.en-US-Wavenet-F',
    timeoutSeconds: 6,
  });

  // Aki csak magyarul ert, es aki csak angolul, mindketto tudja meg
  // mindket lehetoseget - kulonben a masik nyelvu hivo talalgatna.
  assert.match(xml, /nyomja meg az egyes gombot/);
  assert.match(xml, /nyomja meg a kettes gombot/);
  assert.match(xml, /press one/);
  assert.match(xml, /press two/);

  assert.ok(
    xml.indexOf('hu-HU') < xml.indexOf('en-US'),
    'elobb magyarul hangzik el, aztan angolul',
  );

  // Gomb nelkul sem szabad zsakutcaban vegzodnie: a Redirect ugyanoda megy,
  // es ott az idotulleples magyar valasztassa valik.
  assert.match(xml, /<Redirect method="POST">https:\/\/voice\.example\/twiml\/lang<\/Redirect>/);
});

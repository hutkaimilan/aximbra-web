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

import { FormalFilter, formalize } from './turn.js';

test('a tegezo nevmasok magazora cserelodnek', () => {
  assert.equal(formalize('Hány ember foglalkozik ezzel nálatok?'), 'Hány ember foglalkozik ezzel Önöknél?');
  assert.equal(formalize('Küldök nektek egy ajánlatot, neked is jó?'), 'Küldök Önöknek egy ajánlatot, Önnek is jó?');
  // Mas szavak belsejeben nem nyul hozza.
  assert.equal(formalize('A nálatoknál szó nem létezik, a nekedvaló sem.'), 'A nálatoknál szó nem létezik, a nekedvaló sem.');
});

test('streamelve, darabokra torve is cserel', () => {
  const f = new FormalFilter();
  const out = ['Hány ember ', 'foglalkozik ezzel nála', 'tok', '?'].map((d) => f.push(d)).join('') + f.flush();
  assert.equal(out, 'Hány ember foglalkozik ezzel Önöknél?');
});

import { MORE_QUESTIONS_RE, SentenceDropFilter, dropSentences } from './turn.js';

test('a mar elhangzott "Van meg kerdese?" kimarad, a tobbi marad', () => {
  const text = 'A havi díjról előre megállapodunk. Van még kérdése, amiben segíthetek?';
  assert.equal(dropSentences(text, MORE_QUESTIONS_RE), 'A havi díjról előre megállapodunk.');
  const f = new SentenceDropFilter(MORE_QUESTIONS_RE);
  const out = ['A havi díjról ', 'előre megállapodunk. Van ', 'még kérdése, amiben segíthetek?'].map((d) => f.push(d)).join('') + f.flush();
  assert.equal(out.trim(), 'A havi díjról előre megállapodunk.');
  // Kikapcsolva mindent atenged.
  assert.equal(dropSentences(text, null), text);
});

test('a gyakori tegezo igealakok is magazora cserelodnek', () => {
  assert.equal(formalize('Hányan vagytok, és mit szeretnél automatizálni?'), 'Hányan vannak, és mit szeretne automatizálni?');
  assert.equal(formalize('Mondd, tudod, mit használtok most?'), 'Mondja, tudja, mit használnak most?');
  assert.equal(formalize('Kérlek, írj nekünk.'), 'Kérem, írjon nekünk.');
});

import { dropPattern } from './turn.js';

test('amig a hivo nem kerdezte, az ar nem hangzik el; utana igen', () => {
  const h1 = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'Papír naptárat használunk, sokszor meg kell szakítani a munkát.' },
  ];
  const reply = 'Értem, ezt át tudjuk venni. Az agentjeink százötvenezer forinttól indulnak. Naponta hány hívás jön?';
  assert.equal(dropSentences(reply, dropPattern(h1)), 'Értem, ezt át tudjuk venni. Naponta hány hívás jön?');
  const h2 = [...h1, { role: 'assistant', content: 'Értem.' }, { role: 'user', content: 'És mennyibe kerül?' }];
  assert.equal(dropSentences(reply, dropPattern(h2)), reply);
});

test('ha minden mondat kiesne, az eredeti hangzik el (nincs nema valasz)', () => {
  const h = [{ role: 'user', content: 'Mit csinál az e-mail rendező?' }];
  const only = 'Százötvenezer forinttól indul.';
  assert.equal(dropSentences(only, dropPattern(h)), only);
  const f = new SentenceDropFilter(dropPattern(h));
  assert.equal(f.push(only) + f.flush(), only);
});

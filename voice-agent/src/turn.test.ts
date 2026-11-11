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

test('zaras: nev/ajanlat/SMS csak ha a hivo vegzett vagy maga kerte', () => {
  const base = [{ role: 'assistant', content: 'Jó napot kívánok!' }];
  const reply = 'Két-három hét alatt elkészül. Küldjem el az ajánlatot SMS-ben erre a számra?';
  // Eles panasz: a hivo meg kerdez, az agent mar az ajanlatot kuldene.
  const asking = [...base, { role: 'user', content: 'És mennyi idő alatt készül el?' }];
  assert.equal(dropSentences(reply, dropPattern(asking)), 'Két-három hét alatt elkészül.');
  const done = [...asking, { role: 'assistant', content: 'Két-három hét.' }, { role: 'user', content: 'Értem, köszönöm.' }];
  assert.equal(dropSentences(reply, dropPattern(done)), reply);
  const requested = [...base, { role: 'user', content: 'Kérnék egy ajánlatot. Mennyi idő alatt készül el?' }];
  assert.equal(dropSentences(reply, dropPattern(requested)), reply);
});

test('van meg kerdese: csak nyugtazas utan, es csak egyszer; ujrakoszones nincs', () => {
  const base = [{ role: 'assistant', content: 'Jó napot kívánok!' }];
  const r = 'Értem. Van még kérdése, amiben segíthetek?';
  const statement = [...base, { role: 'user', content: 'Napi tizenöt-huszonöt hívás jön.' }];
  assert.equal(dropSentences(r, dropPattern(statement)), 'Értem.');
  const ack = [...base, { role: 'user', content: 'Értem.' }];
  assert.equal(dropSentences(r, dropPattern(ack)), r);
  const greet = 'Üdvözlöm, Kiss úr! Ez kivitelezhető.';
  assert.equal(dropSentences(greet, dropPattern(statement)), 'Ez kivitelezhető.');
});

import { CALLER_DONE_RE, OFFER_REQUEST_RE, callbackWording, callerIsWrapping } from './turn.js';

test('lezaras-felismeres: kerdes es meseles kozben nem zarunk (szimulator, 2026-11-11)', () => {
  // Hamis talalatok a korabbi mintaban: "Mennyi lenne" -> "ennyi lenne", "ez elég nehéz" -> "ez elég".
  assert.equal(CALLER_DONE_RE.test('Mennyi lenne nagyjából?'), false);
  assert.equal(CALLER_DONE_RE.test('Napi tizenöt-huszonöt hívást kapunk, és ez elég nehéz, mert munka közben kell felvenni.'), false);
  assert.equal(CALLER_DONE_RE.test('Ennyi lenne a havidíj?'), false);
  assert.equal(CALLER_DONE_RE.test('Ennyi lenne, köszönöm.'), true);
  assert.equal(CALLER_DONE_RE.test('Nekem ez elég.'), true);
  assert.equal(CALLER_DONE_RE.test('Nincs több kérdésem.'), true);
  assert.equal(CALLER_DONE_RE.test('Rendben, értem. Akkor ha érdekelni fog, keresni foglak.'), true);
  assert.equal(CALLER_DONE_RE.test('Majd jelentkezem, viszonthallásra!'), true);
  assert.equal(CALLER_DONE_RE.test('Az e-mail-kezelés automatizálása miatt keresem önöket.'), false);
});

test('ajanlatkeres: csak a kifejezett keres szamit', () => {
  assert.equal(OFFER_REQUEST_RE.test('Egy e-mail rendező agentre kérnék ajánlatot.'), true);
  assert.equal(OFFER_REQUEST_RE.test('Küldjenek egy árajánlatot!'), true);
  assert.equal(OFFER_REQUEST_RE.test('Elnézést, gép van a vonalban? Inkább egy kollégával beszélnék.'), true);
  assert.equal(OFFER_REQUEST_RE.test('Hívjanak vissza holnap.'), true);
  assert.equal(OFFER_REQUEST_RE.test('Tudna egy kolléga visszahívni? Visszahívnának?'), true);
  // Ezek NEM keresek - a korabbi minta mindre rakapcsolt.
  assert.equal(OFFER_REQUEST_RE.test('Igen, én kértem a visszahívást, az e-mailek miatt.'), false);
  assert.equal(OFFER_REQUEST_RE.test('A kollégáim nem érnek rá, egész nap az ügyfelekkel vannak.'), false);
  assert.equal(OFFER_REQUEST_RE.test('Mi van benne az ajánlatban?'), false);
  assert.equal(OFFER_REQUEST_RE.test('Az e-mail-kezelés automatizálása miatt keresem önöket.'), false);
});

test('a hivo vegzett-e: kerdes, elakadas, "nincs"', () => {
  const g = { role: 'assistant', content: 'Jó napot kívánok!' };
  const u = (c: string) => ({ role: 'user', content: c });
  const a = (c: string) => ({ role: 'assistant', content: c });
  // Kerdes: soha nem lezaras, akkor sem, ha "értem" is van benne.
  assert.equal(callerIsWrapping([g, u('Értem. És mennyibe kerül?')]), false);
  // A mi kerdesunkre adott puszta "Értem." elakadas, nem lezaras.
  assert.equal(callerIsWrapping([g, u('Fodrászat vagyunk.'), a('Naponta hány hívás jön?'), u('Értem.')]), false);
  // Allitasunk utan az "Értem." lezaras.
  assert.equal(callerIsWrapping([g, u('Mennyi idő?'), a('Két-három hét.'), u('Értem.')]), true);
  // "Van meg kerdese?" utan a "Nincs, köszönöm." lezaras.
  assert.equal(callerIsWrapping([g, u('Értem.'), a('Van még kérdése, amiben segíthetek?'), u('Nincs, köszönöm.')]), true);
  assert.equal(callerIsWrapping([g, u('Értem.'), a('Van még kérdése, amiben segíthetek?'), u('Igen, mikor tudnak kezdeni?')]), false);
});

test('eles minta: a hivo kerdesere nem jon "Van meg kerdese?" (szimulator, fodraszat)', () => {
  const h = [
    { role: 'assistant', content: 'Jó napot kívánok! Az Aximbrától keresem.' },
    { role: 'user', content: 'Jó napot, Kiss István vagyok. Weboldal és telefonos időpontfoglalás miatt hívom önöket.' },
    { role: 'assistant', content: 'Értem, ez kivitelezhető. Naponta nagyjából hány hívás érkezik Önökhöz?' },
    { role: 'user', content: 'Értem.' },
    { role: 'assistant', content: 'Naponta átlagosan hány hívást kell fogadniuk?' },
    { role: 'user', content: 'Napi tizenöt-huszonöt hívást kapunk, és ez elég nehéz. De az a lényeg, hogy ez kivitelezhető-e, amit mondtam?' },
  ];
  const reply = 'Igen, teljes mértékben kivitelezhető. Van még kérdése, amiben segíthetek?';
  assert.equal(dropSentences(reply, dropPattern(h)), 'Igen, teljes mértékben kivitelezhető.');
  const closing = 'Igen, kivitelezhető. Kihez címezzem az ajánlatot, és melyik cégnél?';
  assert.equal(dropSentences(closing, dropPattern(h)), 'Igen, kivitelezhető.');
});

test('korabbi ajanlatkeres utan: kerdes kozben nincs nevkerdes, utana lehet', () => {
  const base = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'Egy e-mail rendező agentre kérnék ajánlatot.' },
    { role: 'assistant', content: 'Szívesen. Van még kérdése, mielőtt felírom az adatait?' },
  ];
  const r = 'Két-három hét alatt. Kihez címezzem az ajánlatot?';
  const asks = [...base, { role: 'user', content: 'Mikor tudnának kezdeni?' }];
  assert.equal(dropSentences(r, dropPattern(asks)), 'Két-három hét alatt.');
  const tells = [...base, { role: 'user', content: 'Napi harminc-ötven rendelés jön e-mailben.' }];
  assert.equal(dropSentences(r, dropPattern(tells)), r);
});

test('visszahivasban "Köszönöm a beszélgetést", nem "a hívást"', () => {
  assert.equal(callbackWording('Köszönöm a hívást, viszonthallásra!'), 'Köszönöm a beszélgetést, viszonthallásra!');
  assert.equal(callbackWording('Rendben. Köszönöm szépen a hívást!'), 'Rendben. Köszönöm szépen a beszélgetést!');
  assert.equal(callbackWording('Thank you for calling, goodbye!'), 'Thank you for your time, goodbye!');
  assert.equal(callbackWording('Két-három hét alatt elkészül.'), 'Két-három hét alatt elkészül.');
});

import { MORE_QUESTIONS_RE as MQ, PRICE_ASKED_RE, dropRules } from './turn.js';

test('"Van még esetleg kérdése" es rokonai is felismerve', () => {
  for (const s of [
    'Van még kérdése, amiben segíthetek?',
    'Van még esetleg kérdése, amiben segíthetek, mielőtt rögzítem a részleteket?',
    'Van esetleg még kérdése?',
    'Lenne még más kérdése?',
    'Segíthetek még valamiben?',
    'Is there anything else I can help with?',
  ]) assert.equal(MQ.test(s), true, s);
  assert.equal(MQ.test('Van kérdése az árral kapcsolatban?'), false);
});

test('arkerdes: "mennyiség", "már", "mennyi idő" nem az', () => {
  assert.equal(PRICE_ASKED_RE.test('De azelőtt, hogy bármit is mondanék a mennyiségről, hol tárolódnak az adatok?'), false);
  assert.equal(PRICE_ASKED_RE.test('Már használunk Gmailt.'), false);
  assert.equal(PRICE_ASKED_RE.test('És mennyi idő, amíg elkészül?'), false);
  assert.equal(PRICE_ASKED_RE.test('Mennyi lenne nagyjából?'), true);
  assert.equal(PRICE_ASKED_RE.test('Mennyiért csinálják?'), true);
  assert.equal(PRICE_ASKED_RE.test('És ezek mennyibe kerülnek?'), true);
});

test('ha minden mondat kiesne: az ar marad, a tiltott zaro kerdes nem (szimulator, nehez)', () => {
  const h = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'A számlafeldolgozás miatt keresem.' },
    { role: 'assistant', content: 'Ezt a dokumentum-elemző végzi. Szeretné tudni, mennyibe kerülne?' },
    { role: 'user', content: 'Értem.' },
  ];
  const r = dropRules(h);
  const reply = 'A dokumentum-elemző kétmillió és négymillió forint között van. Van még kérdése, amiben segíthetek?';
  assert.equal(dropSentences(reply, r.strict, r.relaxed), 'A dokumentum-elemző kétmillió és négymillió forint között van.');
  const f = new SentenceDropFilter(r.strict, r.relaxed);
  assert.equal((f.push(reply) + f.flush()).trim(), 'A dokumentum-elemző kétmillió és négymillió forint között van.');
});

test('cegnev-kerdes a hivas kozepen kiesik', () => {
  const h = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'Varga Tamás vagyok, autószervizem van. Mennyibe kerül egy ilyen agent?' },
  ];
  const reply = 'Az agentjeink százötvenezer forinttól indulnak. Melyik szervizről van szó pontosan?';
  assert.equal(dropSentences(reply, dropPattern(h)), 'Az agentjeink százötvenezer forinttól indulnak.');
});

test('"akkor megkereslek" is lezaras', () => {
  assert.equal(CALLER_DONE_RE.test('Oké, akkor megkereslek. Köszönöm szépen.'), true);
  assert.equal(CALLER_DONE_RE.test('Rendben, majd felhívom önöket.'), true);
  assert.equal(CALLER_DONE_RE.test('Megkeresem a számlát, egy pillanat.'), false);
});

test('a nev-/cegkerdes nem ismetlodik (szimulator, emberkero)', () => {
  const h = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'Rendben, akkor kérem, hogy hívjanak vissza. Kiss Ágnes vagyok.' },
    { role: 'assistant', content: 'Rendben, Kiss asszony. Melyik cégnél dolgozik?' },
    { role: 'user', content: 'Értem.' },
  ];
  const reply = 'Megértettem, Kiss asszony. Melyik cégnél dolgozik, hogy a kollégáim felkészülhessenek?';
  assert.equal(dropSentences(reply, dropPattern(h)), 'Megértettem, Kiss asszony.');
});

test('ajanlatkeres: reszletek kuldese is keres, a "kérdezném" nem', () => {
  assert.equal(OFFER_REQUEST_RE.test('Right, okay. Could you send some more details to my email so I can look it over with my team?'), true);
  assert.equal(OFFER_REQUEST_RE.test('Küldjenek egy összefoglalót e-mailben.'), true);
  assert.equal(OFFER_REQUEST_RE.test('Kérnék egy részletes tájékoztatót.'), true);
  assert.equal(OFFER_REQUEST_RE.test('Azt kérdezném, mi van az ajánlatban.'), false);
  assert.equal(OFFER_REQUEST_RE.test('Azt szeretném kérdezni, hogy multiagent rendszert milyen vállalatoknak ajánlanak?'), false);
  assert.equal(OFFER_REQUEST_RE.test('A megrendeléseket e-mailben küldik nekünk.'), false);
  assert.equal(OFFER_REQUEST_RE.test('Do you send invoices to clients?'), false);
});

test('megkezdett zaras: a nev megadasa utan az SMS nyugtazasa nem esik ki', () => {
  const h = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'Mennyibe kerül az e-mail rendező?' },
    { role: 'assistant', content: 'Százötvenezer és négyszázezer forint között.' },
    { role: 'user', content: 'Értem.' },
    { role: 'assistant', content: 'Van még kérdése, amiben segíthetek?' },
    { role: 'user', content: 'Nincs, köszönöm.' },
    { role: 'assistant', content: 'Szívesen elküldöm az ajánlatot SMS-ben erre a számra. Kihez címezzem, és melyik cégnél?' },
    { role: 'user', content: 'Kovács Éva, Kovács és Társa Bt.' },
  ];
  const reply = 'Köszönöm, Kovács asszony. Az ajánlatot SMS-ben elküldöm erre a számra. Köszönöm a beszélgetést, viszonthallásra!';
  assert.equal(dropSentences(reply, dropPattern(h)), reply);
  // De ha a zaras kozben ujra kerdez, elobb a valasz jon, SMS nelkul.
  const asks = [...h.slice(0, -1), { role: 'user', content: 'Előtte még: mennyi idő alatt készül el?' }];
  assert.equal(
    dropSentences('Két-három hét alatt. Az ajánlatot SMS-ben elküldöm erre a számra.', dropPattern(asks)),
    'Két-három hét alatt.',
  );
});

test('angol lezaras: "that\'s what I needed" nem kerdes', () => {
  const g = { role: 'assistant', content: 'It is between one hundred fifty and four hundred thousand forints.' };
  assert.equal(callerIsWrapping([g, { role: 'user', content: "Thanks, that's what I needed." }]), true);
  assert.equal(callerIsWrapping([g, { role: 'user', content: 'Okay. What happens if it gets something wrong' }]), false);
  assert.equal(callerIsWrapping([g, { role: 'user', content: 'Thanks. Could you send it over' }]), false);
});

import { BUGFIX_SAID_RE, NUDGE_RE, META_RE } from './turn.js';

test('felelossegi mondat: a hibajavitas csak kerdesre, a jovahagyas egyszer (szimulator, alap)', () => {
  const base = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'Mennyibe kerül az e-mail rendező?' },
    { role: 'assistant', content: 'Százötvenezer és négyszázezer forint között.' },
  ];
  const reply =
    'Jellemzően két-három hét. Az agent semmit nem küld ki magától: minden kimenetet egy kolléga hagy jóvá, így a végső döntés és a felelősség az Önöké marad. Ha pedig a rendszerben hibát találunk, azt a havidíj keretében mi javítjuk.';
  const time = [...base, { role: 'user', content: 'És mennyi idő alatt tudnánk elindítani?' }];
  assert.equal(
    dropSentences(reply, dropPattern(time)),
    'Jellemzően két-három hét. Az agent semmit nem küld ki magától: minden kimenetet egy kolléga hagy jóvá, így a végső döntés és a felelősség az Önöké marad.',
  );
  // Ha a hibarol kerdez, a teljes ket mondat elhangzik.
  const err = [...base, { role: 'user', content: 'És mi történik, ha az agent hibázik?' }];
  assert.equal(dropSentences(reply, dropPattern(err)), reply);
  // Masodszorra, kerdes nelkul, a jovahagyas sem ismetlodik.
  const again = [
    ...time,
    { role: 'assistant', content: 'Az agent semmit nem küld ki magától: minden kimenetet egy kolléga hagy jóvá.' },
    { role: 'user', content: 'Hol tárolódnak az adatok?' },
  ];
  assert.equal(
    dropSentences('Az Önök saját infrastruktúráján. Az agent semmit nem küld ki magától: minden kimenetet egy kolléga hagy jóvá.', dropPattern(again)),
    'Az Önök saját infrastruktúráján.',
  );
  assert.equal(BUGFIX_SAID_RE.test('If we find a bug in the system, we fix it within the monthly maintenance fee.'), true);
});

test('ajanlkozo kerdes es sajat szabaly kimondasa kiesik', () => {
  assert.equal(NUDGE_RE.test('Érdekli esetleg, hogyan működik a gyakorlatban a folyamatok jóváhagyása?'), true);
  assert.equal(NUDGE_RE.test('Szeretné tudni, hogy ez pontosan mennyibe kerülne?'), true);
  assert.equal(NUDGE_RE.test('Would you like to know more about how it handles the triage process?'), true);
  assert.equal(NUDGE_RE.test('Melyik érdekli ezek közül?'), false);
  assert.equal(NUDGE_RE.test('Érdekli inkább a telefonos agent?'), false);
  assert.equal(META_RE.test('Mivel a nevét és a cégét már megadta, más teendőnk nincs.'), true);
  const h = [{ role: 'assistant', content: 'Jó napot kívánok!' }, { role: 'user', content: 'Hogyan működik?' }];
  assert.equal(
    dropSentences('A beérkező leveleket osztályozza. Érdekli esetleg, hogy milyen folyamatokra építhető ki?', dropPattern(h)),
    'A beérkező leveleket osztályozza.',
  );
});

import { GOODBYE_SAID_RE } from './turn.js';

test('bucsuzo hivo: a nev, a szam es a koszonet lezaras (szimulator, lista)', () => {
  const h = [
    { role: 'assistant', content: 'Jó napot kívánok!' },
    { role: 'user', content: 'És az értékesítő agent mennyibe kerül?' },
    { role: 'assistant', content: 'Az értékesítő agent hatszázezer és másfél millió forint között érhető el.' },
    {
      role: 'user',
      content:
        'Köszönöm a tájékoztatást. Kovács Éva vagyok a Kovács és Társa Bt.-ból, a jelenleg használt számomon keresztül lehet elérni. Köszönöm szépen!',
    },
  ];
  assert.equal(callerIsWrapping(h), true);
  const reply = 'Köszönöm, Kovács asszony. Az ajánlatot SMS-ben elküldöm erre a számra. Köszönöm a beszélgetést, viszonthallásra!';
  assert.equal(dropSentences(reply, dropPattern(h)), reply);
  assert.equal(OFFER_REQUEST_RE.test('A telefonszámom ez, amiről hívtam.'), true);
  assert.equal(GOODBYE_SAID_RE.test('Köszönöm a beszélgetést, viszonthallásra!'), true);
  assert.equal(GOODBYE_SAID_RE.test('Köszönöm a tájékoztatást, Kovács asszony.'), false);
});

test('tovabblepesi szandek es mondat kozepi ajanlkozo kerdes (szimulator v9)', () => {
  assert.equal(OFFER_REQUEST_RE.test('Értem, köszönöm. Akkor mi a következő'), true);
  assert.equal(OFFER_REQUEST_RE.test("Okay, so what's the next step?"), true);
  assert.equal(
    NUDGE_RE.test('Since you asked about automating the inbox, would you like to know more about how this agent functions?'),
    true,
  );
  assert.equal(NUDGE_RE.test('Melyik érdekli ezek közül?'), false);
});

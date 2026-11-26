# Mit nézzen át egy ügyvéd

Ez nem jogi vélemény, hanem lista: mit **csinál ténylegesen a kód**, hogy az
adatkezelési tájékoztatót ne emlékezetből, hanem a valósággal összevetve
lehessen ellenőriztetni. A hivatkozott állítások helye zárójelben.

## 1. Harmadik országba történő adattovábbítás

Négy adatfeldolgozó az Egyesült Államokban van (`frontend/src/legal.js`):

| Feldolgozó | Mit kap | Mikor |
| --- | --- | --- |
| OpenAI | a levél/űrlap szövege | minden demó-futásnál |
| Google (Gmail API) | — (tőlük *olvasunk*) | csak ha a látogató csatlakoztatja a fiókját |
| Twilio | a hívás hangja és metaadata | a bemutató telefonszám hívásakor |
| Resend | a hívás-összefoglaló e-mail | hívás után |

**Kérdés az ügyvédnek:** melyikük szerepel az EU–USA adatvédelmi keret (DPF)
listáján, és ahol nem, ott kell-e SCC, illetve átadási hatásvizsgálat. A
tájékoztató jelenleg felsorolja őket, de a továbbítás **jogalapját nem nevezi
meg** — ez a legvalószínűbb hiányosság.

## 2. A tárhelyszolgáltató naplója

A Railway minden HTTP-kéréshez naplót vezet: idő, útvonal, státusz, böngésző
azonosítója és **IP-cím**. Ezt a szolgáltató kezeli, mi olvasni tudjuk,
törölni nem. A tájékoztató 2. pontja most már kimondja; a **megőrzési időt**
a Railway feltételeiből kell kiolvasni és beírni.

## 3. „A lap bezárásakor azonnal törlődik"

A lap `pagehide`-nál `sendBeacon`-nel jelez a kiszolgálónak
(`frontend/src/demos/EmailAgent.jsx`). Ez a szokásos esetben megérkezik, de
nem garantált. A szöveg ezért már úgy fogalmaz, hogy ilyenkor a 30 perces
határidő zárja le a munkamenetet. **Ellenőrizendő:** elég-e ez a pontosság.

## 4. Gmail-hozzáférés

Alapesetben `gmail.readonly`; `gmail.compose` csak külön bejelölésre. A
Google **Limited Use** követelménye előírja, hogy a felhasználói adatot nem
használjuk hirdetésre, nem adjuk tovább, és emberi szem csak a felhasználó
kifejezett kérésére lát bele. **Ellenőrizendő:** kimondja-e ezt a
tájékoztató olyan formában, amit a Google verifikációja elfogad.

## 5. Az ajánlatkérő űrlap

Név, e-mail, cég, üzenet → egyetlen e-mailben az adatkezelőhöz, adatbázis
nélkül (`backend/lead_intake.py`). Jogalap: hozzájárulás, megőrzés legfeljebb
2 év. **Ellenőrizendő:** a hozzájárulás szövege elég-e önmagában, és kell-e
külön tájékoztatás a visszavonás módjáról az űrlap mellett.

## 6. Ami még hiányzik

* **Adószám / nyilvántartási szám** — amint van, a `frontend/src/legal.js`
  `taxNumber` mezőjébe kerül, és mindkét jogi oldalon magától megjelenik.
* Az adatkezelő természetes személy, nem gazdasági társaság. Az impresszum ezt
  kimondja; **ellenőrizendő**, hogy egy magánszemély által üzemeltetett,
  postafiók-hozzáférést kérő szolgáltatásnak van-e további kötelezettsége.

## Ami biztosan rendben van

A tájékoztató minden állítása a kódból származik, nem sablonból: a 30 napos
és 50 leveles korlát, a mellékletolvasás két fájlos és 5 MB-os határa, az OCR
hiánya, és az, hogy a futás adatbázisba nem kerül — mindegyik mögött ott a
megfelelő konstans a `backend/mail_agent.py`-ban és az `attachments.py`-ban.

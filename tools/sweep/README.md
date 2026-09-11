# sweep

Végigjárja az összes útvonalat igazi böngészőben (asztali és telefon
nézetben), és összegyűjti, ami egy látogatónál hibaként jelentkezik:

* konzolhiba és kezeletlen kivétel,
* elbukott kérés, 4xx/5xx válasz, be nem töltött kép,
* `alt` nélküli kép, címke vagy `name` nélküli űrlapmező,
* duplikált `id`, nem létező elemre mutató horgony, névtelen link vagy gomb,
* `target="_blank"` `rel="noopener"` nélkül,
* 24 CSS-pixelnél kisebb érinthető felület (WCAG 2.2 AA),
* hiányzó `lang`, hiányzó vagy több `h1`, túl hosszú `title`/`description`,
* vízszintes túlcsordulás — és megnevezi a legszélső elemet.

## Futtatás

```sh
cd frontend && yarn build
python3 ../tools/sweep/serve.py "$PWD/build" 8099 &      # SPA-visszaesés az index.html-re
npm i playwright-core                                    # a böngésző már telepítve van
node ../tools/sweep/sweep.js http://127.0.0.1:8099
```

A Google Fonts kéréseit szándékosan megszakítja: egy függő stíluslap a
`DOMContentLoaded`-et is visszatartja, és abból vaktalálat lesz.

Ami **nem** ez a szkript dolga: a szöveg értelme, a tartalom igazsága és a
tényleges telefonos gesztusok. Ezeket kézzel kell nézni.

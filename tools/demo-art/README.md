# demo-art

A referencia-demók saját kiszolgálású képeit ez a három szkript állítja elő.
Azért van itt, mert az előző képek egy külső CDN-en voltak, és amikor az
megszűnt, nem maradt semmi, amiből újra elő lehetett volna állítani őket.

| Kimenet | Szkript | Hova kerül |
| --- | --- | --- |
| OLAJFA hero (JPEG) | `hero.py` + Chromium + `tojpg.sh` | `frontend/public/media/demo/olajfa-hero.jpg` |
| FLÓRA galéria (3 SVG) | `flora.py` | `frontend/public/media/demo/flora-{1,2,3}.svg` |

A paletta a `frontend/src/demos/demos.css`-ből jön; ha az arculat változik, a
színkonstansokat a szkriptek tetején kell átírni.

## Újragenerálás

```sh
python3 flora.py                      # a három SVG a munkakönyvtárba
python3 hero.py                       # hero.html
CH=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
"$CH" --no-sandbox --disable-gpu --hide-scrollbars \
      --window-size=2000,1250 --screenshot=hero.png "file://$PWD/hero.html"
./tojpg.sh "$PWD/hero.png" "$PWD/olajfa-hero.jpg" 0.85 1800
```

A `headless_shell` azért kell a rendes `chrome --headless` helyett, mert az
utóbbi a kért ablakméretnél alacsonyabb nézetablakot ad, és a kép aljára egy
üres sáv kerül. A `tojpg.sh` a böngésző canvasával konvertál: ebben a
környezetben nincs ImageMagick és PIL, az ffmpeg-ben pedig nincs PNG-dekóder
és JPEG-enkóder.

A kép determinisztikus: a `hero.py` rögzített maggal sorsolja a fényfoltokat,
tehát ugyanaz a bemenet ugyanazt a képet adja.

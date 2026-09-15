# DNS-lekérdező

A futtatókörnyezetben nincs `dig`, `host`, `nslookup` és `dnspython`, a
DNS-over-HTTPS végpontok pedig blokkoltak. A `getent hosts` csak A/AAAA
rekordot ad — CNAME-et, TXT-t és CAA-t nem lehet vele megnézni.

Enélkül a domain hibakeresése tippelés lenne. Ez a szkript nyers UDP-n
kérdezi a rendszer feloldóját, függőség nélkül.

```
python3 tools/dns/query.py                      # az aximbra.hu alapkészlete
python3 tools/dns/query.py example.com          # NS, CNAME, A, TXT, CAA
python3 tools/dns/query.py example.com TXT CAA  # csak a felsoroltak
```

Egy tanulság, ami miatt ez bekerült: a hiányzó parancs csendben elbukik, és
egy `|| echo "nincs ilyen rekord"` fallback ilyenkor azt írja ki, hogy nincs
rekord — pedig valójában nem is volt lekérdezés. Az „üres válasz” és a
„nem futott le” két különböző dolog.


## Az apex átállítása egy paranccsal — `fix-apex.py`

Az `aximbra.hu` apexén A-rekord áll, a Railway viszont CNAME-et vár, és az
él-IP-jét nem garantálja állandónak. Amíg ez így van, a tanúsítvány nem áll ki.

Ez a szkript **abból a környezetből nem futtatható, ahol készült**: ott a
szervezeti egress-szabály tiltja az `api.cloudflare.com` elérését. A saját
gépeden viszont lefut.

```
# Token: https://dash.cloudflare.com/profile/api-tokens
# Sablon: "Edit zone DNS" → Zone:DNS:Edit az aximbra.hu zónára
export CF_API_TOKEN="..."

python3 tools/dns/fix-apex.py           # csak megmutatja, mit tenne
python3 tools/dns/fix-apex.py --apply   # meg is csinálja
```

Alapból semmit nem ír. Az `--apply` sem töröl vakon: a meglévő A-rekordot
egy lépésben írja át CNAME-re, hogy a név egy pillanatra se maradjon rekord
nélkül.

Utána ellenőrizd:

```
python3 tools/dns/query.py aximbra.hu CNAME A
```

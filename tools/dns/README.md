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

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

## `cf.py` — DNS-vezérlés GitHub Actionsből

A fejlesztői környezetből az `api.cloudflare.com` elérése szervezeti szabályból
tiltott, tehát onnan DNS-t állítani nem lehet. A GitHub futtatója viszont eléri.
A `.github/workflows/dns.yml` ezért kézzel indítható munkafolyamat, ami a
`CF_API_TOKEN` repository secretet használja.

**Egyszeri beállítás:**

1. Cloudflare → https://dash.cloudflare.com/profile/api-tokens → **Create Token**
   → *Edit zone DNS* sablon → Zone Resources: `aximbra.hu` → **Create**
2. GitHub → a repó **Settings** → *Secrets and variables* → **Actions**
   → **New repository secret** → név: `CF_API_TOKEN`, érték: a token

**Utána:** Actions → *DNS* → *Run workflow*, vagy API-ról indítva.

```
show                                        # minden rekord
show www                                    # egy név rekordjai
proxy www off                               # szürke felhő
proxy @ off                                 # az apex is
set CNAME www t44uikmi.up.railway.app
set TXT _railway-verify.www "railway-verify=..."
delete A @
```

Az `apply` kapcsoló nélkül csak kiírja, mit tenne. A token sosem kerül a
naplóba, és a bemenet a Python argv-jébe megy, nem a shellbe — a szkript csak
Cloudflare DNS-hívásokat tud indítani.

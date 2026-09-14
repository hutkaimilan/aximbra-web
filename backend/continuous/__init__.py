"""A folyamatos, kétóránként futó agent.

Ez NEM a nyilvános demó kiterjesztése, és szándékosan külön modul. A demó azt
ígéri, hogy semmit nem tárol: memóriában él, fél óra alatt lejár, és minden
csatlakozás nulláról indul. Ez a rendszer ennek az ellenkezője — tokent őriz,
hogy két óra múlva magától újra megnézhesse a postafiókot —, tehát nem
kapcsolható rá ugyanarra az ígéretre.

Ezért:

  * ügyfelenként külön telepítés, saját adatkezelési tájékoztatóval;
  * alapból kikapcsolva (`CONTINUOUS_ENABLED`), és kulcs nélkül el sem indul;
  * a nyilvános demó kódja nem hívja, és nem is tud róla.
"""

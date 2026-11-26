"""edge-tts felolvasás: python3 tts.py "szöveg" ki.mp3 [hang] [tempó]"""
import asyncio, os, sys
# A felhős munkamenet proxyja saját CA-t használ; ha ott van, azt adjuk az edge-tts-nek.
_CA = "/root/.ccr/ca-bundle.crt"
if os.path.exists(_CA):
    import certifi
    certifi.where = lambda: _CA
import edge_tts

async def main(text, out, voice, rate):
    await edge_tts.Communicate(text, voice, rate=rate).save(out)

asyncio.run(main(sys.argv[1], sys.argv[2],
                 sys.argv[3] if len(sys.argv) > 3 else "hu-HU-TamasNeural",
                 sys.argv[4] if len(sys.argv) > 4 else "+8%"))

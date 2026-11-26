"""Minden narracios mondat felolvasasa (edge-tts, Tamas), gyorsitotarral."""
import hashlib, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cfg import AGENTS
TTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts.py")
os.makedirs("tts", exist_ok=True)

def path_for(text):
    return os.path.join("tts", hashlib.sha1(text.encode()).hexdigest()[:12] + ".wav")

def make(text):
    out = path_for(text)
    if os.path.exists(out):
        return out
    mp3 = out[:-4] + ".mp3"
    for attempt in range(4):
        r = subprocess.run([sys.executable, TTS, text, mp3, "hu-HU-TamasNeural", "+8%"], capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(mp3) and os.path.getsize(mp3) > 1000:
            break
    else:
        raise RuntimeError(f"tts failed: {text}: {r.stderr[-300:]}")
    # csend levagasa elol-hatul, 48 kHz mono
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                    "-ar", "48000", "-ac", "1", out], check=True)
    os.remove(mp3)
    return out

def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout)

if __name__ == "__main__":
    which = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else sorted(AGENTS)
    for k in which:
        a = AGENTS[k]
        tot = 0
        for b in a["beats"]:
            if b.get("say"):
                tot += dur(make(b["say"]))
        c = dur(make(a["cta"]))
        print(f"{k:2d} {a['name']:<24} narracio {tot:5.1f} s  cta {c:4.1f} s  ({len(a['beats'])} utem)")

"""Melyik Veo-klip melyik agenthez tartozik — a klip saját hangja alapján.

Használat: python3 identify.py klip1.mp4 klip2.mp4 ...
Kimenet: clipmap.json  {agent: klip}, és a nem egyértelmű klipek listája.

A felismert szöveget a 13 mondathoz hasonlítjuk (szóátfedés). Egy klip csak
akkor kerül egy agenthez, ha a legjobb egyezés egyértelmű; különben kézi
döntésre vár, és nem renderelünk rossz horoggal.
"""
import json, os, re, subprocess, sys, unicodedata
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cfg import AGENTS

def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]{3,}", s)

def transcribe(model, path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    if not raw:
        return ""
    segs, _ = model.transcribe(np.frombuffer(raw, np.float32).copy(), language="hu")
    return " ".join(s.text.strip() for s in segs)

if __name__ == "__main__":
    from faster_whisper import WhisperModel
    m = WhisperModel("small", device="cpu", compute_type="int8")
    common = set(norm("Megmutatom, hogyan egy AI Élőben Nézd"))
    mapping = json.load(open("clipmap.json")) if os.path.exists("clipmap.json") else {}
    unsure = []
    for p in sys.argv[1:]:
        text = transcribe(m, p)
        got = set(norm(text)) - common
        scores = []
        for k, a in AGENTS.items():
            want = set(norm(a["line"])) - common
            # részleges szóegyezés is számít (ragozás, félrehallás): közös 5 betűs eleje
            hit = sum(1 for w in want if any(g[:5] == w[:5] for g in got))
            scores.append((hit / max(1, len(want)), k))
        scores.sort(reverse=True)
        (s1, k1), (s2, _) = scores[0], scores[1]
        ok = s1 >= 0.5 and s1 - s2 >= 0.25
        print(f"{os.path.basename(p)}: \"{text}\" -> {k1} {AGENTS[k1]['name']} ({s1:.2f} vs {s2:.2f}){'' if ok else '  ?? KEZI DONTES'}")
        if ok:
            if str(k1) in mapping and mapping[str(k1)] != p:
                print(f"   figyelem: a(z) {k1}. agenthez mar van klip: {mapping[str(k1)]} (az ujabbat hasznalom)")
            mapping[str(k1)] = p
        else:
            unsure.append(p)
    json.dump(mapping, open("clipmap.json", "w"), indent=1, ensure_ascii=False)
    print("hozzarendelve:", sorted(int(k) for k in mapping), "| bizonytalan:", unsure)

import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { ImagePlus, Loader2, Send, Trash2, X } from "lucide-react";
import { buildContext } from "../lib/chatContext";
import { useSlip } from "../lib/slip";

// Csevegés a szelvényekről és a meccsekről (/api/chat → Gemini). A beszélgetés szövege a böngészőben
// megmarad; a képek csak a mostani munkamenetben (méretük miatt nem mentjük el).
const STORE = "chat-history";
const MAX_KEEP = 30;
const MAX_IMG_SIDE = 1400;
const MAX_ATTACH = 3;

const REVIEW = "Véleményezd a szelvényemet tippenként: erős, rendben, kockázatos vagy gyenge, és miért? "
  + "Melyik a leggyengébb láb, és mit cserélnél helyette?";
const QUICK = [
  "Melyik a legbiztosabb meccs a következő napokban, és mit raknál rá?",
  "Melyik meccsen várható sok gól?",
  "Melyik favorit tűnik túlárazottnak?",
];

function loadHistory() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) || "[]");
    return Array.isArray(v) ? v.filter((m) => m && (m.role === "user" || m.role === "assistant")) : [];
  } catch {
    return [];
  }
}

function saveHistory(msgs) {
  try {
    const slim = msgs.slice(-MAX_KEEP).map(({ role, text, images }) => ({ role, text, imgCount: images?.length || 0 }));
    localStorage.setItem(STORE, JSON.stringify(slim));
  } catch { /* privát mód: nem baj */ }
}

// Kép kicsinyítése JPEG-be (a telefonfotó több MB is lehet).
function shrink(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, MAX_IMG_SIDE / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Ezt a képet nem tudom megnyitni.")); };
    img.src = url;
  });
}

// Egyszerű megjelenítés: **félkövér**, felsorolás, címsor.
function Rich({ text }) {
  const bold = (s, k) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") && p.endsWith("**")
    ? <strong key={`${k}-${i}`}>{p.slice(2, -2)}</strong> : <span key={`${k}-${i}`}>{p}</span>));
  return (
    <div className="space-y-1.5">
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} className="h-1" />;
        if (/^#{1,4}\s/.test(t)) return <div key={i} className="font-bold mt-2">{bold(t.replace(/^#{1,4}\s/, ""), i)}</div>;
        if (/^[-*•]\s/.test(t)) return <div key={i} className="flex gap-2"><span className="text-[var(--yellow)]">•</span><span>{bold(t.slice(2), i)}</span></div>;
        return <p key={i}>{bold(t, i)}</p>;
      })}
    </div>
  );
}

export default function Chat({ state }) {
  const slip = useSlip();
  const [msgs, setMsgs] = useState(loadHistory);
  const [text, setText] = useState("");
  const [images, setImages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);
  const endRef = useRef(null);

  useEffect(() => { saveHistory(msgs); endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  const addFiles = async (files) => {
    setError(null);
    const room = MAX_ATTACH - images.length;
    for (const f of [...files].slice(0, Math.max(0, room))) {
      try {
        const url = await shrink(f);
        setImages((xs) => [...xs, url].slice(0, MAX_ATTACH));
      } catch (e) { setError(e.message); }
    }
    if (files.length > room) setError(`Egyszerre legfeljebb ${MAX_ATTACH} kép.`);
  };

  const send = async (override) => {
    const q = (override ?? text).trim();
    if ((!q && !images.length) || busy) return;
    const mine = { role: "user", text: q || "Mit látsz a képen?", images: override ? [] : images };
    const next = [...msgs, mine];
    setMsgs(next);
    setText("");
    setImages([]);
    setBusy(true);
    setError(null);
    try {
      const context = buildContext(state, slip, mine.text);
      const r = await axios.post("/api/chat", {
        context,
        messages: next.slice(-24).map(({ role, text: t, images: im }) => ({ role, text: t, images: im || [] })),
      }, { timeout: 120000 });
      setMsgs((xs) => [...xs, { role: "assistant", text: r.data.reply }]);
    } catch (e) {
      setError(e?.response?.data?.error || e?.response?.data?.detail || (e.code === "ECONNABORTED" ? "Túl sokáig tartott a válasz. Próbáld újra." : e.message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="chat">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">Kérdezz</h1>
          <p className="text-sm muted mt-1 max-w-2xl">Kérdezz a meccsekről, kérd a szelvényed véleményezését, vagy küldj képet (pl. egy TippmixPro-szelvényről). A szelvényedet és a meccsek adatait magától megkapja; hírekhez, sérültekhez nem fér hozzá.</p>
        </div>
        {msgs.length > 0 && (
          <button className="btn-ghost text-xs inline-flex items-center gap-1 shrink-0" onClick={() => { setMsgs([]); setError(null); }} data-testid="chat-clear">
            <Trash2 size={13} /> Új beszélgetés
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="chip" data-on={slip.legs.length > 0} disabled={!slip.legs.length || busy} onClick={() => send(REVIEW)} data-testid="chat-review"
          title={slip.legs.length ? "" : "Előbb rakj tippeket a szelvényre"}>
          Szelvényem véleményezése ({slip.legs.length})
        </button>
        {QUICK.map((q) => <button key={q} className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>)}
      </div>

      <div className="panel p-3 sm:p-4 space-y-3 min-h-[200px]" data-testid="chat-log">
        {!msgs.length && <p className="text-sm faint text-center py-10">Még nincs üzenet. Írj egy kérdést, vagy nyomd meg a fenti gombok egyikét.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed break-words ${m.role === "user"
              ? "bg-[var(--yellow)] text-[var(--on-yellow)]" : "bg-[var(--surface)] border border-[var(--line)]"}`}
            data-testid={`chat-msg-${m.role}`}>
              {m.images?.length > 0 && (
                <div className="flex gap-1.5 mb-2 flex-wrap">{m.images.map((u, k) => <img key={k} src={u} alt="" className="h-20 rounded-lg object-cover" />)}</div>
              )}
              {!m.images?.length && m.imgCount > 0 && <div className="text-xs opacity-70 mb-1">[{m.imgCount} kép]</div>}
              {m.role === "assistant" ? <Rich text={m.text} /> : <div className="whitespace-pre-wrap">{m.text}</div>}
            </div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-sm muted"><Loader2 size={16} className="animate-spin" /> Gondolkodik…</div>}
        {error && <div className="text-sm text-[var(--red)]" data-testid="chat-error">{error}</div>}
        <div ref={endRef} />
      </div>

      <div className="panel p-3 space-y-2">
        {images.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {images.map((u, i) => (
              <div key={i} className="relative">
                <img src={u} alt="" className="h-16 w-16 rounded-lg object-cover border border-[var(--line)]" />
                <button className="absolute -top-2 -right-2 bg-[var(--surface)] border border-[var(--line)] rounded-full p-0.5"
                  onClick={() => setImages((xs) => xs.filter((_, k) => k !== i))} aria-label="Kép törlése"><X size={12} /></button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <button className="btn-ghost shrink-0" onClick={() => fileRef.current?.click()} disabled={busy || images.length >= MAX_ATTACH}
            title="Kép csatolása" aria-label="Kép csatolása" data-testid="chat-attach"><ImagePlus size={18} /></button>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => { addFiles(e.target.files || []); e.target.value = ""; }} />
          <textarea className="field flex-1 min-h-[44px] max-h-40 resize-y" rows={2} placeholder="Kérdezz a meccsekről vagy a szelvényedről…"
            value={text} onChange={(e) => setText(e.target.value)} data-testid="chat-input"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && window.innerWidth >= 768) { e.preventDefault(); send(); } }} />
          <button className="btn-y shrink-0 inline-flex items-center gap-1.5" onClick={() => send()} disabled={busy || (!text.trim() && !images.length)}
            data-testid="chat-send">{busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}</button>
        </div>
        <p className="text-[11px] faint">A válasz modellbecslés, nem garancia. A Gemini napi kerete közös az AXIMBRA-oldallal.</p>
      </div>
    </section>
  );
}

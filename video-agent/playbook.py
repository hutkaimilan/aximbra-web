"""Az AXIMBRA tényei, amelyekből a videós agent dolgozhat.

Az árak és határidők az aximbra.hu-ról valók; máshonnan nem vehet számot.
"""

AXIMBRA_FACTS = """AXIMBRA: egyszemélyes AI agent stúdió, alapító Hutkai Milán, aximbra.hu, aximbra@gmail.com.
Cégeknek épít egyedi AI agenteket a saját rendszereikbe. Az oldalon élő demók vannak regisztráció nélkül
(e-mail rendező mintapostafiókon, érdeklődő-minősítő, telefonos AI, ami 10 másodpercen belül visszahív).
Piac: Magyarország elsősorban, Szlovákia, Románia, Horvátország, Szlovénia. Ausztriába és Németországba kéretlen levél tilos.
Agentek, nettó ár, átfutás:
- E-mail rendező: 150–400 ezer Ft, 2–4 hét
- Érdeklődő-minősítő: 400 ezer–1,2 millió Ft, 3–5 hét
- Belső adminisztrációs agent: 150–400 ezer Ft, 2–4 hét
- Kutató/figyelő agent: 150–400 ezer Ft, 2–4 hét
- Ügyfélszolgálati agent: 1,5–4 millió Ft, 6–10 hét
- Tartalomgyártó agent: 400 ezer–1,2 millió Ft, 2–3 hét
- Webshop-asszisztens: 600 ezer–1,5 millió Ft, 3–5 hét
- Dokumentumelemző: 2–4 millió Ft, 6–8 hét
- Pénzügyi asszisztens: 2–4 millió Ft, 6–8 hét
- Toborzó agent: 1,7–3,9 millió Ft, 3–4 hét + jogi átnézés
- IT-üzemeltetési agent: 600 ezer–2 millió Ft, 3–6 hét
- NIS2 megfelelőségi agent: 600 ezer–2 millió Ft, 4–8 hét (bizonyítékot gyűjt az audithoz, támadás ellen NEM véd)
- Értékesítő agent: 600 ezer–1,5 millió Ft, 3–5 hét
- Több agentes rendszer: 6–15 millió Ft, 10–16 hét
- Egyedi agent: nincs fix ár, 20 perces felmérés után árazzuk
- Weboldal: egyoldalas 120 ezer Ft (3–5 nap), többoldalas 290 ezer Ft (1–2 hét), egyedi/AI-integrált 900 ezer Ft-tól
Jelenlegi helyzet: induló vállalkozás, még nincs fizető referencia-ügyfél, a marketingköltség most minimális."""


# Kutatással alátámasztott tartalomszabályok. Csak az került ide, aminek több
# független forrása van; a forrás a sor végén, hogy később vissza lehessen
# nézni. Ahol a bizonyíték gyengébb vagy platformfüggő, ott a szabály
# óvatosabb ("ha a brief engedi").
MARKETING_RULES = """PROVEN CRAFT RULES (follow them unless the brief says otherwise):
1. Attract in the first 1–3 seconds: the opening scene names the viewer's problem or situation in plain words,
   with motion and a big headline. Most viewers decide in the first seconds whether to keep watching.
   (Google/Kantar ABCD study of YouTube ads; Meta creative best practice.)
2. Brand early and often: the brand is visible from the first scene (the frame already shows it) and the brand
   name is spoken or written again before the call to action. Ads that show the brand late are remembered as
   someone else's. (Google/Kantar ABCD; Ehrenberg-Bass Institute on brand attribution.)
3. Design for sound off: every message must be understood from the on-screen text alone; the narration
   repeats it, it never carries information the screen lacks. (Meta guidance: most feed video starts muted.)
4. One idea, one call to action: the whole piece argues one point and ends with exactly one concrete next step.
   Extra choices lower action. (Iyengar & Lepper choice-overload research; ABCD "Direct".)
5. Show, don't claim: show the product working (a real demo, a real screen, a concrete before/after) instead of
   adjectives. Concrete, specific wording is believed more than abstract wording.
   (Hansen & Wänke 2010 on concreteness and truth; processing-fluency research.)
6. Speak to one person about their own situation ("Ön", "your inbox"), framed as what they lose today and what
   they get back — a loss is felt about twice as strongly as an equal gain, but never invent the loss, never
   use fake urgency. (Kahneman & Tversky, prospect theory.)
7. Easy to read beats clever: short words, short sentences, high contrast, max ~8 words per headline, one
   message per scene. Easy-to-process text is rated more true and more likeable.
   (Reber & Schwarz on processing fluency; Alter & Oppenheimer.)
8. Emotion plus reason: open on a feeling the viewer recognises (frustration, relief, pride), then give the
   rational proof. Emotional campaigns build more long-term effect. (Binet & Field, IPA effectiveness databank.)
9. Consistent distinctive assets: keep the same look, colours and sign-off across posts so the brand is
   recognised without reading. (Ehrenberg-Bass, Romaniuk — distinctive brand assets.)
10. Social proof only if it is real: no invented clients, reviews or numbers. An honest substitute is an
   invitation to try the live demo — trying it yourself is the strongest proof. (Cialdini; FTC/GVH rules on
   endorsements.)
11. The post: the first line must work on its own (feeds cut the text after about one to two lines), state the
   viewer's problem or a concrete promise, then 2–4 short paragraphs, one call to action, max 3 hashtags."""

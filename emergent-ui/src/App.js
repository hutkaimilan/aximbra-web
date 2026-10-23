import { useCallback, useEffect, useState } from "react";
import { Activity, BookOpen, Moon, RefreshCw, Sun, Ticket, Wand2 } from "lucide-react";
import { Drawer, DrawerContent, DrawerTitle } from "./components/ui/drawer";
import Accuracy from "./components/Accuracy";
import Builder from "./components/Builder";
import MatchCard from "./components/MatchCard";
import SlipLog from "./components/SlipLog";
import SlipPanel from "./components/SlipPanel";
import TeamSheet from "./components/TeamSheet";
import { api, COMPS, dayLabel, errText, num } from "./lib/api";
import { SlipProvider, useSlip } from "./lib/slip";

const TABS = [{ key: "builder", name: "Szelvénykészítő", icon: Wand2 }, ...COMPS, { key: "accuracy", name: "Mennyire pontos?", icon: Activity }, { key: "log", name: "Napló", icon: BookOpen }];

function useTheme() {
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  return [dark, setDark];
}

function StatusBar({ state, error }) {
  if (error) return <div className="panel p-3 text-sm text-[var(--red)]" data-testid="status-error">A kínálat nem tölthető be: {error}</div>;
  if (!state) return null;
  const mins = Math.round(state.age / 60);
  return (
    <div className={`panel px-3 py-2.5 text-xs flex flex-wrap items-center gap-x-4 gap-y-1 ${state.stale ? "border-[var(--orange)]" : ""}`} data-testid="status-bar">
      <span className="inline-flex items-center gap-1.5 font-semibold">
        <span className={`w-2 h-2 rounded-full pulse-dot ${state.stale ? "bg-[var(--orange)]" : "bg-[var(--green)]"}`} />
        {state.stale ? "ELAVULT adat" : "Friss adat"} · {mins < 1 ? "most" : `${mins} perce`}
      </span>
      <span className="faint break-words min-w-0">{state.source}</span>
      <span className="faint">Modell: {state.model.status}; visszamérés: {state.model.backtest}</span>
      {state.notes.map((n) => <span key={n} className="text-[var(--orange)] w-full">{n}</span>)}
    </div>
  );
}

function CompetitionView({ comp, state, onTeam, version }) {
  const c = state?.competitions.find((x) => x.key === comp.key);
  const days = {};
  (c?.matches || []).forEach((m) => {
    const d = new Date(m.kickoff).toLocaleDateString("sv-SE", { timeZone: "Europe/Budapest" });
    (days[d] = days[d] || []).push(m);
  });
  return (
    <div className="space-y-6" data-testid={`comp-${comp.key}`}>
      <h1 className="text-2xl sm:text-3xl font-extrabold">{comp.name}</h1>
      <Builder fixedComp={comp.key} stateVersion={version} />
      {c?.error && <div className="panel p-3 text-sm text-[var(--orange)]">{c.error}</div>}
      {!c?.matches?.length && <div className="panel p-6 muted text-sm">Most nincs kiírt meccs a TippmixPro-n ebben a sorozatban.</div>}
      {Object.entries(days).map(([d, ms]) => (
        <div key={d}>
          <h2 className="text-base md:text-lg font-bold mb-3"><span className="capitalize">{dayLabel(d)}</span> <span className="faint text-sm font-medium">· {ms.length} meccs</span></h2>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">{ms.map((m, i) => <MatchCard key={m.id} m={m} onTeam={onTeam} idx={i} />)}</div>
        </div>
      ))}
    </div>
  );
}

function MobileBar({ onOpen }) {
  const { legs, check } = useSlip();
  return (
    <div className="fixed bottom-0 inset-x-0 z-40 lg:hidden p-3 bg-[color-mix(in_srgb,var(--surface)_92%,transparent)] backdrop-blur-lg border-t border-[var(--line)]">
      <button className="btn-y w-full flex items-center justify-between" onClick={onOpen} data-testid="mobile-slip-open">
        <span className="inline-flex items-center gap-2"><Ticket size={16} /> Szelvény ({legs.length})</span>
        <span className="mono">{check?.odds ? num(check.odds) : "–"}</span>
      </button>
    </div>
  );
}

function Shell() {
  const [dark, setDark] = useTheme();
  const [tab, setTab] = useState("builder");
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [version, setVersion] = useState(0);
  const [team, setTeam] = useState(null);
  const [drawer, setDrawer] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback((refresh) => {
    setLoading(true);
    api.state(refresh).then((s) => {
      setState(s);
      setError(null);
      if (refresh && s.refresh_accepted) setVersion((v) => v + 1);
      setNotice(refresh && !s.refresh_accepted ? "Kényszerített frissítés 30 másodpercenként legfeljebb egy; a gyorsítótárazott kínálatot látod." : null);
    })
      .catch((e) => setError(errText(e))).finally(() => setLoading(false));
  }, []);
  useEffect(() => load(false), [load]);

  const comp = COMPS.find((c) => c.key === tab);
  return (
    <div className="min-h-screen pb-24 lg:pb-8">
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-[color-mix(in_srgb,var(--bg)_85%,transparent)] border-b border-[var(--line)]">
        <div className="max-w-[1500px] mx-auto px-4 py-3 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[var(--yellow)] text-[var(--on-yellow)] grid place-items-center font-display font-extrabold shrink-0">Sz</div>
          <div className="min-w-0 flex-1">
            <div className="font-display font-bold leading-tight truncate">Szelvénymodell</div>
            <div className="text-[11px] faint truncate">TippmixPro-szorzók · Dixon–Coles · Monte Carlo</div>
          </div>
          <button className="btn-ghost" onClick={() => load(true)} disabled={loading} title="Frissítés (30 mp-enként egy)" data-testid="refresh-button">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
          <button className="btn-ghost" onClick={() => setDark(!dark)} title="Téma" data-testid="theme-toggle">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
        <nav className="max-w-[1500px] mx-auto px-4 pb-3">
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar" data-testid="main-tabs">
            {TABS.map((t) => (
              <button key={t.key} className="chip" data-on={tab === t.key} onClick={() => setTab(t.key)} data-testid={`tab-${t.key}`}>
                {t.icon && <t.icon size={14} />} {t.name}
              </button>
            ))}
          </div>
        </nav>
      </header>
      <div className="max-w-[1500px] mx-auto px-4 py-5 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <main className="lg:col-span-8 xl:col-span-9 space-y-5 min-w-0">
          <StatusBar state={state} error={error} />
          {notice && <div className="text-xs text-[var(--orange)] px-1" data-testid="refresh-notice">{notice}</div>}
          {tab === "builder" && (
            <div className="space-y-4">
              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight">Szelvénykészítő</h1>
              <p className="text-sm muted max-w-2xl">Kész, TippmixPro-n köthető szelvények a legnagyobb becsült esélyű tippekből. Minden szelvényt a TippmixPro maga is ellenőriz (kötéstiltás, Fogadásépítő-szorzó).</p>
              <Builder stateVersion={version} />
            </div>
          )}
          {comp && <CompetitionView comp={comp} state={state} onTeam={setTeam} version={version} />}
          {tab === "accuracy" && <Accuracy />}
          {tab === "log" && <SlipLog />}
        </main>
        <aside className="hidden lg:block lg:col-span-4 xl:col-span-3 sticky top-32 max-h-[calc(100vh-9rem)] overflow-y-auto no-scrollbar">
          <SlipPanel />
        </aside>
      </div>
      <MobileBar onOpen={() => setDrawer(true)} />
      <Drawer open={drawer} onOpenChange={setDrawer}>
        <DrawerContent className="bg-[var(--bg)] border-[var(--line)] max-h-[90vh]">
          <DrawerTitle className="sr-only">Szelvény</DrawerTitle>
          <div className="overflow-y-auto p-3" data-testid="mobile-slip-drawer"><SlipPanel /></div>
        </DrawerContent>
      </Drawer>
      <TeamSheet teamId={team} onClose={() => setTeam(null)} />
    </div>
  );
}

export default function App() {
  return (
    <SlipProvider>
      <Shell />
    </SlipProvider>
  );
}

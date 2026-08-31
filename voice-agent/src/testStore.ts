/**
 * Tesztfutasok tarolasa.
 *
 * Egy futas = egy JSON fajl a volume-on. Adatbazis helyett fajlok: par szaz
 * futasnal ez bven eleg, es nincs se sema-migracio, se kulon szolgaltatas.
 *
 * A fajlirasok atomosak (ideiglenes fajl + rename), hogy egy deploy kozbeni
 * SIGTERM ne hagyjon felig irt JSON-t a lemezen.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export type RunStatus = 'running' | 'done' | 'failed';

export interface RunTurn {
  /** 'tester' = a mi teszt-agentunk, 'target' = a tesztelt agent. */
  who: 'tester' | 'target';
  text: string;
  /** ms a futas kezdetetol. */
  atMs: number;
}

export interface TestRun {
  id: string;
  createdAt: string;
  status: RunStatus;
  /** Mit kellett a teszt-agentnek elerni. */
  scenario: string;
  target: string;
  callSid: string | null;
  recordingSid: string | null;
  durationSec: number | null;
  turns: RunTurn[];
  /** Hiba szovege, ha a futas elszallt. */
  error: string | null;
}

function runsDir(): string {
  return process.env['TEST_RUNS_DIR']?.trim() || '/data/test-runs';
}

function runPath(id: string): string {
  return path.join(runsDir(), `${id}.json`);
}

/** Csak a sajat magunk altal generalt id-ket fogadjuk el utvonalban. */
export function isValidRunId(id: string): boolean {
  return /^[0-9a-f]{16}$/.test(id);
}

export function newRunId(): string {
  return crypto.randomBytes(8).toString('hex');
}

async function writeAtomic(file: string, data: string): Promise<void> {
  const tmp = `${file}.${crypto.randomBytes(4).toString('hex')}.tmp`;
  await fs.writeFile(tmp, data, 'utf8');
  await fs.rename(tmp, file);
}

export async function createRun(scenario: string, target: string): Promise<TestRun> {
  await fs.mkdir(runsDir(), { recursive: true });

  const run: TestRun = {
    id: newRunId(),
    createdAt: new Date().toISOString(),
    status: 'running',
    scenario,
    target,
    callSid: null,
    recordingSid: null,
    durationSec: null,
    turns: [],
    error: null,
  };

  await writeAtomic(runPath(run.id), JSON.stringify(run, null, 2));
  return run;
}

export async function loadRun(id: string): Promise<TestRun | null> {
  if (!isValidRunId(id)) return null;
  try {
    const raw = await fs.readFile(runPath(id), 'utf8');
    return JSON.parse(raw) as TestRun;
  } catch {
    return null;
  }
}

/**
 * Reszleges frissites. Ujraolvassa a lemezrol, hogy ne irjunk felul
 * kozben erkezett valtozast (pl. a recording callback a beszelgetes alatt).
 */
export async function updateRun(
  id: string,
  patch: Partial<Omit<TestRun, 'id'>>,
): Promise<TestRun | null> {
  const current = await loadRun(id);
  if (!current) return null;

  const merged: TestRun = { ...current, ...patch };
  await writeAtomic(runPath(id), JSON.stringify(merged, null, 2));
  return merged;
}

export async function appendTurn(id: string, turn: RunTurn): Promise<void> {
  const current = await loadRun(id);
  if (!current) return;
  current.turns.push(turn);
  await writeAtomic(runPath(id), JSON.stringify(current, null, 2));
}

/** Legujabb elol, legfeljebb `limit` darab. */
export async function listRuns(limit = 50): Promise<TestRun[]> {
  try {
    const files = await fs.readdir(runsDir());
    const ids = files
      .filter((f) => f.endsWith('.json'))
      .map((f) => f.replace(/\.json$/, ''))
      .filter(isValidRunId);

    const runs: TestRun[] = [];
    for (const id of ids) {
      const run = await loadRun(id);
      if (run) runs.push(run);
    }

    runs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    return runs.slice(0, limit);
  } catch {
    return [];
  }
}

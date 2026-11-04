import { useEffect, useState } from 'react';
import type { CaseDetail, DemoData } from './types';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`./data/${path}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export async function loadDemo(): Promise<DemoData> {
  const [manifest, events, cases, learning, rules] = await Promise.all([
    getJson<DemoData['manifest']>('manifest.json'),
    getJson<DemoData['events']>('events.json'),
    getJson<DemoData['cases']>('cases.json'),
    getJson<DemoData['learning']>('learning.json'),
    getJson<DemoData['rules']>('rules.json'),
  ]);
  return {
    manifest,
    events: [...events].sort((a, b) => a.seq - b.seq),
    cases: [...cases].sort((a, b) => a.first_seq - b.first_seq),
    learning: { ...learning, curve: learning.curve ?? [] },
    rules,
  };
}

// Case files are fetched once, a few at a time, so a long list of rulings does not flood a slow connection.
const cache = new Map<string, Promise<CaseDetail>>();
const resolved = new Map<string, CaseDetail>();
const waiting: (() => void)[] = [];
let active = 0;

function pump() {
  while (active < 6 && waiting.length) {
    active += 1;
    waiting.shift()!();
  }
}

export function loadCase(id: string): Promise<CaseDetail> {
  const known = cache.get(id);
  if (known) return known;
  const p = new Promise<CaseDetail>((resolve, reject) => {
    waiting.push(() => {
      getJson<CaseDetail>(`cases/${encodeURIComponent(id)}.json`)
        .then((d) => {
          resolved.set(id, d);
          resolve(d);
        })
        .catch((e) => {
          cache.delete(id);
          reject(e);
        })
        .finally(() => {
          active -= 1;
          pump();
        });
    });
    pump();
  });
  cache.set(id, p);
  return p;
}

export function useCase(id: string | null): { data: CaseDetail | null; error: string | null } {
  const [state, setState] = useState<{ id: string | null; data: CaseDetail | null; error: string | null }>({
    id,
    data: id ? resolved.get(id) ?? null : null,
    error: null,
  });
  useEffect(() => {
    let live = true;
    if (!id) return;
    const done = resolved.get(id);
    if (done) {
      setState({ id, data: done, error: null });
      return;
    }
    setState({ id, data: null, error: null });
    loadCase(id)
      .then((data) => live && setState({ id, data, error: null }))
      .catch((e: Error) => live && setState({ id, data: null, error: e.message }));
    return () => {
      live = false;
    };
  }, [id]);
  if (state.id !== id) return { data: id ? resolved.get(id) ?? null : null, error: null };
  return { data: state.data, error: state.error };
}

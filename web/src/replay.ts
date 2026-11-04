import { createContext, useContext, useSyncExternalStore } from 'react';
import type { CaseRow, DemoData, ReplayEvent } from './types';

// How long each event holds at speed 1, in milliseconds. The moments that teach something hold longest.
const HOLD: Record<string, number> = {
  'case.submitted': 1000,
  'checks.done': 450,
  'evidence.linked': 500,
  'evidence.judged': 500,
  'requirements.checked': 450,
  'hazards.screened': 450,
  'trees.evaluated': 500,
  'risk.computed': 650,
  'decision.made': 1300,
  'officer.ruled': 1300,
  'correction.made': 3000,
  'weights.updated': 900,
  'thresholds.rechosen': 3000,
  'permit.issued': 500,
  'change.released': 3000,
};
const LOOP_PAUSE_MS = 5000;

export const SPEEDS = [1, 2, 4, 8, 16];

export interface ReplayOptions {
  video: boolean;
  speed: number;
}

export interface ReplayState {
  index: number;
  playing: boolean;
  speed: number;
}

export interface Timeline {
  events: ReplayEvent[];
  cases: CaseRow[];
  caseById: Map<string, CaseRow>;
  caseEvents: Map<string, number[]>;
  submittedAt: Int32Array;
  learningAt: Int32Array;
  correctionIndexes: number[];
  correctionSeq: Map<string, number>;
  updateIndexes: number[];
  rechosenIndexes: number[];
  rechosenCurve: Set<number>;
  lastIndex: number;
}

export function buildTimeline(data: DemoData): Timeline {
  const { events, cases, learning } = data;
  const n = events.length;
  const curveMax = Math.max(0, learning.curve.length - 1);
  const caseEvents = new Map<string, number[]>();
  const firstSeqs = cases.map((c) => c.first_seq);
  const submittedAt = new Int32Array(n);
  const learningAt = new Int32Array(n);
  const correctionIndexes: number[] = [];
  const correctionSeq = new Map<string, number>();
  const updateIndexes: number[] = [];
  const rechosenIndexes: number[] = [];
  const rechosenCurve = new Set<number>();
  let submitted = 0;
  let current = 0;
  let curvePtr = 0;
  events.forEach((ev, i) => {
    if (ev.case_id) {
      const list = caseEvents.get(ev.case_id);
      if (list) list.push(i);
      else caseEvents.set(ev.case_id, [i]);
    }
    while (submitted < firstSeqs.length && firstSeqs[submitted] <= ev.seq) submitted += 1;
    submittedAt[i] = submitted;
    if (typeof ev.learning_index === 'number') current = Math.max(current, Math.min(curveMax, ev.learning_index));
    while (curvePtr + 1 <= curveMax && learning.curve[curvePtr + 1].seq <= ev.seq) curvePtr += 1;
    current = Math.max(current, curvePtr);
    if (i > 0 && current !== learningAt[i - 1]) updateIndexes.push(i);
    learningAt[i] = current;
    if (ev.type === 'correction.made') {
      correctionIndexes.push(i);
      if (ev.case_id) correctionSeq.set(ev.case_id, ev.seq);
    }
    if (ev.type === 'thresholds.rechosen') {
      rechosenIndexes.push(i);
      if (typeof ev.learning_index === 'number') rechosenCurve.add(Math.min(curveMax, ev.learning_index));
    }
  });
  learning.curve.forEach((p, i) => {
    const prev = learning.curve[i - 1];
    if (prev && (prev.t_low !== p.t_low || prev.t_high !== p.t_high)) rechosenCurve.add(i);
  });
  return {
    events,
    cases,
    caseById: new Map(cases.map((c) => [c.case_id, c])),
    caseEvents,
    submittedAt,
    learningAt,
    correctionIndexes,
    correctionSeq,
    updateIndexes,
    rechosenIndexes,
    rechosenCurve,
    lastIndex: n - 1,
  };
}

export class Replay {
  state: ReplayState;
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private timeline: Timeline, private options: ReplayOptions) {
    this.state = { index: 0, playing: timeline.lastIndex > 0, speed: options.speed };
  }

  start() {
    this.schedule();
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  private set(next: Partial<ReplayState>) {
    this.state = { ...this.state, ...next };
    this.listeners.forEach((fn) => fn());
  }

  private clear() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule() {
    this.clear();
    if (!this.state.playing) return;
    const { index, speed } = this.state;
    const { events, lastIndex } = this.timeline;
    if (index >= lastIndex) {
      if (this.options.video) this.timer = setTimeout(() => this.seek(0), LOOP_PAUSE_MS);
      else this.set({ playing: false });
      return;
    }
    const hold = HOLD[events[index]?.type] ?? 650;
    this.timer = setTimeout(() => {
      this.set({ index: this.state.index + 1 });
      this.schedule();
    }, hold / speed);
  }

  play = () => {
    if (this.state.index >= this.timeline.lastIndex) this.state = { ...this.state, index: 0 };
    this.set({ playing: true });
    this.schedule();
  };

  pause = () => {
    this.set({ playing: false });
    this.clear();
  };

  toggle = () => (this.state.playing ? this.pause() : this.play());

  setSpeed = (speed: number) => {
    this.set({ speed });
    this.schedule();
  };

  seek = (index: number) => {
    this.set({ index: Math.max(0, Math.min(this.timeline.lastIndex, index)) });
    this.schedule();
  };

  restart = () => {
    this.state = { ...this.state, playing: true };
    this.seek(0);
  };

  jumpToEnd = () => {
    this.state = { ...this.state, playing: false };
    this.seek(this.timeline.lastIndex);
  };

  /** Moves to the next event where the cards and plots change. */
  nextUpdate = () => {
    const next = this.timeline.updateIndexes.find((i) => i > this.state.index);
    if (next !== undefined) this.seek(next);
  };

  stop() {
    this.clear();
  }
}

export interface ReplayContextValue {
  data: DemoData;
  timeline: Timeline;
  replay: Replay;
  video: boolean;
}

export const ReplayContext = createContext<ReplayContextValue | null>(null);

export function useDemo(): ReplayContextValue {
  const ctx = useContext(ReplayContext);
  if (!ctx) throw new Error('useDemo needs a ReplayContext');
  return ctx;
}

/** Subscribes to a value derived from the replay. The component re-renders only when that value changes. */
export function useReplayValue<T extends string | number | boolean | null>(select: (state: ReplayState, timeline: Timeline) => T): T {
  const { replay, timeline } = useDemo();
  return useSyncExternalStore(replay.subscribe, () => select(replay.state, timeline));
}

export const useReplayIndex = () => useReplayValue((s) => s.index);
export const useLearningIndex = () => useReplayValue((s, t) => t.learningAt[s.index] ?? 0);
export const useAtEnd = () => useReplayValue((s, t) => s.index >= t.lastIndex);
export const useSubmittedCount = () => useReplayValue((s, t) => t.submittedAt[s.index] ?? 0);

/** How many of this case's events the replay has reached. */
export function reachedEvents(t: Timeline, caseId: string, index: number): number {
  const list = t.caseEvents.get(caseId);
  if (!list) return 0;
  let n = 0;
  while (n < list.length && list[n] <= index) n += 1;
  return n;
}

export const hasReachedType = (t: Timeline, caseId: string, index: number, type: string) =>
  (t.caseEvents.get(caseId) ?? []).some((i) => i <= index && t.events[i].type === type);

import { useMemo, useState } from 'react';
import type { WeightChange } from '../types';
import { describeWhen, treeName } from '../words';
import { LevelBar } from './LevelBar';

const LEVEL_WORDS: Record<string, string[]> = {
  likelihood: ['rare', 'possible', 'likely'],
  severity: ['minor', 'serious', 'critical'],
};

function levelNames(treeId: string) {
  const scale = treeId.split('.').pop() ?? '';
  return LEVEL_WORDS[scale] ?? ['level 1', 'level 2', 'level 3'];
}

function deltaWord(before: number, after: number) {
  const d = Math.round((after - before) * 10000) / 100;
  if (d === 0) return 'no change';
  return `${d > 0 ? '+' : ''}${d.toFixed(2)} points`;
}

const moved = (c: WeightChange) => c.before.reduce((s, p, i) => s + Math.abs(p - (c.after[i] ?? p)), 0);

/** Exactly which leaves moved and by how much, largest move first. */
export function WeightChanges({ changes, limit = 4 }: { changes: WeightChange[]; limit?: number }) {
  const [all, setAll] = useState(false);
  const sorted = useMemo(() => [...changes].sort((a, b) => moved(b) - moved(a)), [changes]);
  const shown = all ? sorted : sorted.slice(0, limit);
  return (
    <>
    <ul className="d-changes">
      {shown.map((c, i) => {
        const names = levelNames(c.tree_id);
        return (
          <li key={i} className="d-change">
            <div className="d-change__head">
              <strong>{treeName(c.tree_id)}</strong>
              <span className="d-muted">{describeWhen(c.leaf)}</span>
            </div>
            <div className="d-change__bars">
              <span className="d-change__tag">Before</span>
              <LevelBar levels={c.before} names={names} />
              <span className="d-mono d-change__n">count {c.count_before.toFixed(2)}</span>
              <span className="d-change__tag">After</span>
              <LevelBar levels={c.after} names={names} />
              <span className="d-mono d-change__n">count {c.count_after.toFixed(2)}</span>
            </div>
            <ul className="d-change__deltas">
              {names.map((n, j) => (
                <li key={n}>
                  <span>{n}</span>{' '}
                  <span className="d-mono">{(c.before[j] * 100).toFixed(1)}% to {(c.after[j] * 100).toFixed(1)}%</span>{' '}
                  <span className="d-muted">{deltaWord(c.before[j], c.after[j])}</span>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
    {sorted.length > limit && (
      <button type="button" className="d-textbtn" onClick={() => setAll(!all)}>
        {all ? `Show only the largest ${limit}` : `Show all ${sorted.length} leaves that moved`}
      </button>
    )}
    </>
  );
}

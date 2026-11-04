import type { ReactNode } from 'react';

type TagKind = 'synthetic' | 'simulated' | 'stored' | 'corrected' | 'neutral';

const TITLES: Partial<Record<TagKind, string>> = {
  synthetic: 'Written by a script. No real organiser or event is involved.',
  simulated: 'Produced by a stand-in, not by a real person or a live read.',
  stored: 'Recorded ahead of time and replayed here, not worked out now.',
};

/** A small local label. StatusBadge keeps to its eight status words, so these words live here. */
export function Tag({ kind = 'neutral', children }: { kind?: TagKind; children?: ReactNode }) {
  return (
    <span className={`d-tag d-tag--${kind}`} title={TITLES[kind]}>
      {children ?? kind[0].toUpperCase() + kind.slice(1)}
    </span>
  );
}

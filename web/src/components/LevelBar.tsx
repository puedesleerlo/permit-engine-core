/** One leaf's split across three ordered levels, such as rare, possible and likely. */
export function LevelBar({ levels, names, compact }: { levels: number[]; names?: string[]; compact?: boolean }) {
  const label = levels.map((p, i) => `${Math.round(p * 100)}% ${names?.[i] ?? `level ${i + 1}`}`).join(', ');
  return (
    <span className={`d-levelbar${compact ? ' d-levelbar--compact' : ''}`} role="img" aria-label={label}>
      {levels.map((p, i) => (p > 0 ? <i key={i} className={`d-level-${i}`} style={{ flexGrow: p }} /> : null))}
    </span>
  );
}

export function LevelLegend({ names, anchors }: { names: string[]; anchors?: number[] }) {
  return (
    <span className="d-legend">
      {names.map((n, i) => (
        <span key={n} className="d-legend__item">
          <i className={`d-swatch d-level-${i}`} />
          {n}
          {anchors?.[i] !== undefined && <span className="d-mono d-muted"> {anchors[i]}</span>}
        </span>
      ))}
    </span>
  );
}

export const levelNumbers = (levels: number[]) => levels.map((p) => Math.round(p * 100)).join(' / ');

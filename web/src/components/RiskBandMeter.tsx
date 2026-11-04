import { num } from '../words';
import { useWidth } from './useWidth';

interface Props {
  risk: number | null;
  tLow: number | null;
  tHigh: number | null;
  highestSeverity: number | null;
  ceiling: number | null;
}

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

function Marker({ x, y, h, label, width }: { x: number; y: number; h: number; label: string; width: number }) {
  const textW = label.length * 7.2;
  const anchorX = clamp(x, textW / 2, width - textW / 2);
  return (
    <g className="d-meter__marker">
      <line x1={x} x2={x} y1={y - 4} y2={y + h + 4} />
      <text x={anchorX} y={y - 9} textAnchor="middle">{label}</text>
    </g>
  );
}

function Tick({ x, y, label, width }: { x: number; y: number; label: string; width: number }) {
  const textW = label.length * 6.6;
  const anchorX = clamp(x, textW / 2, width - textW / 2);
  return (
    <g className="d-meter__tick">
      <line x1={x} x2={x} y1={y - 22} y2={y - 2} />
      <text x={anchorX} y={y + 12} textAnchor="middle">{label}</text>
    </g>
  );
}

/** Risk against its two thresholds, and the worst single severity against the ceiling. */
export function RiskBandMeter({ risk, tLow, tHigh, highestSeverity, ceiling }: Props) {
  const [ref, measured] = useWidth<HTMLDivElement>(420);
  const width = Math.max(260, measured);
  const hasRisk = risk !== null && tLow !== null && tHigh !== null;
  const hasSeverity = highestSeverity !== null && ceiling !== null;
  const rowH = 74;
  const height = (hasRisk ? rowH : 0) + (hasSeverity ? rowH : 0) + 4;

  const riskMax = hasRisk ? Math.max(0.5, tHigh! * 1.6, risk! * 1.15) : 1;
  const xR = (v: number) => (v / riskMax) * width;
  const xS = (v: number) => clamp(v, 0, 1) * width;
  const trackH = 16;
  const gap = 2;
  const y1 = 26;
  const y2 = hasRisk ? y1 + rowH : y1;

  const lowHighTooClose = hasRisk && xR(tHigh!) - xR(tLow!) < 74;

  return (
    <div ref={ref} className="d-meter">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Risk ${num(risk)}, low threshold ${num(tLow)}, high threshold ${num(tHigh)}. Highest severity ${num(highestSeverity)}, ceiling ${num(ceiling)}.`}>
        {hasRisk && (
          <g>
            <rect x={0} y={y1} width={Math.max(0, xR(tLow!) - gap / 2)} height={trackH} rx={3} className="d-band d-band--low" />
            <rect x={xR(tLow!) + gap / 2} y={y1} width={Math.max(0, xR(tHigh!) - xR(tLow!) - gap)} height={trackH} className="d-band d-band--mid" />
            <rect x={xR(tHigh!) + gap / 2} y={y1} width={Math.max(0, width - xR(tHigh!) - gap / 2)} height={trackH} rx={3} className="d-band d-band--high" />
            <Tick x={xR(tLow!)} y={y1 + trackH + 6} label={lowHighTooClose ? num(tLow, 2) : `t_low ${num(tLow, 2)}`} width={width} />
            <Tick x={xR(tHigh!)} y={y1 + trackH + 6} label={lowHighTooClose ? num(tHigh, 2) : `t_high ${num(tHigh, 2)}`} width={width} />
            <Marker x={xR(risk!)} y={y1} h={trackH} label={`Risk ${num(risk)}`} width={width} />
          </g>
        )}
        {hasSeverity && (
          <g>
            <rect x={0} y={y2} width={xS(ceiling!) - gap / 2} height={trackH} rx={3} className="d-band d-band--plain" />
            <rect x={xS(ceiling!) + gap / 2} y={y2} width={Math.max(0, width - xS(ceiling!) - gap / 2)} height={trackH} rx={3} className="d-band d-band--high" />
            <Tick x={xS(ceiling!)} y={y2 + trackH + 6} label={`ceiling ${num(ceiling, 2)}`} width={width} />
            <Marker x={xS(highestSeverity!)} y={y2} h={trackH} label={`Highest severity ${num(highestSeverity, 2)}`} width={width} />
          </g>
        )}
      </svg>
    </div>
  );
}

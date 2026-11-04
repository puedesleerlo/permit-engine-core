import { useMemo, useRef, useState } from 'react';
import { useWidth } from './useWidth';

export interface PlotSeries {
  key: string;
  label: string;
  tone: 'main' | 'second';
  values: number[];
  format: (v: number) => string;
}

interface Props {
  xs: number[];
  series: PlotSeries[];
  reached: number;
  markers: Set<number>;
  yDomain: [number, number];
  yTicks: number[];
  yFormat: (v: number) => string;
  height?: number;
  label: string;
  compact?: boolean;
}

/** A line plot over corrections. The axes hold still for the whole run, so the line grows as the replay reaches each point. */
export function LearningPlot({ xs, series, reached, markers, yDomain, yTicks, yFormat, height = 190, label, compact }: Props) {
  const [ref, measured] = useWidth<HTMLDivElement>(420);
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const width = Math.max(120, measured);
  const m = compact ? { left: 36, right: 42, top: 12, bottom: 24 } : { left: 38, right: 54, top: 14, bottom: 30 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;
  const xMax = Math.max(1, ...xs);
  const X = (c: number) => m.left + (c / xMax) * innerW;
  const Y = (v: number) => m.top + (1 - (v - yDomain[0]) / (yDomain[1] - yDomain[0])) * innerH;
  const last = Math.min(reached, xs.length - 1);

  const paths = useMemo(() => series.map((s) => {
    let d = '';
    for (let i = 0; i <= last; i += 1) d += `${i === 0 ? 'M' : 'L'} ${X(xs[i]).toFixed(1)} ${Y(s.values[i]).toFixed(1)} `;
    return { key: s.key, d };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [series, last, width, height]);

  const xTicks = useMemo(() => {
    const room = Math.max(2, Math.floor(innerW / 30));
    const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500].find((s) => xMax / s <= room) ?? 1000;
    const out: number[] = [];
    for (let v = 0; v <= xMax; v += step) out.push(v);
    return out;
  }, [xMax, innerW]);

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box || last < 0) return;
    const px = e.clientX - box.left;
    let best = 0;
    let bestD = Infinity;
    for (let i = 0; i <= last; i += 1) {
      const dist = Math.abs(X(xs[i]) - px);
      if (dist <= bestD) { bestD = dist; best = i; }
    }
    setHover(best);
  };

  const hx = hover !== null && hover <= last ? X(xs[hover]) : null;
  const summary = `${label}. ${series.map((s) => `${s.label} is ${s.format(s.values[Math.max(0, last)])}`).join(', ')} after ${xs[Math.max(0, last)]} officer reviews.`;

  return (
    <div ref={ref} className="d-plot">
      <svg ref={svgRef} width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={m.left} x2={width - m.right} y1={Y(v)} y2={Y(v)} className="d-plot__grid" />
            <text x={m.left - 6} y={Y(v) + 4} textAnchor="end" className="d-plot__axis">{yFormat(v)}</text>
          </g>
        ))}
        {xTicks.map((v) => (
          <text key={v} x={X(v)} y={height - m.bottom + 16} textAnchor="middle" className="d-plot__axis">{v}</text>
        ))}
        {[...markers].filter((i) => i <= last).map((i) => (
          <g key={i} className="d-plot__marker">
            <path d={`M ${X(xs[i]) - 4} ${m.top - 6} h 8 l -4 6 z`} />
          </g>
        ))}
        {paths.map((p, i) => <path key={p.key} d={p.d} className={`d-plot__line d-plot__line--${series[i].tone}`} />)}
        {last >= 0 && series.map((s) => {
          const x = X(xs[last]);
          const y = Y(s.values[last]);
          return (
            <g key={s.key}>
              <circle cx={x} cy={y} r={4} className={`d-plot__dot d-plot__dot--${s.tone}`} />
              <text x={x + 8} y={y + 4} className="d-plot__value">{s.format(s.values[last])}</text>
            </g>
          );
        })}
        {hx !== null && <line x1={hx} x2={hx} y1={m.top} y2={m.top + innerH} className="d-plot__cross" />}
        <rect x={m.left - 6} y={m.top - 6} width={innerW + 12} height={innerH + 12} fill="transparent" />
      </svg>
      {hover !== null && hx !== null && (
        <div className="d-plot__tip" style={{ left: Math.max(0, Math.min(hx + 10, width - 180)), top: 8 }}>
          {series.map((s) => (
            <div key={s.key}><strong>{s.format(s.values[hover])}</strong> <span>{s.label}</span></div>
          ))}
          <div className="d-muted">After {xs[hover]} officer reviews{markers.has(hover) ? ', thresholds re-chosen' : ''}</div>
        </div>
      )}
    </div>
  );
}

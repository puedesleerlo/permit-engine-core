import { memo, useMemo, useState } from 'react';
import { Button, Icon, SectionHeading, StatCallout, StatusBadge } from '@permit-engine/ui';
import { LearningPlot, type PlotSeries } from '../components/LearningPlot';
import { RouteBadge } from '../components/RouteBadge';
import { Tag } from '../components/Tag';
import { hasReachedType, reachedEvents, useDemo, useLearningIndex, useReplayIndex, useReplayValue, useSubmittedCount, useAtEnd } from '../replay';
import type { CaseRow, ReplayEvent } from '../types';
import { EVENT_STAGE, PIPELINE, pct, pipelineStep, reasonShort, simClock } from '../words';

// Nearly every case has a weights.updated event, so it stays quiet. These are the moments that stand out.
const LEARNING_MOMENTS = new Set(['correction.made', 'thresholds.rechosen', 'change.released']);
const OFFICER_MOMENTS = new Set(['officer.ruled', 'correction.made']);

export function useCurrentCards() {
  const { data } = useDemo();
  const li = useLearningIndex();
  const atEnd = useAtEnd();
  const { curve, cards } = data.learning;
  const point = curve[li] ?? null;
  const start = curve[0] ?? null;
  const final = atEnd ? cards?.final ?? null : null;
  return {
    point,
    li,
    first: {
      rightLevel: cards?.first?.right_level ?? start?.right_level ?? null,
      decided: cards?.first?.decided_without_officer ?? start?.decided_without_officer ?? null,
      precision: cards?.first?.precision ?? start?.precision ?? null,
    },
    rightLevel: final?.right_level ?? point?.right_level ?? null,
    decided: final?.decided_without_officer ?? point?.decided_without_officer ?? null,
    precision: final?.precision ?? point?.precision ?? null,
  };
}

export const RIGHT_LEVEL_MEANS = "How often a tree's most likely level matches the level the experts gave.";
export const STEADY_NOTE = 'These stay near flat. About a third of cases can never be automatic, and thresholds hold precision near its target. The point is that the system learned without losing safety.';

/** A domain that holds still for the whole run and still shows the rise. */
export function rightLevelDomain(curve: { right_level?: number | null }[]): [number, number] {
  const values = curve.map((p) => p.right_level).filter((v): v is number => typeof v === 'number');
  const low = values.length ? Math.min(...values) : 0.5;
  return [Math.min(0.5, Math.floor((low - 0.02) * 20) / 20), 1];
}

function Pipeline({ step, compact }: { step: number; compact?: boolean }) {
  return (
    <ol className={`d-pipe${compact ? ' d-pipe--compact' : ''}`} aria-label={step >= 0 ? `Step ${step + 1} of ${PIPELINE.length}: ${PIPELINE[step].label}` : undefined}>
      {PIPELINE.map((p, i) => (
        <li key={p.id} className={i < step ? 'is-done' : i === step ? 'is-now' : undefined} aria-hidden>
          <i />
          {!compact && <span>{p.label}</span>}
        </li>
      ))}
    </ol>
  );
}

function NowStrip() {
  const { timeline, data } = useDemo();
  const index = useReplayIndex();
  const ev = timeline.events[index];
  if (!ev) return null;
  const row = ev.case_id ? timeline.caseById.get(ev.case_id) : null;
  const moment = LEARNING_MOMENTS.has(ev.type);
  const step = pipelineStep(ev.type);
  const li = timeline.learningAt[index] ?? 0;
  const { curve } = data.learning;
  const before = curve[li - 1];
  const after = curve[li];
  const moved = li !== (timeline.learningAt[index - 1] ?? li) && before && after;
  return (
    <section className={`d-now${moment ? ' is-moment' : ''}`} aria-label="What is happening now">
      <div className="d-now__text">
        {row && <a className="d-now__open" href={`#/case/${encodeURIComponent(row.case_id)}`}>{row.title}<Icon name="arrow-right" size={16} /></a>}
        <p className="d-now__summary">{ev.summary}</p>
        {moved && (
          <p className="d-now__moved">
            Right risk level: {pct(before.right_level)} to {pct(after.right_level)}. Decided without an officer: {pct(after.decided_without_officer)}. Precision: {pct(after.precision)}.
          </p>
        )}
      </div>
      {moment ? (
        <p className="d-now__stage"><Tag kind={ev.type === 'correction.made' ? 'simulated' : 'neutral'}>{EVENT_STAGE[ev.type] ?? ev.type}</Tag></p>
      ) : (
        <Pipeline step={step} />
      )}
    </section>
  );
}

export function changeTrend(rise: number, from?: number | null) {
  return {
    value: rise === 0 ? 'No change yet' : `${rise > 0 ? '+' : ''}${rise} points`,
    direction: rise > 0 ? 'up' as const : rise < 0 ? 'down' as const : 'flat' as const,
    label: from !== null && from !== undefined ? `from ${pct(from)}` : undefined,
  };
}

function Cards() {
  const { rightLevel, decided, precision, first, point } = useCurrentCards();
  const rise = rightLevel !== null && first.rightLevel !== null ? Math.round((rightLevel - first.rightLevel) * 100) : 0;
  return (
    <>
      <article className="d-card d-card--metric d-card--lead">
        <StatCallout value={pct(rightLevel)} label={<strong>Right risk level</strong>} trend={changeTrend(rise, first.rightLevel)} />
        <p className="d-small">{RIGHT_LEVEL_MEANS}</p>
        <p className="d-caption">After {point?.corrections ?? 0} officer reviews.</p>
      </article>
      <article className="d-card d-card--metric d-card--steady">
        <div className="d-steady">
          <StatCallout value={pct(decided)} label={<strong>Decided without an officer</strong>} />
          <StatCallout value={pct(precision)} label={<><strong>Precision</strong>: approvals not labelled risky</>} />
        </div>
        <p className="d-caption">{STEADY_NOTE}</p>
      </article>
    </>
  );
}

const NO_MARKERS = new Set<number>();

function MiniPlots() {
  const { data, timeline, video, replay } = useDemo();
  const li = useLearningIndex();
  const hasNext = useReplayValue((s, t) => t.updateIndexes.some((i) => i > s.index));
  const curve = data.learning.curve;
  const xs = useMemo(() => curve.map((p) => p.corrections), [curve]);
  const rightSeries = useMemo<PlotSeries[]>(() => [{ key: 'right', label: 'Right risk level', tone: 'main', values: curve.map((p) => p.right_level ?? 0), format: (v) => pct(v) }], [curve]);
  const lossSeries = useMemo<PlotSeries[]>(() => [{ key: 'loss', label: 'Loss', tone: 'second', values: curve.map((p) => p.loss), format: (v) => v.toFixed(2) }], [curve]);
  const domain = useMemo(() => rightLevelDomain(curve), [curve]);
  const ticks = useMemo(() => [domain[0], (domain[0] + domain[1]) / 2, domain[1]], [domain]);
  const lossMax = useMemo(() => Math.ceil(Math.max(0.25, ...curve.map((p) => p.loss)) * 4) / 4, [curve]);
  const held = curve[li]?.held_out_cases;
  return (
    <article className="d-card d-card--plot">
      <div className="d-plothead">
        <h2 className="d-cardtitle">Over officer reviews</h2>
        {!video && (
          <Button size="sm" variant="quiet" iconRight="arrow-right" disabled={!hasNext} onClick={replay.nextUpdate}>Next update</Button>
        )}
      </div>
      <div className="d-plotpair">
        <div>
          <h3 className="d-plotlabel">Right risk level</h3>
          <LearningPlot compact xs={xs} series={rightSeries} reached={li} markers={timeline.rechosenCurve} yDomain={domain} yTicks={ticks} yFormat={(v) => pct(v)} height={132} label="Right risk level over officer reviews" />
        </div>
        <div>
          <h3 className="d-plotlabel">Loss, lower is better</h3>
          <LearningPlot compact xs={xs} series={lossSeries} reached={li} markers={NO_MARKERS} yDomain={[0, lossMax]} yTicks={[0, lossMax]} yFormat={(v) => v.toFixed(2)} height={132} label="Loss over officer reviews" />
        </div>
      </div>
      <p className="d-caption">The bottom axis counts officer reviews. <i className="d-markerkey" /> marks where thresholds were re-chosen. Measured on {held ?? 'the'} set-aside cases, not the ones in the queue.</p>
    </article>
  );
}

const QueueRow = memo(function QueueRow({ row }: { row: CaseRow }) {
  const type = useReplayValue((s, t) => {
    const n = reachedEvents(t, row.case_id, s.index);
    const list = t.caseEvents.get(row.case_id);
    return n > 0 && list ? t.events[list[n - 1]].type : null;
  });
  const decided = useReplayValue((s, t) => (t.events[s.index]?.seq ?? 0) >= row.decided_seq);
  const corrected = useReplayValue((s, t) => hasReachedType(t, row.case_id, s.index, 'correction.made'));
  const ruled = useReplayValue((s, t) => hasReachedType(t, row.case_id, s.index, 'officer.ruled'));
  const step = pipelineStep(type);
  const stage = (type && EVENT_STAGE[type]) ?? 'Waiting';
  return (
    <li className="d-qrow">
      <a href={`#/case/${encodeURIComponent(row.case_id)}`} className="d-qrow__link">
        <span className="d-qrow__top">
          <span className="d-qrow__title">{row.title}</span>
          <span className="d-qrow__badges">
            {corrected && <Tag kind="corrected">Corrected</Tag>}
            {decided ? <RouteBadge route={row.route} /> : <StatusBadge status="submitted">In progress</StatusBadge>}
          </span>
        </span>
        <span className="d-qrow__mid">
          <Pipeline step={step} compact />
          <span className="d-qrow__stage">{stage}</span>
        </span>
        <span className="d-qrow__reason">
          {decided ? reasonShort(row.reason_code) : 'Not decided yet.'}
          {ruled ? ' The simulated officer has ruled.' : ''}
        </span>
      </a>
    </li>
  );
});

function Queue() {
  const { timeline } = useDemo();
  const submitted = useSubmittedCount();
  const rows = useMemo(() => timeline.cases.slice(0, submitted).reverse(), [timeline.cases, submitted]);
  return (
    <section className="d-card d-card--flush" aria-labelledby="queue-title">
      <div className="d-cardhead">
        <h2 id="queue-title" className="d-cardtitle">Applications</h2>
        <span className="d-small d-muted">{submitted} of {timeline.cases.length} so far. Newest first.</span>
      </div>
      <ol className="d-queue">
        {rows.map((r) => <QueueRow key={r.case_id} row={r} />)}
      </ol>
    </section>
  );
}

const LogLine = memo(function LogLine({ ev, title }: { ev: ReplayEvent; title?: string }) {
  const officer = OFFICER_MOMENTS.has(ev.type);
  const correction = ev.type === 'correction.made';
  const inner = (
    <>
      <span className="d-log__meta"><span className="d-log__time">{simClock(ev.sim_time)}</span>{title && <span className="d-log__case">{title}</span>}</span>
      <span className="d-log__text">
        {correction && <Icon name="edit" size={16} />}
        {ev.summary}
        {officer && <> <Tag kind="simulated" /></>}
      </span>
    </>
  );
  const cls = `d-log__item${correction ? ' is-correction' : ''}${LEARNING_MOMENTS.has(ev.type) && !correction ? ' is-learning' : ''}`;
  return (
    <li className={cls}>
      {ev.case_id ? <a href={`#/case/${encodeURIComponent(ev.case_id)}`} className="d-log__row">{inner}</a> : <div className="d-log__row">{inner}</div>}
    </li>
  );
});

function Log() {
  const { timeline } = useDemo();
  const index = useReplayIndex();
  const [onlyOfficer, setOnlyOfficer] = useState(false);
  const lines = useMemo(() => {
    const out: ReplayEvent[] = [];
    for (let i = index; i >= 0 && out.length < 40; i -= 1) {
      const ev = timeline.events[i];
      if (!onlyOfficer || LEARNING_MOMENTS.has(ev.type)) out.push(ev);
    }
    return out;
  }, [index, onlyOfficer, timeline.events]);
  return (
    <section className="d-card d-card--flush" aria-labelledby="log-title">
      <div className="d-cardhead">
        <h2 id="log-title" className="d-cardtitle">What just happened</h2>
        <label className="d-check">
          <input type="checkbox" checked={onlyOfficer} onChange={(e) => setOnlyOfficer(e.target.checked)} />
          Corrections and updates only
        </label>
      </div>
      {lines.length ? (
        <ol className="d-log">{lines.map((ev) => <LogLine key={ev.seq} ev={ev} title={ev.case_id ? timeline.caseById.get(ev.case_id)?.title : undefined} />)}</ol>
      ) : (
        <p className="d-small d-muted d-pad">No correction or update yet.</p>
      )}
    </section>
  );
}

export function ReplayView() {
  const { data } = useDemo();
  const { curve, cards } = data.learning;
  const last = cards?.final?.right_level ?? curve[curve.length - 1]?.right_level ?? 0;
  const start = cards?.first?.right_level ?? curve[0]?.right_level ?? 0;
  return (
    <div className="d-page d-page--home">
      <SectionHeading
        level="page"
        layout="plain"
        title="Watch permits get decided"
        description={`Each row is a made-up street race application. The system reads it, scores the risk, then decides or asks an officer. ${last > start ? 'Every officer review teaches it, so it picks the right risk level more often.' : 'Every officer review teaches it, and the numbers below show what that did.'} Open any case to see exactly why.`}
      />
      <NowStrip />
      <div className="d-metrics">
        <Cards />
        <MiniPlots />
      </div>
      <div className="d-columns">
        <Queue />
        <Log />
      </div>
    </div>
  );
}

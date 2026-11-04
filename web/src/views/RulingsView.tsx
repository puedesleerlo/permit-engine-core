import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { Icon, SectionHeading, StatCallout, StatusBadge, Tabs } from '@permit-engine/ui';
import { Tag } from '../components/Tag';
import { WeightChanges } from '../components/WeightChanges';
import { useCase } from '../data';
import { useDemo, useReplayValue } from '../replay';
import { BUCKETS, bucketName, humanize, pct, simClock, treeName } from '../words';

function useInView<T extends Element>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setSeen(true);
    }, { rootMargin: '300px' });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return [ref, seen] as const;
}

const RulingCard = memo(function RulingCard({ caseId, seq, simTime, summary, correctionReached, taughtReached }: {
  caseId: string; seq: number; simTime: string; summary: string; correctionReached: boolean; taughtReached: boolean;
}) {
  const { data, timeline } = useDemo();
  const [ref, seen] = useInView<HTMLLIElement>();
  const { data: detail } = useCase(seen ? caseId : null);
  const row = timeline.caseById.get(caseId);
  const logged = data.learning.corrections?.find((k) => k.case_id === caseId);
  const officer = detail?.officer ?? null;
  const correction = taughtReached ? detail?.correction ?? null : null;
  const bucket = correction?.bucket ?? (correctionReached ? logged?.bucket ?? null : null);
  const reason = officer?.reason ?? logged?.reason ?? null;
  const changes = correction?.changes ?? [];
  const trees = [...new Set(changes.map((c) => c.tree_id))];
  return (
    <li ref={ref} className="d-ruling">
      <div className="d-ruling__top">
        <a href={`#/case/${encodeURIComponent(caseId)}`} className="d-ruling__title">{row?.title ?? caseId}</a>
        <div className="d-rowtags">
          {officer && <StatusBadge status={/deny|reject/i.test(officer.ruling) ? 'rejected' : 'approved'}>{humanize(officer.ruling)}</StatusBadge>}
          {correctionReached && <Tag kind="corrected">Corrected</Tag>}
        </div>
      </div>
      {reason ? <p className="d-body">"{reason}"</p> : <p className="d-body">{summary}</p>}
      <dl className="d-ruling__facts">
        {officer && <div><dt>Outcome</dt><dd>{officer.outcome_risky ? 'Risky' : 'Not risky'}</dd></div>}
        <div><dt>Whose mistake</dt><dd>{bucket ? bucketName(bucket) : taughtReached && !detail ? 'Loading' : 'Not a correction'}</dd></div>
        <div>
          <dt>What changed</dt>
          <dd>
            {!taughtReached ? 'Nothing' : changes.length
              ? `${changes.length} leaf ${changes.length === 1 ? 'weight' : 'weights'} in ${trees.length === 1 ? treeName(trees[0]) : `${trees.length} trees`}`
              : detail ? (bucket && BUCKETS[bucket]?.note) || 'No weights moved.' : 'Loading'}
          </dd>
        </div>
        <div><dt>Simulated time</dt><dd className="d-mono">{simClock(simTime)}</dd></div>
      </dl>
      {changes.length > 0 && (
        <details className="d-doc">
          <summary>
            <Icon name="layers" size={18} />
            <span>Exactly which weights moved</span>
            <Icon name="chevron-down" size={16} className="d-doc__chev" />
          </summary>
          <div className="d-pad"><WeightChanges changes={changes} /></div>
        </details>
      )}
      <p className="d-caption"><Tag kind="simulated" /> {data.manifest.officer_label}. Event {seq}.</p>
    </li>
  );
});

const OFFICER_TYPES = ['officer.ruled', 'correction.made', 'weights.updated'];

export function RulingsView() {
  const { data, timeline } = useDemo();
  const seqNow = useReplayValue((s, t) => latestOfficerSeq(t.events, s.index));
  const [tab, setTab] = useState('all');

  const rows = useMemo(() => {
    const taught = new Map(timeline.events.filter((e) => e.type === 'weights.updated' && e.case_id).map((e) => [e.case_id as string, e.seq]));
    return timeline.events
      .filter((e) => e.type === 'officer.ruled' && e.seq <= seqNow && e.case_id)
      .map((e) => {
        const correctionSeq = timeline.correctionSeq.get(e.case_id as string) ?? null;
        return { ev: e, correctionSeq, taughtSeq: taught.get(e.case_id as string) ?? correctionSeq };
      })
      .reverse();
  }, [timeline, seqNow]);

  const correctedNow = rows.filter((r) => r.correctionSeq !== null && r.correctionSeq <= seqNow);
  const visible = tab === 'corrections' ? correctedNow : rows;
  const totalRulings = timeline.events.filter((e) => e.type === 'officer.ruled').length;
  const accuracy = data.learning.officer?.accuracy ?? data.manifest.officer_accuracy;
  const levelAccuracy = data.learning.officer?.level_accuracy;

  return (
    <div className="d-page">
      <SectionHeading
        level="page"
        layout="plain"
        title="Officer rulings"
        description="Every review by the simulated officer, with its one-line reason. Every review teaches the system. Only a disagreement counts as a correction. A real deployment would use a person here."
      />
      <p className="d-officerband"><Tag kind="simulated" /> <strong>{data.manifest.officer_label}</strong></p>
      <div className="d-statrow">
        <StatCallout value={pct(accuracy)} label="Measured accuracy: how often its risky or not risky ruling matches the written label, over the whole run" />
        <StatCallout value={pct(levelAccuracy)} label="Level accuracy: how often the level it names matches the level the experts gave, over the whole run" />
        <StatCallout value={`${rows.length} of ${totalRulings}`} label="Reviews reached so far in the replay" />
        <StatCallout value={String(correctedNow.length)} label="Corrections so far: reviews where the officer disagreed with the system" />
      </div>
      <Tabs
        label="Which rulings to show"
        value={tab}
        onChange={setTab}
        items={[
          { id: 'all', label: 'All reviews', count: rows.length },
          { id: 'corrections', label: 'Corrections', count: correctedNow.length },
        ]}
      />
      {visible.length ? (
        <ol className="d-rulings">
          {visible.map(({ ev, correctionSeq, taughtSeq }) => (
            <RulingCard
              key={ev.seq}
              caseId={ev.case_id as string}
              seq={ev.seq}
              simTime={ev.sim_time}
              summary={ev.summary}
              correctionReached={correctionSeq !== null && correctionSeq <= seqNow}
              taughtReached={taughtSeq !== null && taughtSeq <= seqNow}
            />
          ))}
        </ol>
      ) : (
        <p className="d-notyet">The simulated officer has not ruled on anything yet. Rulings appear here as the replay reaches them.</p>
      )}
    </div>
  );
}

function latestOfficerSeq(events: { seq: number; type: string }[], index: number): number {
  for (let i = index; i >= 0; i -= 1) {
    if (OFFICER_TYPES.includes(events[i].type)) return events[i].seq;
  }
  return 0;
}

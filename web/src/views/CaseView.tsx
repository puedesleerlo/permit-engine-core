import { useMemo, useState, type ReactNode } from 'react';
import { Breadcrumbs, Button, Icon, KeyValueList, Skeleton, StatusBadge, type PermitStatus } from '@permit-engine/ui';
import { Clause, useClauseText } from '../components/Clause';
import { LevelBar, LevelLegend } from '../components/LevelBar';
import { ProbabilityTree } from '../components/ProbabilityTree';
import { Highlighted, excerptAround, findQuote } from '../components/Quote';
import { RiskBandMeter } from '../components/RiskBandMeter';
import { RouteBadge } from '../components/RouteBadge';
import { fmtAny } from '../components/RuleItems';
import { Tag } from '../components/Tag';
import { WeightChanges } from '../components/WeightChanges';
import { useCase } from '../data';
import { reachedEvents, useDemo, useReplayValue } from '../replay';
import type { CaseDetail, EvidenceRecord, HazardEval, TreeEval } from '../types';
import {
  BUCKETS, DECISION_TABLE, EVENT_STAGE, QUESTION_KINDS, REASONS, REQUIREMENT_WORDS, VERDICTS,
  bucketName, fmtThresholds, humanize, num, pct, reasonName, simClock, treeName,
} from '../words';

const EVIDENCE_QUESTION: Record<string, string> = {
  police_escort_letter: 'escort_confirmed',
  police_escort_email: 'escort_confirmed',
  ambulance_agreement: 'ambulance_on_site',
};

const ANCHOR_FALLBACK: Record<string, number[]> = { likelihood: [0.02, 0.1, 0.3], severity: [0.1, 0.4, 1] };

function useAnchors() {
  const { data } = useDemo();
  return (scale: 'likelihood' | 'severity') => {
    const value = data.rules.settings?.find((s) => s.key === `risk.anchors.${scale}`)?.value;
    return Array.isArray(value) ? (value as number[]) : ANCHOR_FALLBACK[scale];
  };
}

function Step({ id, n, title, intro, reached, stoppedNote, children }: {
  id: string; n: number; title: string; intro?: ReactNode; reached: boolean; stoppedNote?: string | null; children?: ReactNode;
}) {
  return (
    <section id={id} className="d-step">
      <div className="d-step__head">
        <span className="d-step__n" aria-hidden>{String(n).padStart(2, '0')}</span>
        <h2 className="d-step__title">{title}</h2>
      </div>
      <div className="d-step__body">
        {intro && reached && <p className="d-step__intro">{intro}</p>}
        {!reached ? (
          <p className="d-notyet"><Icon name="clock" size={18} /> The replay has not reached this step yet.</p>
        ) : stoppedNote ? (
          <p className="d-notyet">{stoppedNote}</p>
        ) : children}
      </div>
    </section>
  );
}

function allQuotes(evidence: EvidenceRecord[], docName: string): string[] {
  return evidence
    .filter((e) => docMatches(e.document, docName))
    .flatMap((e) => e.fields ?? [])
    .map((f) => f.quote)
    .filter((q): q is string => Boolean(q));
}

function docMatches(document: string | null | undefined, name: string) {
  if (!document) return false;
  const strip = (s: string) => s.toLowerCase().replace(/\.[a-z0-9]+$/, '').split('/').pop();
  return strip(document) === strip(name);
}

function documentText(c: CaseDetail, name?: string | null): string | null {
  if (!name) return null;
  const att = c.documents.attachments?.find((a) => docMatches(name, a.name));
  if (att) return att.text;
  if (docMatches(name, 'cover_letter')) return c.documents.cover_letter ?? null;
  if (docMatches(name, 'form')) return JSON.stringify(c.documents.form, null, 2);
  return null;
}

function flatForm(form: Record<string, unknown>, prefix = ''): { label: string; value: string; mono?: boolean }[] {
  return Object.entries(form ?? {}).flatMap(([k, v]) => {
    if (v && typeof v === 'object' && !Array.isArray(v)) return flatForm(v as Record<string, unknown>, `${prefix}${k} `);
    const word = typeof v === 'string' && /^[a-z]+(_[a-z]+)+$/.test(v) ? humanize(v) : fmtAny(v);
    return [{ label: humanize(`${prefix}${k}`), value: word }];
  });
}

function Documents({ c }: { c: CaseDetail }) {
  const evidence = c.evidence ?? [];
  const docs: { name: string; text: string }[] = [
    ...(c.documents.cover_letter ? [{ name: 'cover_letter.txt', text: c.documents.cover_letter }] : []),
    ...(c.documents.attachments ?? []),
  ];
  return (
    <div className="d-stack">
      <div className="d-panel">
        <h3 className="d-h4">Application form</h3>
        <KeyValueList columns={2} items={flatForm(c.documents.form).map((f) => ({ label: f.label, value: f.value }))} />
      </div>
      <div className="d-docs">
        {docs.map((d) => {
          const quotes = allQuotes(evidence, d.name);
          return (
            <details key={d.name} className="d-doc">
              <summary>
                <Icon name="file" size={18} />
                <span className="d-mono d-doc__name">{d.name}</span>
                {quotes.length > 0 && <span className="d-small d-muted">{quotes.length} highlighted</span>}
                <Icon name="chevron-down" size={16} className="d-doc__chev" />
              </summary>
              <pre className="d-doctext"><Highlighted text={d.text} quotes={quotes} /></pre>
            </details>
          );
        })}
      </div>
    </div>
  );
}

const VERDICT_STATUS: Record<string, PermitStatus> = { supported: 'approved', unsupported: 'action-required', contradicted: 'rejected' };

function EvidenceCard({ record, c }: { record: EvidenceRecord; c: CaseDetail }) {
  const [whole, setWhole] = useState(false);
  const text = documentText(c, record.document);
  const quotes = (record.fields ?? []).map((f) => f.quote).filter((q): q is string => Boolean(q));
  const missingQuotes = text ? quotes.filter((q) => !findQuote(text, q)) : quotes;
  const excerpt = text ? excerptAround(text, quotes) : null;
  const shown = whole && text ? { text, cutStart: false, cutEnd: false } : excerpt;
  const req = c.requirements?.find((r) => r.evidence_type === record.evidence_type);
  const questionId = EVIDENCE_QUESTION[record.evidence_type];
  const question = c.hazards?.flatMap((h) => [h.likelihood, h.severity]).flatMap((t) => t?.questions ?? []).find((q) => q.id === questionId);
  const clause = req?.clause ?? question?.clause ?? null;
  return (
    <article className="d-panel d-evidence">
      <header className="d-evidence__head">
        <h3 className="d-h4">{humanize(record.evidence_type)}</h3>
        <div className="d-rowtags">
          {record.status === 'found'
            ? <StatusBadge status={VERDICT_STATUS[record.verdict ?? ''] ?? 'in-review'}>{record.verdict ? humanize(record.verdict) : 'Found'}</StatusBadge>
            : <StatusBadge status="draft">Not found</StatusBadge>}
          {record.source && <Tag kind={record.source === 'stored' ? 'stored' : 'simulated'}>{humanize(record.source)}</Tag>}
        </div>
      </header>
      <p className="d-small">
        {record.status === 'found' ? <>Found in <span className="d-mono">{record.document}</span>. </> : 'No document of this type was sent. '}
        {record.verdict && VERDICTS[record.verdict] ? `${VERDICTS[record.verdict]} ` : ''}
        {record.reason && /\s/.test(record.reason) ? record.reason : ''}
        {clause && <> Clause <Clause id={clause} />.</>}
      </p>
      {shown && quotes.length > 0 && (
        <figure className="d-excerpt">
          <figcaption className="d-caption">The words it relied on, marked in <span className="d-mono">{record.document}</span>:</figcaption>
          <pre className="d-doctext">
            {shown.cutStart && '... '}
            <Highlighted text={shown.text} quotes={quotes} />
            {shown.cutEnd && ' ...'}
          </pre>
          {text && excerpt && (excerpt.cutStart || excerpt.cutEnd) && (
            <button type="button" className="d-textbtn" onClick={() => setWhole(!whole)}>{whole ? 'Show less' : 'Show the whole document'}</button>
          )}
        </figure>
      )}
      {missingQuotes.length > 0 && (
        <p className="d-small d-warn"><Icon name="alert" size={16} /> {missingQuotes.length} quote could not be found in the document text: "{missingQuotes[0]}"</p>
      )}
      {(record.fields?.length ?? 0) > 0 && (
        <div className="d-tablewrap">
          <table className="d-table">
            <thead><tr><th>Detail</th><th>Value</th><th>Quote is in the document</th><th>Matches the form</th></tr></thead>
            <tbody>
              {record.fields!.map((f) => (
                <tr key={f.name}>
                  <td>{humanize(f.name)}</td>
                  <td>{fmtAny(f.value)}</td>
                  <td><YesNo value={f.verified} /></td>
                  <td><YesNo value={f.matches_form} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}

function YesNo({ value }: { value?: boolean | null }) {
  if (value === null || value === undefined) return <span className="d-muted">Not compared</span>;
  return value
    ? <span className="d-yes"><Icon name="check" size={16} /> Yes</span>
    : <span className="d-no"><Icon name="x" size={16} /> No</span>;
}

const REQUIREMENT_STATUS: Record<string, PermitStatus> = { met: 'approved', failed: 'rejected', missing: 'action-required', unclear: 'in-review' };

function EvidenceList({ c }: { c: CaseDetail }) {
  const evidence = c.evidence ?? [];
  const quoted = evidence.filter((e) => e.status === 'found' && (e.fields?.length ?? 0) > 0);
  const whole = evidence.filter((e) => e.status === 'found' && !(e.fields?.length ?? 0));
  const absent = evidence.filter((e) => e.status !== 'found');
  return (
    <>
      {quoted.map((e) => <EvidenceCard key={e.evidence_type} record={e} c={c} />)}
      {whole.length > 0 && (
        <div className="d-panel">
          <h3 className="d-h4">Plans read whole</h3>
          <p className="d-small d-muted">Jev reads these documents as they are, so no words are pulled out of them here. Its answers are in the trees below.</p>
          <ul className="d-caselines">
            {whole.map((e) => (
              <li key={e.evidence_type} className="d-caseline">
                <span>{humanize(e.evidence_type)}</span>
                <span className="d-mono d-muted">{e.document}</span>
                {e.verdict && <span className="d-small d-muted">{humanize(e.verdict)}</span>}
                {e.source && <Tag kind={e.source === 'stored' ? 'stored' : 'simulated'}>{humanize(e.source)}</Tag>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {absent.length > 0 && (
        <div className="d-panel">
          <h3 className="d-h4">Not found in the documents</h3>
          <p className="d-small d-muted">Absent means no document of this type was sent. It is not an error in itself.</p>
          <ul className="d-caselines">
            {absent.map((e) => (
              <li key={e.evidence_type} className="d-caseline">
                <span>{humanize(e.evidence_type)}</span>
                {e.reason && /\s/.test(e.reason) && <span className="d-small d-muted">{e.reason}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function Requirements({ c }: { c: CaseDetail }) {
  return (
    <div className="d-stack">
      {(c.checks?.length ?? 0) > 0 && (
        <div className="d-panel">
          <h3 className="d-h4">Basic checks</h3>
          <ul className="d-checks">
            {c.checks!.map((k) => (
              <li key={k.id}>
                {k.passed ? <span className="d-yes"><Icon name="check" size={16} /> Passed</span> : <span className="d-no"><Icon name="x" size={16} /> Failed</span>}
                <span>{humanize(k.id)}</span>
                <Clause id={k.clause} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {(c.requirements?.length ?? 0) > 0 ? (
        <div className="d-panel">
          <h3 className="d-h4">Requirements</h3>
          <ul className="d-reqs">
            {c.requirements!.map((r) => (
              <li key={r.id}>
                <div className="d-reqs__top">
                  <strong>{humanize(r.id)}</strong>
                  <StatusBadge status={REQUIREMENT_STATUS[r.status] ?? 'draft'}>{humanize(r.status)}</StatusBadge>
                  <Clause id={r.clause} />
                </div>
                <p className="d-small d-muted">{REQUIREMENT_WORDS[r.status] ?? ''}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="d-small d-muted">No requirement was checked, because this case stopped earlier.</p>
      )}
    </div>
  );
}

function TreeBlock({ tree, scale, anchors }: { tree: TreeEval; scale: 'Likelihood' | 'Severity'; anchors: number[] }) {
  return (
    <figure className="d-treeblock">
      <figcaption>
        <div className="d-treeblock__head">
          <h4 className="d-h4">{treeName(tree.tree_id)}</h4>
          <span className="d-treeblock__value"><span className="d-muted d-small">{scale}</span> <strong className="d-mono">{num(tree.value)}</strong></span>
        </div>
        <ol className="d-questions">
          {tree.questions.map((q, i) => (
            <li key={q.id}>
              <span className="d-qnum" aria-hidden>{i + 1}</span>
              <div>
                <p className="d-small">{q.text}</p>
                <p className="d-caption">
                  Yes {pct(q.answer)}. {QUESTION_KINDS[q.kind] ?? humanize(q.kind)}. <Clause id={q.clause} />
                </p>
              </div>
            </li>
          ))}
        </ol>
        <LevelLegend names={tree.level_names} anchors={anchors} />
      </figcaption>
      <ProbabilityTree tree={tree} />
      <div className="d-treeblock__foot">
        <div className="d-treeblock__overall">
          <span className="d-small">This case overall</span>
          <LevelBar levels={tree.levels} names={tree.level_names} />
        </div>
        <p className="d-caption">
          {tree.levels.map((p, i) => `${Math.round(p * 100)}% ${tree.level_names[i]}`).join(', ')}. Each level times its number, added up, gives {num(tree.value)}.
          How split this answer is: {num(tree.entropy, 2)} (0 means certain, 1.10 means an even three-way split).
        </p>
      </div>
    </figure>
  );
}

function HazardTrees({ hazard }: { hazard: HazardEval }) {
  const anchors = useAnchors();
  return (
    <article className="d-hazardtrees">
      <h3 className="d-h3">{hazard.name}</h3>
      <div className="d-treegrid">
        {hazard.likelihood && <TreeBlock tree={hazard.likelihood} scale="Likelihood" anchors={anchors('likelihood')} />}
        {hazard.severity && <TreeBlock tree={hazard.severity} scale="Severity" anchors={anchors('severity')} />}
      </div>
    </article>
  );
}

function RiskSum({ c }: { c: CaseDetail }) {
  const live = (c.hazards ?? []).filter((h) => h.applies && h.likelihood && h.severity);
  return (
    <div className="d-stack">
      <div className="d-panel">
        <div className="d-tablewrap">
          <table className="d-table d-table--num">
            <thead><tr><th>Hazard</th><th>How likely</th><th aria-hidden /><th>How bad</th><th aria-hidden /><th>Risk</th></tr></thead>
            <tbody>
              {live.map((h) => (
                <tr key={h.id}>
                  <td>{h.name}</td>
                  <td className="d-mono">{num(h.likelihood!.value)}</td>
                  <td className="d-muted" aria-hidden>x</td>
                  <td className="d-mono">{num(h.severity!.value)}</td>
                  <td className="d-muted" aria-hidden>=</td>
                  <td className="d-mono">{num(h.product)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr><td colSpan={5}>Sum over the hazards that apply</td><td className="d-mono"><strong>{num(c.risk)}</strong></td></tr>
            </tfoot>
          </table>
        </div>
      </div>
      <div className="d-panel">
        <RiskBandMeter risk={c.risk} tLow={c.t_low} tHigh={c.t_high} highestSeverity={c.highest_severity} ceiling={c.ceiling} />
        <ul className="d-keyline">
          <li><i className="d-band-key d-band-key--low" /><span>Under <span className="d-mono">t_low</span>: approved without an officer</span></li>
          <li><i className="d-band-key d-band-key--mid" /><span>Between them, the review band: an officer decides</span></li>
          <li><i className="d-band-key d-band-key--high" /><span>At or over <span className="d-mono">t_high</span>: an officer decides, high risk</span></li>
        </ul>
        <p className="d-caption">
          The ceiling is checked against the worst single severity, not the sum. It exists because a very small chance of something terrible can multiply to a small number. At or above it, an officer always decides.
        </p>
      </div>
    </div>
  );
}

function RuleFired({ c }: { c: CaseDetail }) {
  const words = useClauseText();
  const fired = c.decision.row;
  return (
    <div className="d-stack">
      <ol className="d-dtable" start={0}>
        {DECISION_TABLE.map((row) => {
          const state = row.row === fired ? 'fired' : row.row < fired ? 'passed' : 'unread';
          return (
            <li key={row.row} className={`d-dtable__row is-${state}`} aria-current={state === 'fired' ? 'true' : undefined}>
              <span className="d-dtable__n">{row.row}</span>
              <span className="d-dtable__when">{row.when}</span>
              <span className="d-dtable__goes">{row.goes}</span>
              <span className="d-dtable__state">
                {state === 'fired' ? 'Fired' : state === 'passed' ? 'Did not match' : 'Not read'}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="d-panel d-firedtext">
        <p className="d-lead">{c.decision.text}</p>
        <div className="d-rowtags">
          <RouteBadge route={c.decision.route} />
          <span className="d-small d-muted">{reasonName(c.decision.reason_code)}</span>
        </div>
        {(c.decision.clauses ?? []).map((id) => (
          <p key={id} className="d-small"><span className="d-clause d-clause--static">{id}</span> {words(id) ?? ''}</p>
        ))}
      </div>
    </div>
  );
}

function OfficerBlock({ c }: { c: CaseDetail }) {
  const { data } = useDemo();
  const o = c.officer;
  if (!o) return <p className="d-small d-muted">No officer looked at this case.</p>;
  return (
    <div className="d-panel">
      <p className="d-officerlabel"><Tag kind="simulated" /> {o.label ?? data.manifest.officer_label}</p>
      <div className="d-rowtags">
        <StatusBadge status={/deny|reject/i.test(o.ruling) ? 'rejected' : 'approved'}>{humanize(o.ruling)}</StatusBadge>
        <span className="d-small">Outcome: {o.outcome_risky ? 'risky' : 'not risky'}</span>
        {o.agrees_with_label !== null && o.agrees_with_label !== undefined && (
          <span className="d-small d-muted">{o.agrees_with_label ? 'Agrees with the written label' : 'Differs from the written label'}</span>
        )}
      </div>
      <p className="d-body">"{o.reason}"</p>
      {(o.named?.length ?? 0) > 0 && (
        <p className="d-small d-muted">
          Named: {o.named!.map((n) => `${treeName(n.tree_id)}, right level ${levelName(c, n.tree_id, n.level)}`).join('; ')}
        </p>
      )}
    </div>
  );
}

function levelName(c: CaseDetail, treeId: string, level: number) {
  for (const h of c.hazards ?? []) {
    for (const t of [h.likelihood, h.severity]) {
      if (t?.tree_id === treeId) return t.level_names[level] ?? String(level);
    }
  }
  return String(level);
}

function CorrectionBlock({ c }: { c: CaseDetail }) {
  const k = c.correction;
  if (!k) return <p className="d-small d-muted">No review moved the weights on this case.</p>;
  const changes = k.changes ?? [];
  return (
    <div className="d-stack">
      <div className="d-panel">
        <p className="d-body">
          <strong>{k.bucket === 'confirmed' ? 'The officer agreed.' : 'A correction: the officer disagreed with the system.'}</strong>{' '}
          {k.bucket !== 'confirmed' && `Whose mistake: ${bucketName(k.bucket).toLowerCase()}. `}The outcome was {k.outcome_risky ? 'risky' : 'not risky'}.
        </p>
        {k.bucket === 'confirmed' && <p className="d-small d-muted">{BUCKETS.confirmed.note}</p>}
      </div>
      {changes.length > 0 && (
        <div className="d-panel">
          <h3 className="d-h4">Exactly what moved</h3>
          <p className="d-small d-muted">Only the leaves this case reached can change, each in proportion to how much of the case reached it. The count says how many past cases now stand behind that leaf. Largest moves first.</p>
          <WeightChanges changes={changes} />
        </div>
      )}
    </div>
  );
}

function Versions({ c }: { c: CaseDetail }) {
  const { timeline } = useDemo();
  const row = timeline.caseById.get(c.case_id);
  const items = timeline.caseEvents.get(c.case_id) ?? [];
  return (
    <div className="d-stack">
      <div className="d-panel">
        <KeyValueList columns={2} items={[
          { label: 'Weights', value: c.manifest?.weights_version ?? row?.weights_version ?? 'Not recorded', mono: true },
          { label: 'Thresholds', value: fmtThresholds(c.manifest?.thresholds, c.t_low, c.t_high), mono: true },
          { label: 'Rules', value: <span title={c.manifest?.rules_hash ?? undefined}>{c.manifest?.rules_hash ? c.manifest.rules_hash.slice(0, 16) : 'Not recorded'}</span>, mono: true },
          { label: 'Answers', value: c.manifest?.source ? <Tag kind={c.manifest.source === 'stored' ? 'stored' : 'simulated'}>{humanize(c.manifest.source)}</Tag> : 'Not recorded' },
        ]} />
      </div>
      <details className="d-doc">
        <summary>
          <Icon name="clock" size={18} />
          <span>Every event for this case</span>
          <span className="d-small d-muted">{items.length}</span>
          <Icon name="chevron-down" size={16} className="d-doc__chev" />
        </summary>
        <ol className="d-caseevents">
          {items.map((i) => {
            const ev = timeline.events[i];
            return (
              <li key={ev.seq}>
                <span className="d-mono d-muted">{simClock(ev.sim_time)}</span>
                <span>{ev.summary}</span>
              </li>
            );
          })}
        </ol>
      </details>
    </div>
  );
}

const INDEX = [
  ['documents', 'Documents'], ['evidence', 'Evidence'], ['requirements', 'Requirements'], ['hazards', 'Hazards'], ['trees', 'Trees'],
  ['risk', 'Risk'], ['rule', 'Rule fired'], ['officer', 'Officer'], ['correction', 'What it taught'], ['versions', 'Versions'],
] as const;

export function CaseView({ id }: { id: string }) {
  const { timeline, video } = useDemo();
  const { data: c, error } = useCase(id);
  const row = timeline.caseById.get(id) ?? null;
  const reachedCount = useReplayValue((s, t) => reachedEvents(t, id, s.index));
  const [showAll, setShowAll] = useState(false);

  const list = timeline.caseEvents.get(id);
  const total = list?.length ?? 0;
  const reachedTypes = useMemo(() => new Set((list ?? []).slice(0, reachedCount).map((i) => timeline.events[i].type)), [list, reachedCount, timeline.events]);
  const notArrived = reachedCount === 0;
  const finished = total > 0 && reachedCount >= total;
  const full = showAll || notArrived || finished;
  const decidedReached = reachedTypes.has('decision.made');
  const at = (...types: string[]) => full || types.some((t) => reachedTypes.has(t)) || decidedReached;
  const lastType = list && reachedCount > 0 ? timeline.events[list[reachedCount - 1]].type : null;

  if (error) {
    return (
      <div className="d-page">
        <Breadcrumbs items={[{ label: 'Replay', href: '#/' }, { label: id }]} />
        <p className="d-notyet">This case could not be loaded: {error}</p>
      </div>
    );
  }
  if (!c) {
    return (
      <div className="d-page">
        <Breadcrumbs items={[{ label: 'Replay', href: '#/' }, { label: row?.title ?? id }]} />
        <Skeleton variant="text" lines={6} label="Loading the case" />
      </div>
    );
  }

  const evidence = c.evidence ?? [];
  const unmapped = c.unmapped_documents ?? [];
  const hazards = c.hazards ?? [];
  const liveHazards = hazards.filter((h) => h.applies && h.likelihood && h.severity);
  const stopped = 'This case stopped before this step.';
  const hasOfficerEvent = (list ?? []).some((i) => timeline.events[i].type === 'officer.ruled');
  const hasTeachingEvent = (list ?? []).some((i) => ['correction.made', 'weights.updated'].includes(timeline.events[i].type));
  const reason = REASONS[c.decision.reason_code];
  const scrollTo = (target: string) => document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const decisionVisible = at('decision.made');

  return (
    <div className="d-page d-case">
      <Breadcrumbs items={[{ label: 'Replay', href: '#/' }, { label: c.title }]} />
      <header className="d-casehead">
        <h1 className="pe-h1">{c.title}</h1>
        <div className="d-rowtags">
          <span className="d-clause d-clause--static">{c.case_id}</span>
          {decisionVisible ? <RouteBadge route={c.decision.route} /> : <StatusBadge status="submitted">In progress</StatusBadge>}
          {(full || reachedTypes.has('correction.made')) && c.correction?.bucket === 'ai_wrong' && <Tag kind="corrected">Corrected</Tag>}
        </div>
      </header>

      {!video && !full && (
        <div className="d-progressnote">
          <p className="d-small">The replay is still on this case: {EVENT_STAGE[lastType ?? ''] ?? 'starting'}. Steps appear as it reaches them.</p>
          <Button size="sm" variant="secondary" onClick={() => setShowAll(true)}>Show the finished case</Button>
        </div>
      )}
      {notArrived && (
        <div className="d-progressnote">
          <p className="d-small">The replay has not reached this case yet, so this is the finished record.</p>
        </div>
      )}

      {decisionVisible && (
        <section className="d-inshort" aria-label="In short">
          <div>
            <h2 className="d-h3">In short</h2>
            <p className="d-lead">{c.decision.text}</p>
            {reason && <p className="d-small d-muted">{reason.long}</p>}
          </div>
          <dl className="d-inshort__facts">
            <div><dt>Risk</dt><dd className="d-mono">{liveHazards.length === 0 || c.risk === null ? 'Not computed' : num(c.risk)}</dd></div>
            <div><dt>Rule fired</dt><dd>Row {c.decision.row} {(c.decision.clauses ?? []).map((k) => <Clause key={k} id={k} />)}</dd></div>
            {row && <div><dt>Written label</dt><dd>{row.label_risky ? 'Risky' : 'Not risky'}. {row.agreed_with_label ? 'The system agreed.' : 'The system disagreed.'}</dd></div>}
          </dl>
        </section>
      )}

      <nav className="d-caseindex" aria-label="Steps on this page">
        {INDEX.map(([target, label], i) => (
          <button key={target} type="button" onClick={() => scrollTo(target)}>
            <span className="d-mono">{i + 1}</span> {label}
          </button>
        ))}
      </nav>

      <Step id="documents" n={1} title="What the applicant sent" reached
        intro="All written by a script. No real organiser or race is involved. Marked words are the ones used as evidence in the next step.">
        <Documents c={c} />
      </Step>

      <Step id="evidence" n={2} title="What was found in the documents"
        intro="An agentic LLM looks for each kind of proof the rules ask for, and must quote the words it relied on. Code then checks that each quote really is in the document and compares the details with the form. A verdict answers one question: does this document show what this proof requires?"
        reached={at('evidence.judged', 'evidence.linked')}
        stoppedNote={evidence.length === 0 && unmapped.length === 0 ? stopped : null}>
        <div className="d-stack">
          <EvidenceList c={c} />
          {unmapped.map((u) => (
            <article key={u.document} className="d-panel d-unmapped">
              <h3 className="d-h4">Unknown document</h3>
              <p className="d-small"><span className="d-mono">{u.document}</span>: {u.why}</p>
            </article>
          ))}
        </div>
      </Step>

      <Step id="requirements" n={3} title="Requirement status"
        intro="A requirement is something the ordinance demands outright, such as event insurance. Its status comes straight from the proof above, by written rule."
        reached={at('requirements.checked', 'checks.done')}>
        <Requirements c={c} />
      </Step>

      <Step id="hazards" n={4} title="Which hazards apply"
        intro="Written rules decide this, not a model. A hazard that does not apply adds nothing to the risk."
        reached={at('hazards.screened')} stoppedNote={hazards.length === 0 ? stopped : null}>
        <ul className="d-hazards">
          {hazards.map((h) => (
            <li key={h.id} className={h.applies ? 'is-on' : 'is-off'}>
              {h.applies ? <Icon name="check-circle" size={20} /> : <Icon name="minus" size={20} />}
              <div>
                <strong>{h.name}</strong>: {h.applies ? 'applies' : 'does not apply'}
                {h.why && <p className="d-small d-muted">{h.why}</p>}
              </div>
            </li>
          ))}
        </ul>
      </Step>

      <Step id="trees" n={5} title="How likely, and how bad"
        intro="Each hazard has two trees of yes-or-no questions: one for how likely it is, one for how bad it would be. An answer is a probability, so the case splits and flows down both branches. The thicker the line, the more of the case went that way. Each leaf at the end holds a split across levels, and a count of the cases behind it, starting from a small assumed number. Corrections change only those splits and counts."
        reached={at('trees.evaluated')} stoppedNote={liveHazards.length === 0 ? stopped : null}>
        <div className="d-stack d-stack--lg">
          {liveHazards.map((h) => <HazardTrees key={h.id} hazard={h} />)}
        </div>
      </Step>

      <Step id="risk" n={6} title="Risk against the thresholds"
        intro="For each hazard, likelihood times severity. Risk is the sum. Two thresholds cut the range into approve, review and high risk."
        reached={at('risk.computed')} stoppedNote={c.risk === null || liveHazards.length === 0 ? stopped : null}>
        <RiskSum c={c} />
      </Step>

      <Step id="rule" n={7} title="The rule that fired"
        intro="The decision table is written as code in Rego, not left to a model. It is read from the top and the first row that matches wins."
        reached={at('decision.made')}>
        <RuleFired c={c} />
      </Step>

      <Step id="officer" n={8} title="The officer's ruling"
        reached={full || reachedTypes.has('officer.ruled') || (decidedReached && !hasOfficerEvent)}>
        <OfficerBlock c={c} />
      </Step>

      <Step id="correction" n={9} title="What the review taught"
        intro="Every officer review teaches, whether the officer agrees or not. Only a disagreement counts as a correction."
        reached={full || reachedTypes.has('correction.made') || reachedTypes.has('weights.updated') || (decidedReached && !hasTeachingEvent)}>
        <CorrectionBlock c={c} />
      </Step>

      <Step id="versions" n={10} title="Versions used" intro="Everything a decision used is recorded, so it can be replayed exactly." reached>
        <Versions c={c} />
      </Step>
    </div>
  );
}

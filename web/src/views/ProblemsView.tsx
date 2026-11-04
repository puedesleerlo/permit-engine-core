import { useMemo } from 'react';
import { Icon, SectionHeading, StatCallout } from '@permit-engine/ui';
import { RouteBadge } from '../components/RouteBadge';
import { Tag } from '../components/Tag';
import { useDemo, useReplayValue } from '../replay';
import type { CaseRow } from '../types';
import { REASONS, reasonName, riskText } from '../words';

const ORDER = ['red_flag', 'requirement_unclear', 'unmapped_evidence', 'model_failure', 'policy_unavailable', 'stop_switch', 'severity_ceiling', 'requirement_missing', 'high_risk', 'review_band'];

function CaseLine({ row, note, seq }: { row: CaseRow; note?: string; seq: number }) {
  const { timeline } = useDemo();
  const correctedAt = timeline.correctionSeq.get(row.case_id);
  return (
    <li className="d-caseline">
      <a href={`#/case/${encodeURIComponent(row.case_id)}`}>{row.title}</a>
      <span className="d-mono d-muted">Risk {riskText(row.risk, row.row)}</span>
      {note && <span className="d-small d-muted">{note}</span>}
      {correctedAt !== undefined && correctedAt <= seq && <Tag kind="corrected">Corrected</Tag>}
    </li>
  );
}

export function ProblemsView() {
  const { timeline, data } = useDemo();
  const decidedCount = useReplayValue((s, t) => {
    const seq = t.events[s.index]?.seq ?? 0;
    return t.cases.filter((c) => c.decided_seq <= seq).length;
  });
  const seq = useReplayValue((s, t) => t.events[s.index]?.seq ?? 0);
  const decided = useMemo(
    () => [...timeline.cases].sort((a, b) => a.decided_seq - b.decided_seq).slice(0, decidedCount),
    [timeline.cases, decidedCount],
  );

  const toOfficer = decided.filter((c) => c.route === 'officer');
  const groups = useMemo(() => {
    const map = new Map<string, CaseRow[]>();
    for (const c of toOfficer) map.set(c.reason_code, [...(map.get(c.reason_code) ?? []), c]);
    return [...map.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
  }, [toOfficer]);

  const riskyApprovals = decided.filter((c) => c.route === 'approved' && c.label_risky);
  const forbidden = decided.filter((c) => c.route === 'approved' && !c.label_risky && !c.agreed_with_label);
  const others = decided.filter((c) => !c.agreed_with_label && c.route !== 'approved');

  return (
    <div className="d-page">
      <SectionHeading
        level="page"
        layout="plain"
        title="Problem cases"
        description="Where the system stopped and asked a person, and where it was wrong according to its written labels. Only cases the replay has decided so far are shown."
      />
      <div className="d-statrow">
        <StatCallout value={String(toOfficer.length)} label={`Sent to an officer, of ${decided.length} decided so far`} />
        <StatCallout value={String(forbidden.length)} label="Forbidden permits so far" />
        <StatCallout value={String(riskyApprovals.length)} label="Risky approvals so far" />
      </div>

      <section className="d-section">
        <SectionHeading title="The two ways it can fail" description="These are counted apart because they mean different things. Both compare the system with labels the author wrote, so they test the mechanism, not real events." />
        <div className="d-two">
          <article className="d-panel">
            <h3 className="d-h3"><Icon name="x-circle" size={20} /> Forbidden permit</h3>
            <p className="d-small d-muted">An approval the ordinance does not allow.</p>
            {forbidden.length ? <ul className="d-caselines">{forbidden.map((c) => <CaseLine key={c.case_id} row={c} seq={seq} />)}</ul> : <p className="d-small">None so far.</p>}
          </article>
          <article className="d-panel">
            <h3 className="d-h3"><Icon name="alert" size={20} /> Risky approval</h3>
            <p className="d-small d-muted">An automatic approval of a case labelled risky.</p>
            {riskyApprovals.length ? <ul className="d-caselines">{riskyApprovals.map((c) => <CaseLine key={c.case_id} row={c} seq={seq} />)}</ul> : <p className="d-small">None so far.</p>}
          </article>
        </div>
        {others.length > 0 && (
          <details className="d-doc">
            <summary>
              <Icon name="users" size={18} />
              <span>Other disagreements with the label</span>
              <span className="d-mono d-muted">{others.length}</span>
              <Icon name="chevron-down" size={16} className="d-doc__chev" />
            </summary>
            <div className="d-pad d-stack">
              <p className="d-small d-muted">The route differs from the label, but no unsafe permit came of it. These cost a person's time.</p>
              <ul className="d-caselines">
                {others.map((c) => (
                  <li key={c.case_id} className="d-caseline">
                    <a href={`#/case/${encodeURIComponent(c.case_id)}`}>{c.title}</a>
                    <RouteBadge route={c.route} />
                    {(timeline.correctionSeq.get(c.case_id) ?? Infinity) <= seq && <Tag kind="corrected">Corrected</Tag>}
                  </li>
                ))}
              </ul>
            </div>
          </details>
        )}
      </section>

      <section className="d-section">
        <SectionHeading title="Sent to an officer, by reason" meta={`${toOfficer.length} cases`} />
        <p className="d-officerlabel"><Tag kind="simulated" /> {data.manifest.officer_label}</p>
        {groups.length ? (
          <div className="d-groups">
            {groups.map(([code, rows]) => (
              <article key={code} className="d-panel">
                <div className="d-group__head">
                  <h3 className="d-h4">{reasonName(code)}</h3>
                  <span className="d-mono d-muted">{rows.length}</span>
                </div>
                <p className="d-small d-muted">{REASONS[code]?.long ?? ''}</p>
                <ul className="d-caselines">{rows.map((c) => <CaseLine key={c.case_id} row={c} seq={seq} />)}</ul>
              </article>
            ))}
          </div>
        ) : (
          <p className="d-notyet">No case has gone to an officer yet.</p>
        )}
      </section>
    </div>
  );
}

function rank(code: string) {
  const i = ORDER.indexOf(code);
  return i < 0 ? ORDER.length : i;
}

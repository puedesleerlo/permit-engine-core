import { SectionHeading, StatusBadge } from '@permit-engine/ui';
import { RuleItems, fmtAny } from '../components/RuleItems';
import { useDemo, useLearningIndex } from '../replay';
import { DECISION_TABLE, humanize, num } from '../words';

export function RulesView() {
  const { data } = useDemo();
  const li = useLearningIndex();
  const { rules, learning } = data;
  const point = learning.curve[li];
  return (
    <div className="d-page">
      <SectionHeading
        level="page"
        layout="plain"
        title="Rules"
        description="The ordinance, the evidence map and the thresholds this run used. They are invented for this demo, and shown read only."
      />

      <section className="d-section">
        <SectionHeading title="Thresholds" description="Thresholds are re-chosen as the system learns, to hold the targets below. They follow the replay." />
        <dl className="d-thresholds">
          <div><dt>Low threshold, <span className="d-mono">t_low</span></dt><dd className="d-mono">{num(point?.t_low, 2)}</dd><p className="d-small d-muted">Under this, a case with no other problem is approved without an officer.</p></div>
          <div><dt>High threshold, <span className="d-mono">t_high</span></dt><dd className="d-mono">{num(point?.t_high, 2)}</dd><p className="d-small d-muted">At or over this, the case goes to an officer as high risk. Between the two it goes to an officer for review.</p></div>
        </dl>
      </section>

      <section className="d-section">
        <SectionHeading title="Settings" description="Each setting has limits and one owner. A value outside its limits stops the run." />
        <div className="d-settings">
          {(rules.settings ?? []).map((s) => (
            <article key={s.key} className="d-panel">
              <div className="d-group__head">
                <code className="d-mono d-setting__key">{s.key}</code>
                <strong className="d-mono">{fmtAny(s.value)}</strong>
              </div>
              <dl className="d-setting__facts">
                <div><dt>Limits</dt><dd>{fmtAny(s.limits)}</dd></div>
                <div><dt>Owner</dt><dd>{s.owner ? humanize(s.owner) : 'Not stated'}</dd></div>
                <div><dt>Why</dt><dd>{s.why ?? 'Not stated'}</dd></div>
                <div><dt>If raised</dt><dd>{s.if_raised ?? 'Not stated'}</dd></div>
              </dl>
            </article>
          ))}
          {!rules.settings?.length && <p className="d-small d-muted">No settings in this export.</p>}
        </div>
      </section>

      <section className="d-section">
        <SectionHeading title="Decision table" description="Read from the top. The first row that matches wins." />
        <ol className="d-dtable">
          {DECISION_TABLE.map((row) => (
            <li key={row.row} className="d-dtable__row">
              <span className="d-dtable__n">{row.row}</span>
              <span className="d-dtable__when">{row.when}</span>
              <span className="d-dtable__goes">{row.goes}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="d-section">
        <SectionHeading title="Evidence map" description="What counts as proof, and which requirement each kind of proof can meet." />
        <div className="d-two">
          <article className="d-panel">
            <h3 className="d-h4">Requirements</h3>
            <RuleItems items={rules.requirements} empty="None in this export." />
          </article>
          <article className="d-panel">
            <h3 className="d-h4">Does not count as proof</h3>
            <RuleItems items={rules.does_not_count} empty="None in this export." />
          </article>
        </div>
        <article className="d-panel">
          <h3 className="d-h4">Kinds of proof</h3>
          <RuleItems items={rules.evidence_types} empty="None in this export." />
        </article>
        <article className="d-panel">
          <h3 className="d-h4">Hazards</h3>
          <RuleItems items={rules.hazards} empty="None in this export." />
        </article>
      </section>

      <section className="d-section">
        <SectionHeading title="Ordinance" meta={<StatusBadge status="draft">Invented for this demo</StatusBadge>} />
        <ul className="d-ordinance">
          {(rules.ordinance ?? []).map((c) => (
            <li key={c.id}>
              <span className="d-clause d-clause--static">{c.id}</span>
              <span>{c.text}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

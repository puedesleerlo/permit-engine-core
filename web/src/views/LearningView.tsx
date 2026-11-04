import { useMemo } from 'react';
import { Button, DataTable, Icon, NoteBox, SectionHeading, StatCallout, StatusBadge } from '@permit-engine/ui';
import { LevelBar, levelNumbers } from '../components/LevelBar';
import { LearningPlot, type PlotSeries } from '../components/LearningPlot';
import { fmtAny } from '../components/RuleItems';
import { useAtEnd, useDemo, useLearningIndex } from '../replay';
import type { Arm, CurvePoint, FinalTest, LearningTree } from '../types';
import { fmtCount, humanize, num, pct, treeName } from '../words';
import { RIGHT_LEVEL_MEANS, STEADY_NOTE, changeTrend, rightLevelDomain, useCurrentCards } from './ReplayView';

const WORDS: Record<string, string[]> = { likelihood: ['rare', 'possible', 'likely'], severity: ['minor', 'serious', 'critical'] };

function Plot({ title, note, field, domain, ticks, format, height }: {
  title: string; note: string; field: keyof CurvePoint; domain: [number, number]; ticks: number[]; format: (v: number) => string; height?: number;
}) {
  const { data, timeline } = useDemo();
  const li = useLearningIndex();
  const curve = data.learning.curve;
  const xs = useMemo(() => curve.map((p) => p.corrections), [curve]);
  const series = useMemo<PlotSeries[]>(() => [{ key: String(field), label: title, tone: 'main', values: curve.map((p) => Number(p[field] ?? 0)), format }], [curve, field, title, format]);
  return (
    <article className="d-panel">
      <h3 className="d-h4">{title}</h3>
      <LearningPlot xs={xs} series={series} reached={li} markers={timeline.rechosenCurve} yDomain={domain} yTicks={ticks} yFormat={format} height={height} label={title} />
      <p className="d-caption">{note}</p>
    </article>
  );
}

const missing = (a: Arm) => (a.status === 'not_run' ? 'Not run yet' : 'Not measured');
const armValue = (a: Arm, v: number | null | undefined, format: (x: number) => string) => (v === null || v === undefined ? missing(a) : format(v));
const armInterval = (a: Arm) => (a.interval && a.interval[0] !== null && a.interval[1] !== null ? `${pct(a.interval[0])} to ${pct(a.interval[1])}` : missing(a));

function ArmsTable({ arms }: { arms: Arm[] }) {
  return (
    <>
    <ul className="d-armcards">
      {arms.map((a) => (
        <li key={a.name} className="d-panel">
          <h4 className="d-h4">{a.name}</h4>
          <dl className="d-ruling__facts d-armfacts">
            <div><dt>Right level</dt><dd className="d-mono">{armValue(a, a.right_level, (v) => pct(v))}</dd></div>
            <div><dt>Loss</dt><dd className="d-mono">{armValue(a, a.loss, (v) => num(v, 2))}</dd></div>
            <div><dt>Approved</dt><dd className="d-mono">{armValue(a, a.approved, (v) => pct(v))}</dd></div>
            <div><dt>Risky among approved</dt><dd className="d-mono">{a.risky_among_approved === null || a.risky_among_approved === undefined ? missing(a) : `${pct(a.risky_among_approved)}, ${armInterval(a)}`}</dd></div>
          </dl>
        </li>
      ))}
    </ul>
    <div className="d-armtable">
    <DataTable
      caption={arms[0]?.split === 'test' ? 'Each approach compared on the sealed test cases' : 'Each approach compared on set-aside validation cases'}
      rows={arms.map((a) => ({ ...a, id: a.name }))}
      density="compact"
      columns={[
        { key: 'name', header: 'Approach' },
        { key: 'right_level', header: 'Right level', align: 'right', mono: true, render: (a) => armValue(a, a.right_level, (v) => pct(v)) },
        { key: 'loss', header: 'Loss', align: 'right', mono: true, render: (a) => armValue(a, a.loss, (v) => num(v, 2)) },
        { key: 'approved', header: 'Approved', align: 'right', mono: true, render: (a) => armValue(a, a.approved, (v) => pct(v)) },
        { key: 'risky', header: 'Risky among approved', align: 'right', mono: true, render: (a) => armValue(a, a.risky_among_approved, (v) => pct(v)) },
        { key: 'interval', header: '95% interval', align: 'right', mono: true, render: armInterval },
      ]}
    />
    </div>
    </>
  );
}

function FinalTestBlock({ test }: { test?: FinalTest | null }) {
  const notRun = !test || test.status === 'not_run' || test.verdict === null;
  const passed = !notRun && /pass/i.test(test!.verdict as string);
  return (
    <article className="d-panel">
      <div className="d-group__head">
        <h3 className="d-h3">Final test</h3>
        {notRun
          ? <StatusBadge status="draft">Not run yet</StatusBadge>
          : <StatusBadge status={passed ? 'approved' : 'rejected'}>{passed ? 'Passed' : 'Failed'}</StatusBadge>}
      </div>
      <p className="d-small d-muted">
        Sealed cases, looked at once. It passes if the trained trees beat the first guess and the shuffled control on loss, approve more than the first guess, and the test does not clearly show risky approvals above 5%. Jev asked directly is reported and is not part of the rule.
      </p>
      {notRun && <p className="d-body">Not run yet.</p>}
      {(test?.conditions?.length ?? 0) > 0 && (
        <ul className="d-conditions">
          {test!.conditions!.map((c) => (
            <li key={c.name}>
              {c.passed === null || c.passed === undefined
                ? <Icon name="clock" size={18} />
                : c.passed ? <span className="d-yes"><Icon name="check-circle" size={18} /></span> : <span className="d-no"><Icon name="x-circle" size={18} /></span>}
              <div>
                <strong>{c.name}</strong>
                {c.detail && <p className="d-small d-muted">{c.detail}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {!notRun && (
        <dl className="d-ruling__facts">
          <div><dt>Forbidden permits</dt><dd className="d-mono">{test!.forbidden_permits === null || test!.forbidden_permits === undefined ? 'Not measured' : fmtAny(test!.forbidden_permits)}</dd></div>
          <div><dt>Risky approvals</dt><dd className="d-mono">{test!.risky_approvals === null || test!.risky_approvals === undefined ? 'Not measured' : fmtAny(test!.risky_approvals)}</dd></div>
        </dl>
      )}
    </article>
  );
}

function TreeTable({ tree }: { tree: LearningTree }) {
  const scale = tree.tree_id.split('.').pop() ?? '';
  const names = WORDS[scale];
  const questions = Object.keys(tree.leaves[0]?.when ?? {});
  return (
    <article className={`d-panel${tree.flagged ? ' d-panel--flagged' : ''}`}>
      <div className="d-group__head">
        <h3 className="d-h4">{treeName(tree.tree_id)}</h3>
        {tree.flagged && <StatusBadge status="action-required">Flagged</StatusBadge>}
      </div>
      <p className="d-small d-muted">
        How mixed its leaves are on average (mean entropy): <span className="d-mono">{num(tree.mean_leaf_entropy, 2)}</span>. Loss: <span className="d-mono">{num(tree.loss, 2)}</span>.
        {questions.length > 0 && <> Answers in order: {questions.map((q) => humanize(q).toLowerCase()).join(', ')}.</>}
        {names && <> Splits read {names.join(' / ')}.</>}
      </p>
      {tree.flagged && (
        <p className="d-small">
          Flagged because its leaves are the most mixed of all the trees. Cases that reach the same leaf end up at different levels, which points to a question this tree does not ask. High entropy is a reason to look, not proof.
        </p>
      )}
      <DataTable
        caption={`${treeName(tree.tree_id)} leaves`}
        density="compact"
        rows={tree.leaves.map((l, i) => ({ ...l, id: String(i) }))}
        columns={[
          { key: 'when', header: 'Answers', render: (l) => <span className="d-small">{questions.map((q) => (l.when[q] ? 'Yes' : 'No')).join(', ')}</span> },
          { key: 'first', header: 'First guess', render: (l) => <span className="d-split"><LevelBar compact levels={l.levels_first} names={names} /><span className="d-mono">{levelNumbers(l.levels_first)}</span></span> },
          { key: 'now', header: 'Now', render: (l) => <span className="d-split"><LevelBar compact levels={l.levels_now} names={names} /><span className="d-mono">{levelNumbers(l.levels_now)}</span></span> },
          { key: 'count', header: 'Count', align: 'right', mono: true, render: (l) => fmtCount(l.count) },
          { key: 'entropy', header: 'Entropy', align: 'right', mono: true, render: (l) => num(l.entropy, 2) },
        ]}
      />
    </article>
  );
}

export function LearningView() {
  const { data, video, replay } = useDemo();
  const atEnd = useAtEnd();
  const li = useLearningIndex();
  const { rightLevel, decided, precision, first, point } = useCurrentCards();
  const { learning } = data;
  const curve = learning.curve;
  const trees = useMemo(() => [...(learning.trees ?? [])].sort((a, b) => Number(b.flagged) - Number(a.flagged)), [learning.trees]);
  const lossMax = useMemo(() => {
    const top = Math.max(1, ...curve.map((p) => p.loss));
    return Math.ceil(top * 4) / 4;
  }, [curve]);
  const lossTicks = useMemo(() => [0, lossMax / 2, lossMax], [lossMax]);
  const rise = rightLevel !== null && first.rightLevel !== null ? Math.round((rightLevel - first.rightLevel) * 100) : 0;
  const rightDomain = useMemo(() => rightLevelDomain(curve), [curve]);
  const rightTicks = useMemo(() => [rightDomain[0], (rightDomain[0] + rightDomain[1]) / 2, rightDomain[1]], [rightDomain]);

  return (
    <div className="d-page">
      <SectionHeading
        level="page"
        layout="plain"
        title="Learning"
        description="Teaching starts from a rough first guess, and every officer review teaches. This page follows the replay, so the plots stop at the point it has reached."
      />
      <div className="d-statrow">
        <StatCallout value={pct(rightLevel)} label={`Right risk level. ${RIGHT_LEVEL_MEANS}`} trend={changeTrend(rise, first.rightLevel)} />
        <StatCallout value={num(point?.loss, 2)} label={`Loss after ${point?.corrections ?? 0} officer reviews. Lower is better.`} />
        <StatCallout value={pct(decided)} label="Decided without an officer" />
        <StatCallout value={pct(precision)} label="Precision: the share of automatic approvals not labelled risky" />
      </div>
      <p className="d-small d-muted d-steadynote">Decided without an officer and precision: {STEADY_NOTE.charAt(0).toLowerCase() + STEADY_NOTE.slice(1)}</p>

      <section className="d-section">
        <SectionHeading title="Across officer reviews" meta={`Point ${li + 1} of ${curve.length}`} />
        <div className="d-legend">
          <span className="d-legend__item"><i className="d-markerkey" />Thresholds re-chosen</span>
          <span className="d-small d-muted">The bottom axis counts officer reviews.</span>
        </div>
        <div className="d-plots">
          <Plot title="Right risk level" note="This is the number that rises. It counts how often a tree's most likely level is the experts' level, on set-aside cases." field="right_level" domain={rightDomain} ticks={rightTicks} format={(v) => pct(v)} />
          <Plot title="Loss" note="How wrong the trees' predictions are on set-aside cases. Lower is better." field="loss" domain={[0, lossMax]} ticks={lossTicks} format={(v) => v.toFixed(2)} />
          <Plot title="Decided without an officer" note="Stays near flat. About a third of cases can never be decided automatically." field="decided_without_officer" domain={[0, 1]} ticks={[0, 0.5, 1]} format={(v) => pct(v)} />
          <Plot title="Precision" note="Stays near its target, because thresholds are re-chosen to hold it there." field="precision" domain={[0, 1]} ticks={[0, 0.5, 1]} format={(v) => pct(v)} />
        </div>
        <details className="d-doc">
          <summary>
            <Icon name="filter" size={18} />
            <span>Show these numbers as a table</span>
            <Icon name="chevron-down" size={16} className="d-doc__chev" />
          </summary>
          <div className="d-tablewrap d-pad">
            <table className="d-table d-table--num">
              <thead><tr><th>Officer reviews</th><th>Right risk level</th><th>Decided without an officer</th><th>Precision</th><th>Loss</th><th>t_low</th><th>t_high</th><th>Set-aside cases</th></tr></thead>
              <tbody>
                {curve.slice(0, li + 1).map((p) => (
                  <tr key={p.index}>
                    <td className="d-mono">{p.corrections}</td>
                    <td className="d-mono">{pct(p.right_level, 1)}</td>
                    <td className="d-mono">{pct(p.decided_without_officer, 1)}</td>
                    <td className="d-mono">{pct(p.precision, 1)}</td>
                    <td className="d-mono">{num(p.loss, 2)}</td>
                    <td className="d-mono">{num(p.t_low, 2)}</td>
                    <td className="d-mono">{num(p.t_high, 2)}</td>
                    <td className="d-mono">{p.held_out_cases ?? 'Not recorded'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="d-section">
        <NoteBox title="What corrections cannot change" icon="shield">
          <p>
            Officer reviews and corrections move leaf weights and nothing else. They cannot change the rules (the ordinance and decision table), the anchors (the number each level stands for) or the targets thresholds aim at. Thresholds are re-chosen to meet those targets, and only a person can change a target.
          </p>
        </NoteBox>
      </section>

      <section className="d-section">
        <SectionHeading title="Results from the finished run" description="The comparison of approaches, the final test and the current weights belong to the end of the run." />
        {!atEnd ? (
          <div className="d-notyet d-gate">
            <p>These appear when the replay reaches the end.</p>
            {!video && <Button size="sm" onClick={replay.jumpToEnd}>Jump to end</Button>}
          </div>
        ) : (
          <div className="d-stack d-stack--lg">
            <div className="d-stack">
              <h3 className="d-h3">How each approach compares</h3>
              {(learning.arms?.length ?? 0) > 0 ? <ArmsTable arms={learning.arms!} /> : <p className="d-small d-muted">No comparison in this export.</p>}
              <p className="d-caption">The interval is on the share of risky approvals. Loss says how wrong each approach's predictions are, and lower is better. All of these are scored against labels written by the author, which the trees trained on and Jev never saw, so this measures agreement with those labels and not real risk.</p>
              {(() => {
                const baseline = learning.arms?.find((a) => a.right_route_share !== null && a.right_route_share !== undefined);
                return baseline ? <p className="d-caption">The one-LLM baseline read the ordinance strictly and approved few cases. It matched the labelled right route on {pct(baseline.right_route_share!)} of cases. It gives no probabilities, so it has no loss or right level.</p> : null;
              })()}
            </div>
            <FinalTestBlock test={learning.final_test} />
            {learning.tone && (
              <div className="d-stack">
                <h3 className="d-h3">Does the tone of a cover letter change the decision?</h3>
                <p className="d-small">{learning.tone.requests} test requests were each rewritten in three more tones: persuasive, insistent, and name-dropping the mayor. The decision changed in {learning.tone.decision_flips} of {learning.tone.compared} comparisons.</p>
                <p className="d-small d-muted">What the reader extracted changed in {Math.min(...Object.values(learning.tone.evidence_flips))} to {Math.max(...Object.values(learning.tone.evidence_flips))} of {learning.tone.requests} requests per tone. Reading the same plain letters a second time changed {learning.tone.noise_evidence_flips ?? 'an unmeasured number'} of {learning.tone.requests}, so with this few cases those changes cannot be told apart from ordinary noise. A test this small also cannot rule out a small effect on decisions.</p>
              </div>
            )}
            <div className="d-stack">
              <h3 className="d-h3">Each tree's leaves</h3>
              <p className="d-small d-muted">First-guess and current weights side by side. Count is how many cases stand behind the leaf, starting from a small assumed number. Entropy is how mixed its outcomes are: 0 means all one level, 1.10 means an even three-way split.</p>
              {learning.crossings && (
                <article className="d-panel">
                  <div className="d-group__head">
                    <h3 className="d-h4">The crossings question</h3>
                    <StatusBadge status={learning.crossings.status === 'released' ? 'approved' : 'in-review'}>{learning.crossings.status === 'released' ? 'Released' : 'Proposed'}</StatusBadge>
                  </div>
                  <p className="d-small">{learning.crossings.text}</p>
                  <p className="d-small d-muted">Traffic likelihood loss on validation cases: <span className="d-mono">{num(learning.crossings.loss_before, 2)}</span> before, <span className="d-mono">{num(learning.crossings.loss_after, 2)}</span> after.</p>
                </article>
              )}
              <div className="d-treetables">
                {trees.map((t) => <TreeTable key={t.tree_id} tree={t} />)}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

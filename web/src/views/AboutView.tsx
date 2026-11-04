import { Icon, KeyValueList, SectionHeading } from '@permit-engine/ui';
import { Tag } from '../components/Tag';
import { useDemo } from '../replay';
import { SOURCE_NOTE, fmtDateTime } from '../words';

const ARCHITECTURE_URL = 'https://puedesleerlo.github.io/permit-engine/';

export function AboutView() {
  const { data } = useDemo();
  const m = data.manifest;
  return (
    <div className="d-page d-about">
      <SectionHeading
        level="page"
        layout="plain"
        title="About this demo"
        description="Permit Engine splits a permit decision into parts a person can check. This page says what you are looking at, and what it does not show."
      />

      <section className="d-section">
        <SectionHeading title="What is synthetic, simulated and stored" />
        <div className="d-three">
          <article className="d-panel">
            <p><Tag kind="synthetic" /></p>
            <p className="d-small">Every application, organiser, document and race. A script wrote them. The ordinance is invented as well.</p>
          </article>
          <article className="d-panel">
            <p><Tag kind="simulated" /></p>
            <p className="d-small">The officer, and the clock. {m.source === 'simulated' ? SOURCE_NOTE.simulated : ''} This run's source is <span className="d-mono">{m.source}</span>.</p>
          </article>
          <article className="d-panel">
            <p><Tag kind="stored" /></p>
            <p className="d-small">The whole run. It finished ahead of time and your browser replays it. {m.source === 'real' ? SOURCE_NOTE.real : ''} Nothing is computed on a server while you watch, and no keys are involved.</p>
          </article>
        </div>
      </section>

      <section className="d-section">
        <SectionHeading title="An LLM stands in for the officer" />
        <div className="d-prose">
          <p>In this demo an agentic LLM stands in for the officer, given the expert rubric in words and asked for a ruling and a one-line reason. In this run it is labelled "{m.officer_label}". Its measured accuracy is on the officer rulings page.</p>
          <p>A real deployment would use a person. The stand-in is here so you can watch corrections arrive without a person in the room.</p>
        </div>
      </section>

      <section className="d-section">
        <SectionHeading title="Every review teaches" />
        <div className="d-prose">
          <p>Every officer review moves the weights, whether the officer agrees with the system or not. A review that disagrees is still shown as a correction.</p>
          <p>Teaching from corrections alone was tried, and it made things worse. A system that learns only from its mistakes gets a skewed view of the cases it sees.</p>
        </div>
      </section>

      <section className="d-section">
        <SectionHeading title="What this does not prove" />
        <div className="d-prose">
          <p>The labels were written by the author. When training recovers them, that shows the mechanism works. It does not show that the levels describe real events, or that the system would be safe on real applications.</p>
          <p>Precision and risky approvals are measured against those same labels. On this many cases, the intervals are wide.</p>
        </div>
      </section>

      <section className="d-section">
        <SectionHeading title="How it is built" />
        <div className="d-prose">
          <p>The architecture is on its own page: <a href={ARCHITECTURE_URL} rel="noreferrer" target="_blank">{ARCHITECTURE_URL} <Icon name="external" size={14} /></a></p>
        </div>
      </section>

      <section className="d-section">
        <SectionHeading title="This run" />
        <div className="d-panel">
          <KeyValueList columns={2} items={[
            { label: 'Run', value: m.run_id, mono: true },
            { label: 'Finished', value: fmtDateTime(m.created_at) },
            { label: 'Applications', value: String(m.case_count), mono: true },
            { label: 'Events', value: String(m.event_count), mono: true },
            { label: 'Answers', value: m.source, mono: true },
            { label: 'Jev version', value: m.jev_model ?? 'Not recorded', mono: true },
          ]} />
          {(m.notes?.length ?? 0) > 0 && (
            <ul className="d-notes">{m.notes!.map((n) => <li key={n} className="d-small d-muted">{n}</li>)}</ul>
          )}
        </div>
      </section>
    </div>
  );
}

import { Button } from '@permit-engine/ui';
import { useDemo, useReplayValue, SPEEDS } from '../replay';
import { EVENT_STAGE } from '../words';
import { EndGlyph, PauseGlyph, PlayGlyph, RestartGlyph } from './ReplayIcons';

export function PositionLabel() {
  const { timeline } = useDemo();
  const submitted = useReplayValue((s, t) => t.submittedAt[s.index] ?? 0);
  const type = useReplayValue((s, t) => t.events[s.index]?.type ?? '');
  const atEnd = useReplayValue((s, t) => s.index >= t.lastIndex);
  const total = timeline.cases.length;
  return (
    <span className="d-position" aria-live="off">
      <span className="d-position__main">Case {submitted} of {total}</span>
      <span className="d-position__sub">{atEnd ? 'End of the run' : EVENT_STAGE[type] ?? type}</span>
    </span>
  );
}

export function ReplayButtons() {
  const { replay } = useDemo();
  const playing = useReplayValue((s) => s.playing);
  const speed = useReplayValue((s) => s.speed);
  const atEnd = useReplayValue((s, t) => s.index >= t.lastIndex);
  const speeds = SPEEDS.includes(speed) ? SPEEDS : [...SPEEDS, speed].sort((a, b) => a - b);
  return (
    <div className="d-controls" role="group" aria-label="Replay controls">
      <Button size="sm" variant="primary" onClick={replay.toggle} aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? <PauseGlyph /> : <PlayGlyph />}
        <span className="d-btn-text">{playing ? 'Pause' : 'Play'}</span>
      </Button>
      <label className="d-speed">
        <span className="d-btn-text">Speed</span>
        <select aria-label="Speed" value={speed} onChange={(e) => replay.setSpeed(Number(e.target.value))}>
          {speeds.map((s) => <option key={s} value={s}>{s}x</option>)}
        </select>
      </label>
      <Button size="sm" variant="secondary" onClick={replay.restart} aria-label="Restart">
        <RestartGlyph />
        <span className="d-btn-text">Restart</span>
      </Button>
      <Button size="sm" variant="secondary" onClick={replay.jumpToEnd} disabled={atEnd} aria-label="Jump to end">
        <EndGlyph />
        <span className="d-btn-text">Jump to end</span>
      </Button>
    </div>
  );
}

/** The whole run as a track. Drag it to move through the replay. Small marks are the officer's corrections. */
export function ReplayTrack({ readOnly }: { readOnly?: boolean }) {
  const { replay, timeline } = useDemo();
  const index = useReplayValue((s) => s.index);
  const last = Math.max(1, timeline.lastIndex);
  const done = (index / last) * 100;
  return (
    <div className="d-track" style={{ '--d-done': `${done}%` } as React.CSSProperties}>
      <div className="d-track__rail" aria-hidden>
        <div className="d-track__fill" />
        {timeline.correctionIndexes.map((i) => (
          <i key={i} className={`d-track__tick${i <= index ? ' is-past' : ''}`} style={{ left: `${(i / last) * 100}%` }} />
        ))}
      </div>
      {!readOnly && (
        <input
          type="range"
          min={0}
          max={timeline.lastIndex}
          value={index}
          aria-label="Position in the replay"
          aria-valuetext={`Event ${index + 1} of ${timeline.lastIndex + 1}`}
          onChange={(e) => replay.seek(Number(e.target.value))}
        />
      )}
    </div>
  );
}

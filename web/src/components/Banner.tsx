import { useDemo } from '../replay';
import { SOURCE_NOTE } from '../words';

export function Banner() {
  const { data } = useDemo();
  const { source } = data.manifest;
  return (
    <aside className="d-banner" aria-label="About this data">
      <strong>All applications are synthetic.</strong>{' '}
      <span>Source: <span className="d-mono">{source}</span>.</span>{' '}
      {SOURCE_NOTE[source] && <span>{SOURCE_NOTE[source]}</span>}
    </aside>
  );
}

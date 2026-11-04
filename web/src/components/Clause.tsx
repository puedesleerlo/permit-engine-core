import { Tooltip } from '@permit-engine/ui';
import { useDemo } from '../replay';

export function useClauseText() {
  const { data } = useDemo();
  return (id: string) => data.rules.ordinance?.find((c) => c.id === id)?.text ?? null;
}

/** A clause code. Hovering or focusing it shows the clause in plain words. */
export function Clause({ id }: { id?: string | null }) {
  const text = useClauseText();
  if (!id) return null;
  const words = text(id);
  if (!words) return <span className="d-clause d-clause--static">{id}</span>;
  return (
    <Tooltip content={words}>
      <button type="button" className="d-clause">{id}</button>
    </Tooltip>
  );
}

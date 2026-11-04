import { StatusBadge } from '@permit-engine/ui';
import { routeBadge } from '../words';

export function RouteBadge({ route }: { route: string }) {
  const r = routeBadge(route);
  return <StatusBadge status={r.status}>{r.label}</StatusBadge>;
}

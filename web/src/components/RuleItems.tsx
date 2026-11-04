import { humanize } from '../words';

export function fmtAny(v: unknown): string {
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v)) return v.map((x) => (x && typeof x === 'object' && 'name' in x ? humanize(String((x as { name: unknown }).name)).toLowerCase() : fmtAny(x))).join(', ');
  if (typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${humanize(k).toLowerCase()} ${fmtAny(x)}`).join(', ');
  return String(v);
}

const PLAIN_TITLES = ['name', 'label', 'title', 'what'];
const TITLE_KEYS = [...PLAIN_TITLES, 'id', 'key', 'evidence_type'];
const INTERNAL_KEYS = new Set(['id', 'applies_rule', 'trees', 'whole_document']);

/** The contract does not fix the shape of these lists, so strings and objects are both shown plainly. */
export function RuleItems({ items, empty }: { items?: unknown[] | null; empty: string }) {
  if (!items?.length) return <p className="d-muted d-small">{empty}</p>;
  return (
    <ul className="d-ruleitems">
      {items.map((item, i) => {
        if (typeof item !== 'object' || item === null) return <li key={i}>{String(item)}</li>;
        const rec = item as Record<string, unknown>;
        const titleKey = TITLE_KEYS.find((k) => rec[k]);
        const title = titleKey ? String(rec[titleKey]) : `Item ${i + 1}`;
        const rest = Object.entries(rec).filter(([k]) => k !== titleKey && !INTERNAL_KEYS.has(k));
        return (
          <li key={i}>
            <strong>{titleKey && PLAIN_TITLES.includes(titleKey) ? title : humanize(title)}</strong>
            {rest.length > 0 && (
              <dl>
                {rest.map(([k, v]) => (
                  <div key={k}>
                    <dt>{humanize(k)}</dt>
                    <dd>{fmtAny(v)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        );
      })}
    </ul>
  );
}

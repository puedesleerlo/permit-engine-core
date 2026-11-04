import type { ReactNode } from 'react';

const escapeForRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function findQuote(text: string, quote: string): [number, number] | null {
  const exact = text.indexOf(quote);
  if (exact >= 0) return [exact, exact + quote.length];
  const words = quote.trim().split(/\s+/).map(escapeForRegex);
  if (!words.length || !words[0]) return null;
  const match = new RegExp(words.join('\\s+'), 'i').exec(text);
  return match ? [match.index, match.index + match[0].length] : null;
}

/** The text with every quote marked. Quotes that overlap are merged. */
export function Highlighted({ text, quotes }: { text: string; quotes: string[] }) {
  const ranges = quotes
    .map((q) => findQuote(text, q))
    .filter((r): r is [number, number] => r !== null)
    .sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const top = merged[merged.length - 1];
    if (top && r[0] <= top[1]) top[1] = Math.max(top[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  const out: ReactNode[] = [];
  let at = 0;
  merged.forEach(([a, b], i) => {
    if (a > at) out.push(text.slice(at, a));
    out.push(<mark key={i}>{text.slice(a, b)}</mark>);
    at = b;
  });
  if (at < text.length) out.push(text.slice(at));
  return <>{out}</>;
}

/** A window of the text around the first quote, widened to whole lines. Short documents come back whole. */
export function excerptAround(text: string, quotes: string[], limit = 520): { text: string; cutStart: boolean; cutEnd: boolean } {
  if (text.length <= limit) return { text, cutStart: false, cutEnd: false };
  const found = quotes.map((q) => findQuote(text, q)).filter((r): r is [number, number] => r !== null);
  if (!found.length) return { text: text.slice(0, limit), cutStart: false, cutEnd: true };
  const from = Math.min(...found.map((r) => r[0]));
  const to = Math.max(...found.map((r) => r[1]));
  const spare = Math.max(80, (limit - (to - from)) / 2);
  let start = Math.max(0, from - spare);
  let end = Math.min(text.length, to + spare);
  const lineStart = text.lastIndexOf('\n', from);
  if (lineStart >= start) start = lineStart + 1;
  const lineEnd = text.indexOf('\n', to);
  if (lineEnd >= 0 && lineEnd <= end) end = lineEnd;
  return { text: text.slice(start, end), cutStart: start > 0, cutEnd: end < text.length };
}

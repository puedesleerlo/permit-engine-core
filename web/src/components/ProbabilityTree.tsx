import { memo } from 'react';
import type { TreeEval, TreeLeaf, TreeQuestion } from '../types';
import { fmtCount, pct } from '../words';
import { levelNumbers } from './LevelBar';
import { useWidth } from './useWidth';

interface LeafNode {
  kind: 'leaf';
  leaf: TreeLeaf | null;
  reach: number;
  y: number;
  main: boolean;
}
interface QuestionNode {
  kind: 'question';
  question: TreeQuestion;
  number: number;
  yes: TreeNode;
  no: TreeNode;
  reach: number;
  y: number;
  main: boolean;
}
type TreeNode = LeafNode | QuestionNode;

const ROW = 64;
const TOP = 6;

function build(tree: TreeEval): { root: TreeNode; rows: number } {
  let row = 0;
  const walk = (depth: number, fixed: Record<string, boolean>): TreeNode => {
    if (depth >= tree.questions.length) {
      const leaf = tree.leaves.find((l) => Object.entries(fixed).every(([k, v]) => l.when?.[k] === v)) ?? null;
      const y = TOP + (row + 0.5) * ROW;
      row += 1;
      return { kind: 'leaf', leaf, reach: leaf?.reach ?? 0, y, main: false };
    }
    const question = tree.questions[depth];
    const yes = walk(depth + 1, { ...fixed, [question.id]: true });
    const no = walk(depth + 1, { ...fixed, [question.id]: false });
    return { kind: 'question', question, number: depth + 1, yes, no, reach: yes.reach + no.reach, y: (yes.y + no.y) / 2, main: false };
  };
  const root = walk(0, {});
  const mark = (n: TreeNode) => {
    n.main = true;
    if (n.kind === 'question') mark(n.yes.reach >= n.no.reach ? n.yes : n.no);
  };
  mark(root);
  return { root, rows: row };
}

function Levels({ x, y, width, levels }: { x: number; y: number; width: number; levels: number[] }) {
  const gap = 2;
  const parts = levels.filter((p) => p > 0).length;
  const usable = width - gap * Math.max(0, parts - 1);
  const total = levels.reduce((s, p) => s + p, 0) || 1;
  let cursor = x;
  return (
    <g>
      {levels.map((p, i) => {
        if (p <= 0) return null;
        const w = (p / total) * usable;
        const rect = <rect key={i} x={cursor} y={y} width={Math.max(w, 1)} height={10} rx={2} className={`d-level-${i}`} />;
        cursor += w + gap;
        return rect;
      })}
    </g>
  );
}

/** Draws a tree's questions, how much of this case flowed down each branch, and what each leaf holds. */
export const ProbabilityTree = memo(function ProbabilityTree({ tree }: { tree: TreeEval }) {
  const [ref, measured] = useWidth<HTMLDivElement>(420);
  const width = Math.max(260, measured);
  const narrow = width < 460;
  const depth = tree.questions.length;
  const col = narrow ? (depth > 2 ? 48 : 62) : 88;
  const shortLabels = col < 56;
  const startX = 14;
  const leafX = startX + depth * col + 8;
  const leafW = Math.min(width - leafX - 2, 320);
  const { root, rows } = build(tree);
  const height = TOP * 2 + rows * ROW;

  const branches: JSX.Element[] = [];
  const nodes: JSX.Element[] = [];
  const leaves: JSX.Element[] = [];

  const visit = (n: TreeNode, depthAt: number) => {
    const x = startX + depthAt * col;
    if (n.kind === 'leaf') {
      if (!n.leaf) return;
      const faint = n.reach < 0.005;
      const names = tree.level_names;
      leaves.push(
        <g key={`leaf-${n.y}`} className={`d-tree__leaf${faint ? ' is-faint' : ''}${n.main ? ' is-main' : ''}`}>
          <text x={leafX} y={n.y - 11} className="d-tree__reach">{pct(n.reach)} of {narrow ? 'case' : 'this case'}</text>
          <text x={leafX + leafW} y={n.y - 11} textAnchor="end" className="d-tree__count">count {fmtCount(n.leaf.count)}</text>
          <Levels x={leafX} y={n.y - 5} width={leafW} levels={n.leaf.levels} />
          <text x={leafX} y={n.y + 19} className="d-tree__split">
            {narrow ? `${levelNumbers(n.leaf.levels)} %` : n.leaf.levels.map((p, i) => `${Math.round(p * 100)}% ${names[i] ?? ''}`).join(', ')}
          </text>
        </g>,
      );
      return;
    }
    const answer = n.question.answer;
    const draw = (child: TreeNode, isYes: boolean) => {
      const childX = startX + (depthAt + 1) * col;
      const share = isYes ? answer : 1 - answer;
      const mid = x + (childX - x) * 0.45;
      const dead = child.reach < 0.005;
      const main = n.main && child.main;
      branches.push(
        <path
          key={`b-${n.y}-${isYes}`}
          d={`M ${x} ${n.y} C ${mid} ${n.y}, ${mid} ${child.y}, ${childX} ${child.y}`}
          className={`d-tree__branch${main ? ' is-main' : ''}${dead ? ' is-dead' : ''}`}
          strokeWidth={dead ? 1 : 1.5 + 9 * child.reach}
        />,
      );
      const word = shortLabels ? (isYes ? 'Y' : 'N') : isYes ? 'yes' : 'no';
      const toNode = child.kind === 'question';
      nodes.push(
        <text key={`l-${n.y}-${isYes}`} x={toNode ? childX + 2 : childX - 3} y={child.y + (isYes ? (toNode ? -15 : -9) : toNode ? 24 : 15)} textAnchor="end" className={`d-tree__answer${dead ? ' is-dead' : ''}`}>
          {word} {pct(share)}
        </text>,
      );
      visit(child, depthAt + 1);
    };
    draw(n.yes, true);
    draw(n.no, false);
    nodes.push(
      <g key={`n-${n.y}-${depthAt}`} className={`d-tree__node${n.main ? ' is-main' : ''}${n.reach < 0.005 ? ' is-dead' : ''}`}>
        <circle cx={x} cy={n.y} r={11} />
        <text x={x} y={n.y + 4} textAnchor="middle">{n.number}</text>
      </g>,
    );
  };
  visit(root, 0);

  const mainLeaf = tree.leaves.reduce<TreeLeaf | null>((best, l) => (!best || l.reach > best.reach ? l : best), null);
  const summary = `${tree.questions.map((q, i) => `Question ${i + 1}: ${q.text} Yes ${pct(q.answer)}.`).join(' ')} Most of this case, ${pct(mainLeaf?.reach)}, reached one leaf, with a count of ${fmtCount(mainLeaf?.count)}.`;

  return (
    <div ref={ref} className="d-tree">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
        {branches}
        {leaves}
        {nodes}
      </svg>
    </div>
  );
});

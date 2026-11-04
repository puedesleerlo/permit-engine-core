// The export contract in docs/designs/demo-build.md. Optional and nullable fields are read defensively.

export interface Manifest {
  run_id: string;
  created_at: string;
  source: 'simulated' | 'real' | string;
  synthetic: boolean;
  officer_label: string;
  jev_model?: string | null;
  case_count: number;
  event_count: number;
  officer_accuracy?: number | null;
  notes?: string[] | null;
}

export type EventType =
  | 'case.submitted' | 'checks.done' | 'evidence.linked' | 'evidence.judged' | 'requirements.checked'
  | 'hazards.screened' | 'trees.evaluated' | 'risk.computed' | 'decision.made' | 'officer.ruled'
  | 'correction.made' | 'weights.updated' | 'thresholds.rechosen' | 'permit.issued' | 'change.released';

export interface ReplayEvent {
  seq: number;
  sim_time: string;
  case_id: string | null;
  type: EventType | string;
  actor: string;
  simulated: boolean;
  summary: string;
  learning_index?: number;
}

export type Route = 'approved' | 'returned' | 'proposed_denial' | 'officer';

export interface CaseRow {
  case_id: string;
  title: string;
  first_seq: number;
  decided_seq: number;
  route: Route | string;
  reason_code: string;
  row: number;
  risk: number | null;
  t_low: number | null;
  t_high: number | null;
  weights_version?: string | null;
  officer: boolean;
  corrected: boolean;
  label_risky: boolean;
  agreed_with_label: boolean;
}

export interface EvidenceField {
  name: string;
  value: unknown;
  quote?: string | null;
  verified?: boolean | null;
  matches_form?: boolean | null;
}

export interface EvidenceRecord {
  evidence_type: string;
  status: 'found' | 'absent' | string;
  document?: string | null;
  fields?: EvidenceField[] | null;
  verdict?: 'supported' | 'unsupported' | 'contradicted' | string | null;
  reason?: string | null;
  source?: string | null;
}

export interface TreeQuestion {
  id: string;
  kind: 'evidence' | 'rule' | 'jev' | string;
  text: string;
  answer: number;
  clause?: string | null;
}

export interface TreeLeaf {
  when: Record<string, boolean>;
  reach: number;
  levels: number[];
  count: number;
  entropy: number;
  contribution: number;
}

export interface TreeEval {
  tree_id: string;
  value: number;
  entropy: number;
  levels: number[];
  level_names: string[];
  questions: TreeQuestion[];
  leaves: TreeLeaf[];
}

export interface HazardEval {
  id: string;
  name: string;
  applies: boolean;
  why?: string | null;
  likelihood: TreeEval | null;
  severity: TreeEval | null;
  product: number | null;
}

export interface OfficerRuling {
  label: string;
  ruling: string;
  outcome_risky: boolean;
  reason: string;
  named?: { tree_id: string; level: number }[] | null;
  agrees_with_label?: boolean | null;
}

export interface WeightChange {
  tree_id: string;
  leaf: Record<string, boolean>;
  before: number[];
  after: number[];
  count_before: number;
  count_after: number;
}

export interface Correction {
  bucket: string;
  outcome_risky: boolean;
  named?: { tree_id: string; level: number }[] | null;
  changes?: WeightChange[] | null;
}

export interface CaseDetail {
  case_id: string;
  title: string;
  documents: {
    form: Record<string, unknown>;
    cover_letter?: string | null;
    attachments?: { name: string; text: string }[] | null;
  };
  checks?: { id: string; passed: boolean; clause?: string | null }[] | null;
  evidence?: EvidenceRecord[] | null;
  unmapped_documents?: { document: string; why: string }[] | null;
  requirements?: { id: string; status: string; clause?: string | null; evidence_type?: string | null }[] | null;
  hazards?: HazardEval[] | null;
  risk: number | null;
  highest_severity: number | null;
  t_low: number | null;
  t_high: number | null;
  ceiling: number | null;
  decision: { row: number; route: string; reason_code: string; clauses?: string[] | null; text: string };
  officer: OfficerRuling | null;
  correction: Correction | null;
  manifest?: { weights_version?: string | null; thresholds?: unknown; rules_hash?: string | null; source?: string | null } | null;
  events?: number[] | null;
}

export interface CurvePoint {
  index: number;
  corrections: number;
  seq: number;
  right_level?: number | null;
  decided_without_officer: number;
  precision: number;
  loss: number;
  t_low: number;
  t_high: number;
  held_out_cases?: number | null;
}

export interface CardValues {
  right_level?: number | null;
  decided_without_officer?: number | null;
  precision?: number | null;
}

export interface Tone {
  requests: number;
  compared: number;
  decision_flips: number;
  evidence_flips: Record<string, number>;
  noise_evidence_flips?: number | null;
  noise_decision_flips?: number | null;
}

export interface Arm {
  name: string;
  split?: string | null;
  right_level?: number | null;
  right_route_share?: number | null;
  loss?: number | null;
  approved?: number | null;
  risky_among_approved?: number | null;
  interval?: [number | null, number | null] | null;
  status?: string | null;
}

export interface FinalTest {
  status: string;
  verdict: string | null;
  conditions?: { name: string; passed: boolean | null; detail?: string | null }[] | null;
  forbidden_permits?: unknown;
  risky_approvals?: unknown;
}

export interface LearningTree {
  tree_id: string;
  mean_leaf_entropy: number;
  flagged: boolean;
  loss?: number | null;
  leaves: { when: Record<string, boolean>; count: number; entropy: number; levels_first: number[]; levels_now: number[] }[];
}

export interface Learning {
  curve: CurvePoint[];
  cards?: { first?: CardValues | null; final?: CardValues | null } | null;
  arms?: Arm[] | null;
  final_test?: FinalTest | null;
  tone?: Tone | null;
  trees?: LearningTree[] | null;
  crossings?: { status: string; loss_before?: number | null; loss_after?: number | null; text?: string | null } | null;
  corrections?: { case_id: string; seq: number; bucket: string; outcome_risky: boolean; reason?: string | null; tree_ids?: string[] | null }[] | null;
  officer?: { reviewed?: number | null; corrections?: number | null; accuracy?: number | null; level_accuracy?: number | null; label?: string | null } | null;
}

export interface Setting {
  key: string;
  value: unknown;
  limits?: unknown;
  owner?: string | null;
  why?: string | null;
  if_raised?: string | null;
}

export interface Rules {
  ordinance?: { id: string; text: string }[] | null;
  evidence_types?: unknown[] | null;
  requirements?: unknown[] | null;
  does_not_count?: unknown[] | null;
  settings?: Setting[] | null;
  hazards?: unknown[] | null;
}

export interface DemoData {
  manifest: Manifest;
  events: ReplayEvent[];
  cases: CaseRow[];
  learning: Learning;
  rules: Rules;
}

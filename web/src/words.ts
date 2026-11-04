import type { PermitStatus } from '@permit-engine/ui';

export const SOURCE_NOTE: Record<string, string> = {
  simulated: 'The answers are simulated rather than read by the models.',
  real: 'The answers were read by the models ahead of time and stored.',
};

export const REASONS: Record<string, { name: string; short: string; long: string }> = {
  form_returned: {
    name: 'Incomplete form',
    short: 'The form is incomplete, so it goes back to the applicant.',
    long: 'Something the form must state is missing. The applicant gets it back and nothing else is assessed.',
  },
  basic_rule_failed: {
    name: 'Basic rule failed',
    short: 'A basic rule failed, so a denial is proposed.',
    long: 'The fee was not paid, or the date is one the city does not allow.',
  },
  red_flag: {
    name: 'Red flag',
    short: 'A document contradicts the form.',
    long: 'A document says something the form does not, such as another date. The system does not try to settle this, so a person looks.',
  },
  requirement_unclear: {
    name: 'Requirement unclear',
    short: 'The proof for a requirement and its details disagree.',
    long: 'The verdict on a proof and the details pulled from it point different ways, so the system cannot call the requirement met or failed.',
  },
  unmapped_evidence: {
    name: 'Unknown document',
    short: 'A document fits no known type of proof.',
    long: 'The applicant sent a document the rules have no place for. It might matter, so a person reads it.',
  },
  model_failure: {
    name: 'Model failure',
    short: 'A model gave no usable answer.',
    long: 'A model refused or answered in a broken form. Nothing is assumed, so a person decides.',
  },
  policy_unavailable: {
    name: 'Rules engine failure',
    short: 'The rules engine could not run.',
    long: 'The written rules could not be evaluated, so the system will not decide without them.',
  },
  stop_switch: {
    name: 'Stop switch on',
    short: 'The stop switch is on.',
    long: 'The policy owner has paused automatic approvals. Until it is lifted, every case goes to a person.',
  },
  severity_ceiling: {
    name: 'Severity ceiling',
    short: 'One hazard could be very severe, however unlikely.',
    long: 'A small chance times a terrible outcome can look like a small number. At or above the ceiling a person always decides.',
  },
  requirement_failed: {
    name: 'Requirement failed',
    short: 'A document exists but fails a requirement.',
    long: 'The proof was sent, but a detail breaks a rule, such as insurance that ends before the race.',
  },
  requirement_missing: {
    name: 'Requirement missing',
    short: 'The proof for a requirement is missing.',
    long: 'Nothing sent counts as this proof. In this demo there are no letters back, so a person decides straight away.',
  },
  approved: {
    name: 'Approved automatically',
    short: 'Risk is under the low threshold.',
    long: 'Nothing stopped the case earlier, and its risk is under the low threshold.',
  },
  high_risk: {
    name: 'High risk',
    short: 'Risk is at or over the high threshold.',
    long: 'The risk score is at or above the high threshold, so a person looks closely before anything is issued.',
  },
  review_band: {
    name: 'Review band',
    short: 'Risk is between the two thresholds.',
    long: 'The score is neither low enough to approve nor high enough to call high risk, so a person decides.',
  },
};

export const reasonName = (code: string) => REASONS[code]?.name ?? humanize(code);
export const reasonShort = (code: string) => REASONS[code]?.short ?? humanize(code);

export const ROUTES: Record<string, { label: string; status: PermitStatus }> = {
  approved: { label: 'Approved', status: 'approved' },
  proposed_denial: { label: 'Proposed denial', status: 'rejected' },
  returned: { label: 'Returned', status: 'action-required' },
  officer: { label: 'Sent to officer', status: 'in-review' },
};

export const routeBadge = (route: string) => ROUTES[route] ?? { label: humanize(route), status: 'draft' as PermitStatus };

// Pipeline steps shown in the queue and on the case page, in order.
export const PIPELINE: { id: string; label: string; doing: string; types: string[] }[] = [
  { id: 'received', label: 'Received', doing: 'Application received', types: ['case.submitted'] },
  { id: 'checks', label: 'Checks', doing: 'Checking fee, form and date', types: ['checks.done'] },
  { id: 'evidence', label: 'Evidence', doing: 'Reading the documents', types: ['evidence.linked', 'evidence.judged'] },
  { id: 'requirements', label: 'Requirements', doing: 'Checking requirements', types: ['requirements.checked'] },
  { id: 'hazards', label: 'Hazards', doing: 'Working out which hazards apply', types: ['hazards.screened'] },
  { id: 'trees', label: 'Trees', doing: 'Answering the tree questions', types: ['trees.evaluated'] },
  { id: 'risk', label: 'Risk', doing: 'Adding up the risk', types: ['risk.computed'] },
  { id: 'decision', label: 'Decision', doing: 'Decided', types: ['decision.made', 'officer.ruled', 'correction.made', 'weights.updated', 'permit.issued'] },
];

export function pipelineStep(eventType: string | null): number {
  if (!eventType) return -1;
  return PIPELINE.findIndex((p) => p.types.includes(eventType));
}

export const EVENT_STAGE: Record<string, string> = {
  'case.submitted': 'Application received',
  'checks.done': 'Basic checks done',
  'evidence.linked': 'Proof found in the documents',
  'evidence.judged': 'Proof judged',
  'requirements.checked': 'Requirements checked',
  'hazards.screened': 'Hazards screened',
  'trees.evaluated': 'Trees answered',
  'risk.computed': 'Risk added up',
  'decision.made': 'Decided',
  'officer.ruled': 'Officer ruled',
  'correction.made': 'Officer corrected the system',
  'weights.updated': 'The review taught the system',
  'thresholds.rechosen': 'Thresholds re-chosen',
  'permit.issued': 'Permit issued',
  'change.released': 'Change released',
};

export const BUCKETS: Record<string, { name: string; note: string }> = {
  ai_wrong: { name: "The system's mistake", note: 'The officer disagreed, so this is a correction. Leaf weights move.' },
  confirmed: { name: 'No mistake: the officer agreed', note: 'The officer agreed with the system, and the weights still learned from it.' },
  human_wrong: { name: "A person's mistake", note: 'Stored. No weights change, because the system did not cause it.' },
  context_changed: { name: 'The situation changed', note: 'Stored. No weights change, because the past was not wrong.' },
  genuine_exception: { name: 'A genuine exception', note: 'Stored. No weights change, because one exception should not teach a general lesson.' },
};

export const bucketName = (b: string) => BUCKETS[b]?.name ?? humanize(b);

export const VERDICTS: Record<string, string> = {
  supported: 'Supported: the document shows what this proof requires.',
  unsupported: 'Unsupported: the document does not show what this proof requires.',
  contradicted: 'Contradicted: the document says something different from the form.',
};

export const REQUIREMENT_WORDS: Record<string, string> = {
  met: 'The details match the case and the proof is supported.',
  failed: 'A document exists, and a detail breaks a rule.',
  missing: 'Nothing sent counts as this proof.',
  unclear: 'The verdict and the details disagree.',
};

export const QUESTION_KINDS: Record<string, string> = {
  evidence: 'Answered from the proof found in the documents',
  rule: 'Answered by a written rule, so it is yes or no',
  jev: 'Answered by Jev, reading the whole plan',
};

export const DECISION_TABLE: { row: number; when: string; goes: string }[] = [
  { row: 0, when: 'A basic check failed: fee, form or date', goes: 'Returned, or proposed denial' },
  { row: 1, when: 'Evidence contradicted, a requirement unclear, an unknown document, a model or the rules engine failed, the stop switch on, or the highest severity at or above the ceiling', goes: 'Officer' },
  { row: 2, when: 'A requirement failed', goes: 'Proposed denial' },
  { row: 3, when: 'A requirement is missing', goes: 'Officer' },
  { row: 4, when: 'Risk under the low threshold', goes: 'Approved' },
  { row: 5, when: 'Risk at or over the high threshold', goes: 'Officer' },
  { row: 6, when: 'Anything else: risk inside the review band', goes: 'Officer' },
];

export const TREE_NAMES: Record<string, string> = {
  'traffic.likelihood': 'Traffic likelihood',
  'traffic.severity': 'Traffic severity',
  'crowd.likelihood': 'Crowd likelihood',
  'crowd.severity': 'Crowd severity',
  'medical.likelihood': 'Medical likelihood',
  'medical.severity': 'Medical severity',
};

export const treeName = (id: string) => TREE_NAMES[id] ?? humanize(id);

export function humanize(id: string): string {
  const words = String(id).replace(/[._]+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : '';
}

export const lower = (s: string) => s.toLowerCase();

export function describeWhen(when: Record<string, boolean>): string {
  const parts = Object.entries(when ?? {}).map(([q, v]) => `${humanize(q).toLowerCase()}: ${v ? 'yes' : 'no'}`);
  return parts.length ? parts.join(', ') : 'all cases';
}

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined || Number.isNaN(x) ? 'Not measured' : `${(x * 100).toFixed(digits)}%`;

export const num = (x: number | null | undefined, digits = 3) =>
  x === null || x === undefined || Number.isNaN(x) ? 'Not measured' : x.toFixed(digits);

export const fmtCount = (x: number | null | undefined) =>
  x === null || x === undefined ? 'Not measured' : Number.isInteger(x) ? String(x) : x.toFixed(1);

/** The fixture sends thresholds as a sentence, the engine as an object. Both read the same. */
export function fmtThresholds(v: unknown, tLow: number | null, tHigh: number | null): string {
  if (typeof v === 'string') return v;
  const rec = (v ?? {}) as { t_low?: number | null; t_high?: number | null };
  return `t_low ${num(rec.t_low ?? tLow)}, t_high ${num(rec.t_high ?? tHigh)}`;
}

/** A case stopped at row 0 was never scored, even if the export writes 0 for its risk. */
export const riskText = (risk: number | null | undefined, row: number) => (risk === null || risk === undefined || row === 0 ? 'not computed' : num(risk));

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

export function simClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
}

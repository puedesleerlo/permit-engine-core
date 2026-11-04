// Writes a small, self-consistent export in web/public/data matching docs/designs/demo-build.md.
// The real export from the engine replaces it. Every number is computed, so the tree, risk and meter arithmetic can be checked.
//   node scripts/make_fixture.mjs                     about 20 cases, every route and reason code
//   node scripts/make_fixture.mjs --cases 120 --out DIR   a larger run for checking that the replay stays smooth
// It refuses to overwrite a real export unless given --force.
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const argOf = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
};
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(argOf('--out', join(HERE, '..', 'public', 'data')));
const TARGET_CASES = Number(argOf('--cases', 0));

let seed = 20261104;
const rnd = () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const pick = (list) => list[Math.floor(rnd() * list.length)];
const round = (x, d = 3) => Number(x.toFixed(d));
const entropy = (p) => round(p.reduce((s, x) => (x > 0 ? s - x * Math.log(x) : s), 0));

const OFFICER_LABEL = 'Simulated officer: an LLM following the expert rubric';
const ANCHORS = { likelihood: [0.02, 0.1, 0.3], severity: [0.1, 0.4, 1.0] };
const LEVEL_NAMES = { likelihood: ['rare', 'possible', 'likely'], severity: ['minor', 'serious', 'critical'] };
const P_EVIDENCE = { supported: 0.9, unsupported: 0.1, contradicted: 0.05 };

const QUESTIONS = {
  escort_confirmed: { kind: 'evidence', text: 'Is the police escort confirmed?', clause: 'ORD-12.4' },
  traffic_plan_adequate: { kind: 'jev', text: 'Does the traffic plan cover every road closure on the route?', clause: 'ORD-12.2' },
  arterial_road: { kind: 'rule', text: 'Does the route use an arterial road?', clause: 'ORD-12.1' },
  crowd_over_800: { kind: 'rule', text: 'Are runners and spectators together more than 800?', clause: 'ORD-14.1' },
  crowd_plan_adequate: { kind: 'jev', text: 'Does the crowd plan cover entry, exit and marshals?', clause: 'ORD-14.2' },
  narrow_venue: { kind: 'jev', text: 'Does the race plan describe a narrow start or finish?', clause: 'ORD-14.3' },
  medical_plan_adequate: { kind: 'jev', text: 'Does the medical plan cover first aid and how to reach help?', clause: 'ORD-13.1' },
  hot_date: { kind: 'rule', text: 'Is the race in June, July or August?', clause: 'ORD-13.3' },
  ambulance_on_site: { kind: 'evidence', text: 'Is an ambulance agreed for the event?', clause: 'ORD-13.2' },
  hospital_far: { kind: 'rule', text: 'Is the nearest hospital more than 10 km away?', clause: 'ORD-13.4' },
};

// First guesses, deliberately rough, one row per leaf with the questions' answers true first.
const TREES = [
  { id: 'traffic.likelihood', hazard: 'traffic_conflict', scale: 'likelihood', q: ['escort_confirmed', 'traffic_plan_adequate'], first: [[0.7, 0.2, 0.1], [0.3, 0.5, 0.2], [0.3, 0.5, 0.2], [0.1, 0.3, 0.6]] },
  { id: 'traffic.severity', hazard: 'traffic_conflict', scale: 'severity', q: ['arterial_road', 'crowd_over_800'], first: [[0.1, 0.4, 0.5], [0.3, 0.5, 0.2], [0.3, 0.5, 0.2], [0.7, 0.25, 0.05]] },
  { id: 'crowd.likelihood', hazard: 'crowd_pressure', scale: 'likelihood', q: ['crowd_plan_adequate', 'crowd_over_800'], first: [[0.5, 0.35, 0.15], [0.8, 0.15, 0.05], [0.1, 0.3, 0.6], [0.3, 0.5, 0.2]] },
  { id: 'crowd.severity', hazard: 'crowd_pressure', scale: 'severity', q: ['narrow_venue', 'crowd_over_800'], first: [[0.1, 0.3, 0.6], [0.3, 0.5, 0.2], [0.3, 0.5, 0.2], [0.75, 0.2, 0.05]] },
  { id: 'medical.likelihood', hazard: 'medical_emergency', scale: 'likelihood', q: ['medical_plan_adequate', 'hot_date'], first: [[0.4, 0.45, 0.15], [0.75, 0.2, 0.05], [0.1, 0.3, 0.6], [0.3, 0.5, 0.2]] },
  { id: 'medical.severity', hazard: 'medical_emergency', scale: 'severity', q: ['ambulance_on_site', 'hospital_far'], first: [[0.3, 0.5, 0.2], [0.8, 0.15, 0.05], [0.02, 0.08, 0.9], [0.2, 0.55, 0.25]] },
];
const HAZARDS = { traffic_conflict: 'Traffic conflict', crowd_pressure: 'Crowd pressure', medical_emergency: 'Medical emergency' };

const combos = (ids) => {
  if (!ids.length) return [{}];
  const rest = combos(ids.slice(1));
  return [true, false].flatMap((v) => rest.map((r) => ({ [ids[0]]: v, ...r })));
};

// Live weights: corrections move them, so what each later case reads is what earlier corrections left behind.
const weights = Object.fromEntries(
  TREES.map((t) => [t.id, combos(t.q).map((when, i) => ({ when, first: t.first[i], levels: [...t.first[i]], count: round(16 + rnd() * 30, 1) }))]),
);

function evaluateTree(tree, answers) {
  const leaves = weights[tree.id].map((leaf) => {
    const reach = tree.q.reduce((r, id) => r * (leaf.when[id] ? answers[id] : 1 - answers[id]), 1);
    const leafValue = leaf.levels.reduce((s, p, i) => s + p * ANCHORS[tree.scale][i], 0);
    return {
      when: leaf.when,
      reach: round(reach),
      levels: leaf.levels.map((x) => round(x)),
      count: round(leaf.count, 1),
      entropy: entropy(leaf.levels),
      contribution: round(reach * leafValue),
      raw: reach,
      leaf,
    };
  });
  const levels = [0, 1, 2].map((i) => leaves.reduce((s, l) => s + l.raw * l.leaf.levels[i], 0));
  return {
    tree_id: tree.id,
    value: round(levels.reduce((s, p, i) => s + p * ANCHORS[tree.scale][i], 0)),
    entropy: entropy(levels),
    levels: levels.map((x) => round(x)),
    level_names: LEVEL_NAMES[tree.scale],
    questions: tree.q.map((id) => ({ id, kind: QUESTIONS[id].kind, text: QUESTIONS[id].text, answer: round(answers[id]), clause: QUESTIONS[id].clause })),
    leaves,
  };
}
const publicTree = (t) => ({ ...t, leaves: t.leaves.map(({ raw, leaf, ...rest }) => rest) });

const REASON_TEXT = {
  form_returned: 'The form is incomplete, so it goes back to the applicant.',
  basic_rule_failed: 'A basic rule failed, so a denial is proposed.',
  red_flag: 'A document contradicts the form, so an officer decides.',
  requirement_unclear: 'The proof for a requirement and its details disagree, so an officer decides.',
  unmapped_evidence: 'A document fits no known type of proof, so an officer decides.',
  model_failure: 'A model gave no usable answer, so an officer decides.',
  policy_unavailable: 'The rules engine could not run, so an officer decides.',
  stop_switch: 'The stop switch is on, so an officer decides.',
  severity_ceiling: 'One hazard reaches the severity ceiling, so an officer decides however unlikely it is.',
  requirement_failed: 'A document exists but fails a requirement, so a denial is proposed.',
  requirement_missing: 'The proof for a requirement is missing, so an officer decides.',
  approved: 'Risk is under the low threshold and nothing stopped the case, so it is approved.',
  high_risk: 'Risk is at or over the high threshold, so an officer decides.',
  review_band: 'Risk is inside the review band, so an officer decides.',
};

function decide(s, ctx) {
  const row = (r, route, reason_code, clauses) => ({ row: r, route, reason_code, clauses, text: REASON_TEXT[reason_code] });
  if (!s.form_complete) return row(0, 'returned', 'form_returned', ['ORD-3.2']);
  if (!s.fee_paid) return row(0, 'proposed_denial', 'basic_rule_failed', ['ORD-3.1']);
  if (!s.date_allowed) return row(0, 'proposed_denial', 'basic_rule_failed', ['ORD-3.3']);
  if (ctx.contradicted) return row(1, 'officer', 'red_flag', ['ORD-5.2']);
  if (ctx.unclear) return row(1, 'officer', 'requirement_unclear', ['ORD-7.1']);
  if (ctx.unmapped) return row(1, 'officer', 'unmapped_evidence', ['ORD-5.3']);
  if (s.model_failure) return row(1, 'officer', 'model_failure', ['ORD-5.4']);
  if (s.policy_failure) return row(1, 'officer', 'policy_unavailable', ['ORD-5.4']);
  if (s.stop_switch) return row(1, 'officer', 'stop_switch', ['ORD-5.5']);
  if (ctx.highest >= ctx.ceiling) return row(1, 'officer', 'severity_ceiling', ['ORD-6.2']);
  if (ctx.failed) return row(2, 'proposed_denial', 'requirement_failed', ['ORD-7.1']);
  if (ctx.missing) return row(3, 'officer', 'requirement_missing', ['ORD-7.1']);
  if (ctx.risk < ctx.t_low) return row(4, 'approved', 'approved', ['ORD-6.1']);
  if (ctx.risk >= ctx.t_high) return row(5, 'officer', 'high_risk', ['ORD-6.1']);
  return row(6, 'officer', 'review_band', ['ORD-6.1']);
}

const base = {
  runners: 300, spectators: 0, road_closure: false, arterial: false, crossings: 1, date: '2027-04-17', hospital_km: 3,
  fee_paid: true, form_complete: true, date_allowed: true, insurance: 'valid', escort: 'letter', ambulance: 'letter',
  traffic: 0.85, crowd: 0.85, medical: 0.9, narrow: 0.15, model_failure: false, policy_failure: false, stop_switch: false,
};

// Replay order. One scenario for every route and reason code, plus both failure modes and each correction bucket.
const SCENARIOS = [
  { org: 'Riverside Runners', event: '5K', runners: 240, spectators: 30 },
  { org: 'Harbour Athletics', title: 'Harbour Half Marathon', event: 'half marathon', agreed: false, runners: 900, spectators: 400, road_closure: true, arterial: true, crossings: 2, date: '2027-05-16', traffic: 0.55, crowd: 0.6, medical: 0.7, officer: { ruling: 'approve', risky: false, reason: 'The plan covers each closure and the escort letter is signed, so the risk is acceptable.', bucket: 'ai_wrong' } },
  { org: 'Old Town Night Run', event: '5K', form_complete: false },
  { org: 'Summit Trail Club', event: '10K', agreed: false, runners: 520, spectators: 60, road_closure: true, crossings: 2, traffic: 0.5, medical: 0.5, hospital_km: 8, date: '2027-06-19', officer: { ruling: 'approve', risky: false, reason: 'Few spectators and a short closure. The system is too cautious about this kind of route.', bucket: 'ai_wrong' } },
  { org: 'Mill Lane Athletics', title: 'Mill Lane Mile', event: 'one mile race', runners: 150, fee_paid: false },
  { org: 'Eastside Striders', event: '10K', runners: 1400, spectators: 900, road_closure: true, arterial: true, crossings: 4, date: '2027-07-11', escort: 'none', traffic: 0.2, crowd: 0.25, medical: 0.4, narrow: 0.7, officer: { ruling: 'deny', risky: true, reason: 'No escort on an arterial road with four major crossings and a large crowd.' } },
  { org: 'Canal Path Runners', event: '5K', runners: 380, road_closure: true, escort: 'contradicting', officer: { ruling: 'deny', risky: true, reason: 'The escort letter names a different date from the form, so the escort is not confirmed.' } },
  { org: 'Bridge to Bridge', event: '10K', runners: 620, spectators: 100, insurance: 'broker_letter', officer: { ruling: 'approve', risky: false, reason: 'A broker letter is not on the list of proof, but it names the venue and dates. Accepted as an exception.' } },
  { org: 'Parkside Fun Run', event: '5K', runners: 200, insurance: 'unclear', officer: { ruling: 'approve', risky: false, reason: 'The certificate is valid. The mismatch is a typing error in the street name.' } },
  { org: 'Lakeshore Runners', event: '8K', runners: 440, spectators: 80, insurance: 'expired' },
  { org: 'Hilltop Runners', title: 'Hilltop Relay', event: 'relay', runners: 320, spectators: 90, insurance: 'missing', officer: { ruling: 'deny', risky: true, reason: 'No insurance was sent, and insurance is a legal requirement.' } },
  { org: 'Westbank Sprint', event: '5K', runners: 180, model_failure: true, officer: { ruling: 'approve', risky: false, reason: 'A small race on closed paths. The documents are in order when read by hand.' } },
  { org: 'University Athletics', title: 'University Loop 5K', event: '5K', runners: 270, spectators: 15, crossings: 3, medical: 0.95, label_risky: true, agreed: false },
  { org: 'Market Street Club', title: 'Market Street Mile', event: 'one mile race', runners: 260, spectators: 200, policy_failure: true, officer: { ruling: 'approve', risky: false, reason: 'Rules checked by hand. All requirements are met and the crowd is small.' } },
  { org: 'Stadium Harriers', event: '10K', runners: 720, spectators: 120, road_closure: true, crossings: 3, traffic: 0.55, crowd: 0.55, medical: 0.6, date: '2027-05-30', officer: { ruling: 'deny', risky: true, reason: 'Three major crossings with an unclear traffic plan. The system underrates crossings.', bucket: 'ai_wrong', named: [{ tree_id: 'traffic.likelihood', level: 2 }] } },
  { org: 'Cathedral Close Runners', event: '5K', runners: 260, stop_switch: true, officer: { ruling: 'approve', risky: false, reason: 'Stop switch was on for all cases. This one looks routine.', disagree: true } },
  { org: 'Northgate Harriers', title: 'Northgate Marathon', event: 'marathon', runners: 1800, spectators: 1100, road_closure: true, arterial: true, crossings: 2, date: '2027-08-08', ambulance: 'none', hospital_km: 18, traffic: 0.75, crowd: 0.7, medical: 0.6, officer: { ruling: 'deny', risky: true, reason: 'August heat, no ambulance and the hospital is 18 km away.' } },
  { org: 'Foundry Road Runners', event: '5K', runners: 280, spectators: 10, forbidden: true, agreed: false },
  { org: 'Orchard Lane Joggers', event: '5K', runners: 210, spectators: 20 },
  { org: 'Westfield Athletic Club', event: '10K', runners: 860, spectators: 240, road_closure: true, arterial: true, crossings: 1, traffic: 0.45, crowd: 0.45, medical: 0.5, date: '2027-06-27', officer: { ruling: 'approve', risky: false, reason: 'The route changed last month, so the older plan score no longer applies.' } },
  { org: 'Greenway Runners', event: '8K', runners: 450, spectators: 60, traffic: 0.9, crowd: 0.82, medical: 0.88 },
  { org: 'Bayview Pacers', event: '5K', runners: 330, spectators: 40, medical: 0.93 },
];

const ORGS = ['Ashford', 'Beacon Hill', 'Cedar Park', 'Dockside', 'Elm Street', 'Fairview', 'Glenwood', 'Highbridge', 'Ironworks', 'Junction', 'Kingsway', 'Lowfield', 'Meadow', 'Newbridge', 'Oakdale', 'Pinehurst', 'Quayside', 'Redwood', 'Stonegate', 'Tanners', 'Upland', 'Valley', 'Wharf', 'Yarrow'];
const CLUBS = ['Runners', 'Athletics', 'Striders', 'Harriers', 'Pacers', 'Road Club'];

function scenarioList() {
  if (!TARGET_CASES) return SCENARIOS;
  const out = [];
  while (out.length < TARGET_CASES) {
    const s = SCENARIOS[out.length % SCENARIOS.length];
    if (out.length < SCENARIOS.length) { out.push(s); continue; }
    const jitter = (x, d = 0.12) => Math.min(0.98, Math.max(0.02, (x ?? 0.8) + (rnd() - 0.5) * 2 * d));
    const routine = rnd() < 0.55;
    out.push(routine
      ? { org: `${pick(ORGS)} ${pick(CLUBS)}`, event: pick(['5K', '8K', '10K']), runners: 150 + Math.floor(rnd() * 500), spectators: Math.floor(rnd() * 150), road_closure: rnd() < 0.4, traffic: jitter(0.85), crowd: jitter(0.85), medical: jitter(0.88), narrow: jitter(0.15) }
      : { ...s, title: undefined, org: `${pick(ORGS)} ${pick(CLUBS)}`, runners: s.runners ?? 300 + Math.floor(rnd() * 500), traffic: jitter(s.traffic), crowd: jitter(s.crowd), medical: jitter(s.medical) });
  }
  return out;
}

function makeDocuments(s, title) {
  const closure = s.road_closure ? 'Main Street and Quay Road will close from 07:00 to 11:00.' : 'The route stays on park paths, so no road closes.';
  const attachments = [
    { name: 'race_plan.txt', text: `Race plan for ${title}.\nStart and finish at Civic Square. ${s.narrow > 0.5 ? 'The start uses a narrow lane about 4 metres wide.' : 'The start and finish are on the open square.'}\nExpected runners: ${s.runners}. Expected spectators: ${s.spectators}.\n${closure}` },
    { name: 'traffic_plan.txt', text: `Traffic plan.\n${closure}\n${s.traffic > 0.6 ? 'Marshals stand at every closed junction, and diversion signs go up the evening before.' : 'Marshals will be placed where needed on the day.'}\nMajor crossings on the route: ${s.crossings}.` },
    { name: 'crowd_plan.txt', text: `Crowd plan.\n${s.crowd > 0.6 ? 'Entry and exit are separated at the square, with 14 marshals in visible vests.' : 'Volunteers will help people find their way.'}` },
    { name: 'medical_plan.txt', text: `Medical plan.\n${s.medical > 0.6 ? 'Two first aid points on the course, with radio contact to race control.' : 'First aid kit at the finish line.'}\nNearest hospital: ${s.hospital_km} km.` },
  ];
  const quotes = {};
  const add = (name, text, quote) => { attachments.push({ name, text }); quotes[name] = quote; };
  if (s.insurance === 'valid' || s.insurance === 'unclear' || s.insurance === 'expired') {
    const venue = s.insurance === 'unclear' ? 'Civic Sq. annex' : 'Civic Square and marked route';
    const end = s.insurance === 'expired' ? '31 Dec 2026' : '31 Dec 2027';
    add('insurance.txt', `Certificate of insurance.\nNamed insured: ${s.org}.\nEvent venue: ${venue}.\nCover runs from 1 Jan 2027 to ${end}.\nLiability cover: 2,000,000.`, { venue: `Event venue: ${venue}.`, end: `Cover runs from 1 Jan 2027 to ${end}.`, insured: `Named insured: ${s.org}.` });
  }
  if (s.insurance === 'broker_letter') attachments.push({ name: 'broker_letter.txt', text: `To whom it may concern.\nOur client ${s.org} holds cover for events at Civic Square this year.\nA certificate will follow.` });
  if (s.road_closure && s.escort === 'letter') add('police_escort_letter.txt', `City police, traffic unit.\nWe confirm an escort for ${title} on ${s.date}.\nTwo officers will lead the field along the closed roads.`, { confirm: `We confirm an escort for ${title} on ${s.date}.` });
  if (s.road_closure && s.escort === 'contradicting') add('police_escort_letter.txt', `City police, traffic unit.\nWe confirm an escort for ${title} on 2027-10-03.\nTwo officers will lead the field along the closed roads.`, { confirm: `We confirm an escort for ${title} on 2027-10-03.` });
  if (s.ambulance === 'letter') add('ambulance_agreement.txt', `Ambulance agreement.\nCity Ambulance will keep one crew on site for ${title} from 07:00 to 12:00.`, { crew: `City Ambulance will keep one crew on site for ${title} from 07:00 to 12:00.` });
  const form = {
    organizer: s.org,
    event_type: 'street race',
    event_date: s.date,
    expected_runners: s.runners,
    description: `${title}, starting and finishing at Civic Square.`,
    route: { road_closure: s.road_closure, arterial_road: s.arterial, major_crossings: s.crossings },
    hospital_distance_km: s.hospital_km,
    fee_paid: s.fee_paid,
    attachments: attachments.map((a) => a.name),
  };
  if (!s.form_complete) delete form.description;
  return { form, cover_letter: `Dear permit office,\nWe are asking for a permit for ${title} on ${s.date}. We expect about ${s.runners} runners${s.spectators ? ` and about ${s.spectators} spectators` : ''}.\nThe plans are attached.\nThank you,\n${s.org}`, attachments, quotes };
}

function makeEvidence(s, documents) {
  const { quotes } = documents;
  const out = [];
  const stored = { source: 'stored' };
  if (s.insurance === 'valid' || s.insurance === 'expired' || s.insurance === 'unclear') {
    const q = quotes['insurance.txt'];
    out.push({
      evidence_type: 'certificate_of_insurance', status: 'found', document: 'insurance.txt',
      fields: [
        { name: 'named insured', value: s.org, quote: q.insured, verified: true, matches_form: true },
        { name: 'venue', value: s.insurance === 'unclear' ? 'Civic Sq. annex' : 'Civic Square and marked route', quote: q.venue, verified: true, matches_form: s.insurance !== 'unclear' },
        { name: 'end date', value: s.insurance === 'expired' ? '2026-12-31' : '2027-12-31', quote: q.end, verified: true, matches_form: s.insurance !== 'expired' },
      ],
      verdict: s.insurance === 'expired' ? 'unsupported' : 'supported',
      reason: s.insurance === 'expired' ? 'The cover ends before the event date.' : s.insurance === 'unclear' ? 'The certificate reads as valid, but the venue differs from the form.' : null,
      ...stored,
    });
  } else {
    out.push({ evidence_type: 'certificate_of_insurance', status: 'absent', document: null, fields: [], verdict: null, reason: 'No document of this type was sent.', ...stored });
  }
  if (s.road_closure) {
    if (s.escort === 'none') out.push({ evidence_type: 'police_escort_letter', status: 'absent', document: null, fields: [], verdict: null, reason: 'No letter or email from the police was sent.', ...stored });
    else {
      const q = quotes['police_escort_letter.txt'];
      const contradicted = s.escort === 'contradicting';
      out.push({
        evidence_type: 'police_escort_letter', status: 'found', document: 'police_escort_letter.txt',
        fields: [{ name: 'date', value: contradicted ? '2027-10-03' : s.date, quote: q.confirm, verified: true, matches_form: !contradicted }],
        verdict: contradicted ? 'contradicted' : 'supported',
        reason: contradicted ? 'The letter names a different date from the form.' : null,
        ...stored,
      });
    }
  }
  if (s.ambulance === 'letter') {
    const q = quotes['ambulance_agreement.txt'];
    out.push({ evidence_type: 'ambulance_agreement', status: 'found', document: 'ambulance_agreement.txt', fields: [{ name: 'crew on site', value: 'one crew, 07:00 to 12:00', quote: q.crew, verified: true, matches_form: true }], verdict: 'supported', reason: null, ...stored });
  } else {
    out.push({ evidence_type: 'ambulance_agreement', status: 'absent', document: null, fields: [], verdict: null, reason: 'No ambulance agreement was sent.', ...stored });
  }
  return out;
}

const HOT = (date) => ['06', '07', '08'].includes(date.slice(5, 7));
const fmtRate = (x) => `${Math.round(x * 100)}%`;

function main() {
  const existing = join(OUT, 'manifest.json');
  if (existsSync(existing) && !args.includes('--force') && !JSON.parse(readFileSync(existing, 'utf8')).run_id?.startsWith('fixture')) {
    console.error(`${OUT} holds a real export. Pass --out DIR to write elsewhere, or --force to replace it.`);
    process.exit(1);
  }
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(join(OUT, 'cases'), { recursive: true });

  const events = [];
  const rows = [];
  const details = [];
  const learningCorrections = [];
  const scenarios = scenarioList().map((s) => ({ ...base, ...s }));
  const total = scenarios.length;
  const plannedReviews = scenarios.filter((x) => x.officer).length || 1;

  let seq = 0;
  let time = Date.UTC(2027, 0, 4, 9, 0, 0);
  let reviews = 0;
  const thresholdPlan = [{ t_low: 0.05, t_high: 0.15 }, { t_low: 0.06, t_high: 0.16 }, { t_low: 0.07, t_high: 0.18 }, { t_low: 0.08, t_high: 0.2 }];
  let thresholdStage = 0;
  const curve = [];
  const heldOut = 90;
  const curvePoint = (seqAt) => {
    const f = Math.min(1, reviews / (plannedReviews * 1.4));
    const eased = 1 - (1 - f) ** 1.6;
    const t = thresholdPlan[thresholdStage];
    curve.push({
      index: curve.length,
      corrections: reviews,
      seq: seqAt,
      right_level: round(0.68 + 0.16 * eased + (rnd() - 0.5) * 0.008),
      decided_without_officer: round(0.62 + (rnd() - 0.5) * 0.012),
      precision: round(0.93 + 0.01 * eased + (rnd() - 0.5) * 0.006),
      loss: round(0.78 - 0.26 * eased + (rnd() - 0.5) * 0.008),
      t_low: t.t_low,
      t_high: t.t_high,
      held_out_cases: heldOut,
    });
    return curve.length - 1;
  };

  const emit = (case_id, type, summary, actor = 'engine', extra = {}) => {
    seq += 1;
    time += 1000 * 60 * (2 + Math.floor(rnd() * 6));
    const ev = { seq, sim_time: new Date(time).toISOString().slice(0, 19), case_id, type, actor, simulated: true, summary, ...extra };
    events.push(ev);
    return ev;
  };
  curvePoint(1);

  const every = total < 50 ? 2 : 10;
  scenarios.forEach((s, n) => {
    const caseId = `R${String(n + 1).padStart(4, '0')}-plain`;
    const title = s.title ?? `${s.org} ${s.event}`;
    const documents = makeDocuments(s, title);
    const caseEvents = [];
    const log = (type, summary, actor, extra) => { caseEvents.push(emit(caseId, type, summary, actor, extra).seq); };
    const first_seq = seq + 1;
    log('case.submitted', `${s.org} applied for a ${s.event} with ${s.runners} runners.`, 'script');

    const checks = [
      { id: 'fee_paid', passed: s.fee_paid, clause: 'ORD-3.1' },
      { id: 'form_complete', passed: s.form_complete, clause: 'ORD-3.2' },
      { id: 'date_allowed', passed: s.date_allowed, clause: 'ORD-3.3' },
    ];
    const basicFailed = checks.filter((c) => !c.passed);
    log('checks.done', basicFailed.length ? `A basic check failed (${basicFailed[0].id.replace('_', ' ')}).` : `Fee, form and date checks passed.`, 'rego');

    const t = thresholdPlan[thresholdStage];
    const ceiling = 0.85;
    let evidence = [];
    let unmapped = [];
    let requirements = [];
    let hazards = [];
    let risk = null;
    let highest = null;
    const stopped = basicFailed.length > 0;
    const unread = s.model_failure;
    if (!stopped && !unread) {
      evidence = makeEvidence(s, documents);
      if (s.insurance === 'broker_letter') unmapped = [{ document: 'broker_letter.txt', why: 'A broker letter fits no type of proof on the evidence map.' }];
      const found = evidence.filter((e) => e.status === 'found').length;
      log('evidence.linked', `The agentic LLM found ${found} of ${evidence.length} kinds of proof in the documents.`, 'llm');
      const judged = evidence.filter((e) => e.verdict).map((e) => `${e.evidence_type.replaceAll('_', ' ')} ${e.verdict}`);
      log('evidence.judged', judged.length ? `${judged.join(', ')}.` : `Nothing to judge, no proof was found.`, 'llm');
      const ins = evidence[0];
      const insStatus = ins.status === 'absent' ? 'missing' : s.insurance === 'expired' ? 'failed' : s.insurance === 'unclear' ? 'unclear' : 'met';
      requirements = [{ id: 'event_insurance', status: insStatus, clause: 'ORD-7.1', evidence_type: 'certificate_of_insurance' }];
      log('requirements.checked', `Event insurance is ${insStatus}.`, 'rego');

      const crowd = s.runners + s.spectators;
      const answers = {
        escort_confirmed: s.road_closure && s.escort === 'letter' ? P_EVIDENCE.supported : s.escort === 'contradicting' ? P_EVIDENCE.contradicted : P_EVIDENCE.unsupported,
        traffic_plan_adequate: s.traffic,
        arterial_road: s.arterial ? 1 : 0,
        crowd_over_800: crowd > 800 ? 1 : 0,
        crowd_plan_adequate: s.crowd,
        narrow_venue: s.narrow,
        medical_plan_adequate: s.medical,
        hot_date: HOT(s.date) ? 1 : 0,
        ambulance_on_site: s.ambulance === 'letter' ? P_EVIDENCE.supported : P_EVIDENCE.unsupported,
        hospital_far: s.hospital_km > 10 ? 1 : 0,
      };
      const applies = { traffic_conflict: s.road_closure, crowd_pressure: crowd >= 300, medical_emergency: true };
      const why = {
        traffic_conflict: s.road_closure ? 'The road closes.' : 'No road closes, so traffic does not apply.',
        crowd_pressure: crowd >= 300 ? `Runners and spectators add up to ${crowd}, which is 300 or more.` : `Runners and spectators add up to ${crowd}, under 300.`,
        medical_emergency: 'A medical emergency always applies.',
      };
      const applying = Object.keys(applies).filter((h) => applies[h]);
      log('hazards.screened', `Rules say ${applying.length} hazards apply: ${applying.map((h) => HAZARDS[h].toLowerCase()).join(', ')}.`, 'rego');
      hazards = Object.keys(HAZARDS).map((id) => {
        if (!applies[id]) return { id, name: HAZARDS[id], applies: false, why: why[id], likelihood: null, severity: null, product: null };
        const l = evaluateTree(TREES.find((x) => x.hazard === id && x.scale === 'likelihood'), answers);
        const sev = evaluateTree(TREES.find((x) => x.hazard === id && x.scale === 'severity'), answers);
        return { id, name: HAZARDS[id], applies: true, why: why[id], likelihood: l, severity: sev, product: round(l.value * sev.value) };
      });
      log('trees.evaluated', `Jev answered the plan questions and the trees gave their levels.`, 'jev');
      const live = hazards.filter((h) => h.applies);
      risk = round(live.reduce((sum, h) => sum + h.likelihood.value * h.severity.value, 0));
      highest = round(Math.max(...live.map((h) => h.severity.value)));
      log('risk.computed', `Risk adds up to ${risk.toFixed(3)}. Under ${t.t_low} is approved, ${t.t_high} or more goes to an officer.`, 'engine');
    }
    const ctx = {
      contradicted: evidence.some((e) => e.verdict === 'contradicted'),
      unclear: requirements.some((r) => r.status === 'unclear'),
      unmapped: unmapped.length > 0,
      failed: requirements.some((r) => r.status === 'failed'),
      missing: requirements.some((r) => r.status === 'missing'),
      highest: highest ?? 0, ceiling, risk: risk ?? 0, t_low: t.t_low, t_high: t.t_high,
    };
    const decision = decide(s, ctx);
    // The officer reviews almost every case it can, approved ones too. Row 0 cases and failed reads are left out, as in the engine.
    if (!s.officer && hazards.length) {
      const risky = Boolean(s.label_risky) || (risk !== null && risk > t.t_high);
      s.officer = { ruling: risky ? 'deny' : 'approve', risky, reason: risky ? 'High risk with no plan that lowers it.' : 'The plans are adequate and the crowd is manageable.', bucket: decision.route === 'approved' && s.label_risky ? 'ai_wrong' : decision.route !== 'approved' && rnd() < 0.2 ? 'ai_wrong' : undefined };
    }
    log('decision.made', decision.text, 'rego');
    const decided_seq = seq;
    let officer = null;
    let correction = null;
    let label_risky = Boolean(s.label_risky);
    let agreed = s.agreed ?? true;
    if (decision.route === 'approved') log('permit.issued', `Permit issued automatically to ${s.org}.`, 'engine');
    if (s.officer) {
      const o = s.officer;
      label_risky = o.risky || label_risky;
      officer = {
        label: OFFICER_LABEL, ruling: o.ruling, outcome_risky: o.risky, reason: o.reason, named: o.named ?? [],
        agrees_with_label: !o.disagree,
      };
      log('officer.ruled', `The simulated officer ruled ${o.ruling}: ${o.reason}`, 'officer');
      const bucket = o.bucket === 'ai_wrong' ? 'ai_wrong' : 'confirmed';
      const changes = [];
      for (const tr of hazards.filter((h) => h.applies).flatMap((h) => [h.likelihood, h.severity])) {
        for (const l of tr.leaves) {
          if (l.raw < 0.08) continue;
          const before = l.leaf.levels.map((x) => round(x));
          const count_before = round(l.leaf.count, 2);
          const target = o.risky ? [0.05, 0.25, 0.7] : [0.75, 0.2, 0.05];
          const w = l.raw * (bucket === 'ai_wrong' ? 2.4 : 0.6);
          l.leaf.levels = l.leaf.levels.map((x, i) => (x * l.leaf.count + target[i] * w) / (l.leaf.count + w));
          l.leaf.count += l.raw;
          changes.push({ tree_id: tr.tree_id, leaf: l.when, before, after: l.leaf.levels.map((x) => round(x)), count_before, count_after: round(l.leaf.count, 2) });
        }
      }
      if (changes.length) {
        reviews += 1;
        correction = { bucket, outcome_risky: o.risky, named: o.named ?? [], changes };
        if (bucket === 'ai_wrong') {
          const ev = emit(caseId, 'correction.made', `The officer found this case ${o.risky ? 'risky' : 'not risky'}, against the system's estimate.`, 'officer', { learning_index: curve.length - 1 });
          caseEvents.push(ev.seq);
          learningCorrections.push({ case_id: caseId, seq: ev.seq, bucket, outcome_risky: o.risky, reason: o.reason, tree_ids: [...new Set(changes.map((c) => c.tree_id))] });
        }
        log('weights.updated', `The officer's review moved leaf counts on ${new Set(changes.map((c) => c.tree_id)).size} trees. Weights are now first-guess+${reviews}.`, 'engine');
        if (reviews % every === 0) {
          thresholdStage = Math.min(thresholdPlan.length - 1, thresholdStage + 1);
          const nt = thresholdPlan[thresholdStage];
          const li = curvePoint(seq + 1);
          const ev = emit(caseId, 'thresholds.rechosen', `Thresholds re-chosen after ${reviews} officer reviews: approve under ${nt.t_low}, high risk from ${nt.t_high}.`, 'engine', { learning_index: li });
          curve[li].seq = ev.seq;
          caseEvents.push(ev.seq);
        }
      }
      if (o.ruling === 'approve' && decision.route !== 'approved') log('permit.issued', `Permit issued to ${s.org} after the simulated officer's ruling.`, 'engine');
    }
    rows.push({
      case_id: caseId, title, first_seq, decided_seq, route: decision.route, reason_code: decision.reason_code, row: decision.row, risk,
      t_low: t.t_low, t_high: t.t_high, weights_version: `first-guess+${reviews}`, officer: decision.route === 'officer', corrected: Boolean(correction),
      label_risky, agreed_with_label: agreed,
    });
    const { quotes, ...docs } = documents;
    details.push({
      case_id: caseId, title, documents: docs, checks, evidence, unmapped_documents: unmapped, requirements,
      hazards: hazards.map((h) => (h.applies ? { ...h, likelihood: publicTree(h.likelihood), severity: publicTree(h.severity) } : h)),
      risk, highest_severity: highest, t_low: t.t_low, t_high: t.t_high, ceiling, decision, officer, correction,
      manifest: { weights_version: `first-guess+${reviews}`, thresholds: `t_low ${t.t_low}, t_high ${t.t_high}`, rules_hash: 'b41f0c2e9a7d', source: 'stored' },
      events: caseEvents,
    });

  });
  emit(null, 'change.released', 'The policy owner released the crossings question for the traffic likelihood tree.', 'engine');

  const manifest = {
    run_id: 'fixture-1', created_at: '2026-11-04T01:00:00-05:00', source: 'simulated', synthetic: true, officer_label: OFFICER_LABEL,
    jev_model: 'jev-1.14.0', case_count: rows.length, event_count: events.length, officer_accuracy: 0.91,
    notes: ['All applications are synthetic.', 'This export is a test fixture. The real export replaces it.'],
  };

  const last = curve[curve.length - 1];
  const treeStats = TREES.map((t) => {
    const leaves = weights[t.id].map((l) => ({ when: l.when, count: round(l.count, 1), entropy: entropy(l.levels), levels_first: l.first, levels_now: l.levels.map((x) => round(x)) }));
    const mean = round(leaves.reduce((s, l) => s + l.entropy, 0) / leaves.length, 2);
    return { tree_id: t.id, mean_leaf_entropy: mean, flagged: false, loss: round(0.3 + mean * 0.5, 2), leaves };
  });
  const top = treeStats.reduce((a, b) => (b.mean_leaf_entropy > a.mean_leaf_entropy ? b : a));
  const flagTarget = treeStats.find((t) => t.tree_id === 'traffic.likelihood');
  flagTarget.mean_leaf_entropy = Math.max(top.mean_leaf_entropy + 0.02, 0.69);
  flagTarget.loss = 0.8;
  flagTarget.flagged = true;

  const learning = {
    curve,
    cards: {
      first: { right_level: curve[0].right_level, decided_without_officer: curve[0].decided_without_officer, precision: curve[0].precision },
      final: { right_level: last.right_level, decided_without_officer: last.decided_without_officer, precision: last.precision },
    },
    arms: [
      { name: 'First guess', loss: 1.23, approved: 0.46, risky_among_approved: 0.06, interval: [0.02, 0.14] },
      { name: 'Trained on labelled cases', loss: 0.48, approved: 0.8, risky_among_approved: 0.06, interval: [0.03, 0.12] },
      { name: 'Shuffled labels (control)', loss: 1.05, approved: 0.5, risky_among_approved: 0.17, interval: [0.1, 0.27] },
      { name: 'One LLM reads and decides (baseline)', loss: null, approved: 0.71, risky_among_approved: 0.11, interval: [0.06, 0.19] },
      { name: 'Jev asked directly', loss: 0.92, approved: 0.58, risky_among_approved: 0.09, interval: [0.04, 0.18] },
    ],
    final_test: {
      status: 'run', verdict: 'pass',
      conditions: [
        { name: 'Lower loss than the first guess', passed: true, detail: 'Difference 0.74, interval 0.61 to 0.86, which excludes zero.' },
        { name: 'Lower loss than the shuffled control', passed: true, detail: 'Difference 0.56, interval 0.44 to 0.69, which excludes zero.' },
        { name: 'More approvals than the first guess', passed: true, detail: 'Difference 34 points, interval 22 to 45, which excludes zero.' },
        { name: 'The test does not clearly show risky approvals above 5%', passed: true, detail: '3 of 52 approvals labelled risky. Interval 2% to 16%, so the lower end is under 5%.' },
      ],
      forbidden_permits: 0, risky_approvals: 3,
    },
    trees: treeStats,
    crossings: { status: 'released', loss_before: 0.8, loss_after: 0.58, text: 'Adding the question about many major crossings lowered this tree\'s loss on validation cases, so the policy owner released it.' },
    corrections: learningCorrections,
    officer: { reviewed: details.filter((d) => d.officer).length, corrections: learningCorrections.length, accuracy: manifest.officer_accuracy, level_accuracy: 0.9, label: OFFICER_LABEL },
  };

  const rules = {
    ordinance: [
      ['ORD-3.1', 'The application fee must be paid when the application is sent.'],
      ['ORD-3.2', 'The application form must be complete.'],
      ['ORD-3.3', 'Races may only be held on dates the city allows.'],
      ['ORD-5.2', 'A document that contradicts the form must be reviewed by an officer.'],
      ['ORD-5.3', 'A document that fits no listed type must be reviewed by an officer.'],
      ['ORD-5.4', 'If a system fails, an officer decides.'],
      ['ORD-5.5', 'While the stop switch is on, an officer decides every case.'],
      ['ORD-6.1', 'A case may be approved automatically only if its risk is under the low threshold.'],
      ['ORD-6.2', 'A case at or above the severity ceiling always goes to an officer.'],
      ['ORD-7.1', 'Every race must hold valid liability insurance for its venue and date.'],
      ['ORD-12.1', 'An arterial road closure raises the possible harm from traffic.'],
      ['ORD-12.2', 'The traffic plan must cover every road closure on the route.'],
      ['ORD-12.4', 'A race that closes a road should have a confirmed police escort.'],
      ['ORD-13.1', 'The medical plan must cover first aid and how to reach help.'],
      ['ORD-13.2', 'An ambulance should be agreed for the event.'],
      ['ORD-13.3', 'Races in June, July or August carry a higher heat risk.'],
      ['ORD-13.4', 'A hospital more than 10 km away raises the possible harm of an emergency.'],
      ['ORD-14.1', 'A crowd of more than 800 people raises the possible harm of crowding.'],
      ['ORD-14.2', 'The crowd plan must cover entry, exit and marshals.'],
      ['ORD-14.3', 'A narrow start or finish raises the possible harm of crowding.'],
    ].map(([id, text]) => ({ id, text })),
    evidence_types: [
      { id: 'certificate_of_insurance', name: 'Certificate of insurance', fields: ['named insured', 'venue', 'start date', 'end date', 'coverage'], terms: ['COI', 'insurance certificate'] },
      { id: 'police_escort_letter', name: 'Police escort letter', fields: ['date', 'route'], terms: ['escort confirmation'] },
      { id: 'police_escort_email', name: 'Police escort email', fields: ['date', 'route'], terms: ['escort email'] },
      { id: 'ambulance_agreement', name: 'Ambulance agreement', fields: ['provider', 'hours'], terms: ['EMS agreement'] },
    ],
    requirements: [{ id: 'event_insurance', name: 'Event liability insurance', evidence_type: 'certificate_of_insurance', clause: 'ORD-7.1' }],
    does_not_count: [{ id: 'broker_letter', name: 'Broker letter', why: 'It says a certificate will follow, and is not the certificate.' }],
    settings: [
      { key: 'decision.risky_approval_target', value: 0.05, limits: { min: 0.01, max: 0.15 }, owner: 'policy_owner', why: 'The share of automatic approvals the city accepts being labelled risky.', if_raised: 'More events are approved automatically, and risky approvals may rise.' },
      { key: 'decision.high_risk_precision_target', value: 0.85, limits: { min: 0.5, max: 0.99 }, owner: 'policy_owner', why: 'How sure the system must be before calling a case high risk.', if_raised: 'Fewer cases are marked high risk, and more fall in the review band.' },
      { key: 'decision.severity_ceiling', value: 0.85, limits: { min: 0.5, max: 1 }, owner: 'policy_owner', why: 'A rare catastrophe can hide inside a small product, so very severe cases always go to an officer.', if_raised: 'Fewer cases go to an officer for severity alone, and more rare catastrophes rest on the sum.' },
      { key: 'risk.anchors.likelihood', value: [0.02, 0.1, 0.3], limits: 'Fixed by the policy owner', owner: 'policy_owner', why: 'The number each likelihood level stands for.', if_raised: 'Every risk score rises, so fewer cases are approved until thresholds are re-chosen.' },
      { key: 'risk.anchors.severity', value: [0.1, 0.4, 1.0], limits: 'Fixed by the policy owner', owner: 'policy_owner', why: 'The number each severity level stands for.', if_raised: 'Every risk score rises, so fewer cases are approved until thresholds are re-chosen.' },
      { key: 'corrections.discount', value: 0.93, limits: { min: 0.5, max: 1 }, owner: 'policy_owner', why: 'How much weight older corrections keep.', if_raised: 'Old corrections fade more slowly.' },
      { key: 'evidence.p_supported', value: 0.9, limits: { min: 0.5, max: 0.99 }, owner: 'steward', why: 'How much a supported proof counts as a yes in the trees.', if_raised: 'A supported proof lowers risk a little more.' },
    ],
    hazards: Object.entries(HAZARDS).map(([id, name]) => ({ id, name, applies_when: id === 'traffic_conflict' ? 'A road closes.' : id === 'crowd_pressure' ? 'Runners and spectators add up to 300 or more.' : 'Always.' })),
  };

  const write = (path, data) => {
    mkdirSync(dirname(join(OUT, path)), { recursive: true });
    writeFileSync(join(OUT, path), JSON.stringify(data));
  };
  write('manifest.json', manifest);
  write('events.json', events);
  write('cases.json', rows);
  write('learning.json', learning);
  write('rules.json', rules);
  for (const d of details) write(`cases/${d.case_id}.json`, d);

  const codes = new Set(rows.map((r) => r.reason_code));
  const routes = new Set(rows.map((r) => r.route));
  const missing = Object.keys(REASON_TEXT).filter((c) => !codes.has(c));
  if (missing.length) throw new Error(`The fixture misses reason codes: ${missing.join(', ')}`);
  for (const r of ['approved', 'returned', 'proposed_denial', 'officer']) if (!routes.has(r)) throw new Error(`The fixture misses route ${r}`);
  console.log(`${rows.length} cases, ${events.length} events, ${curve.length} curve points, ${reviews} reviews that taught, ${learningCorrections.length} corrections. Right level ${fmtRate(curve[0].right_level)} to ${fmtRate(last.right_level)}. Written to ${OUT}`);
}

main();

#!/usr/bin/env python3
"""Scores stored real reads against the hidden case cards. Makes no model calls. Reads only cards, never labels.

Run from the repository root: uv run python scripts/check_read.py [--split validation] [--model MODEL]
"""
import argparse, json, statistics as st
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--split', default=None)
ap.add_argument('--model', default=None, help='by default, the one model with stored reads')
args = ap.parse_args()

cards = {}
for line in open('data/cards.jsonl'):
    c = json.loads(line)
    cards[c['case_id']] = c
folder = Path('cache/records/real') / (args.model or next(Path('cache/records/real').iterdir()).name)
records = [json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))]
if args.split:
    records = [r for r in records if cards[r['case_id']]['split'] == args.split]


def expected(evidence_type, f):
    if evidence_type == 'certificate_of_insurance':
        return {'valid': 'supported', 'expired': 'unsupported or contradicted', 'wrong_venue': 'unsupported or contradicted'}.get(f['insurance'], 'not found')
    if evidence_type in ('police_escort_letter', 'police_escort_email'):
        ev = f['escort_evidence']
        if ev == 'contradicting':
            return 'contradicted'
        if ev == 'none':
            return 'not found'
        return 'supported' if f['escort_arranged'] else 'unsupported'
    if evidence_type == 'ambulance_agreement':
        if f['ambulance_evidence'] == 'none':
            return 'not found'
        return 'supported' if f['ambulance_arranged'] else 'unsupported'
    return None


status = Counter()
agree = Counter()
wrong = []
jev = {}
for r in records:
    f = cards[r['case_id']]['facts']
    status[('stopped', r.get('stopped'))] += 1
    for stage in ('first_pass', 'judge', 'jev'):
        status[(stage, r[stage]['status'])] += 1
    fp = (r['first_pass'].get('output') or {}).get('evidence', [])
    found = {e['evidence_type'] for e in fp if e.get('status') == 'found'}
    verdicts = {v['evidence_type']: v for v in (r['judge'].get('output') or {}).get('verdicts', [])}
    for t in r.get('needed_types', []):
        want = expected(t, f)
        if want is None:
            continue
        if t in ('police_escort_letter', 'police_escort_email'):
            want_type = {'letter': 'police_escort_letter', 'contradicting': 'police_escort_letter', 'email': 'police_escort_email'}.get(f['escort_evidence'])
            if t != want_type:
                want = 'not found'
        if want == 'not found':
            got = 'not found' if t not in found else 'found:' + verdicts.get(t, {}).get('verdict', 'no verdict')
        else:
            got = verdicts[t]['verdict'] if t in verdicts else ('found, no verdict' if t in found else 'not found')
        ok = got in want.split(' or ')
        agree[(t, 'right' if ok else 'wrong')] += 1
        if not ok:
            wrong.append((r['case_id'], t, want, got, (verdicts.get(t) or {}).get('reason')))
    for q, p in (r['jev'].get('answers') or {}).items():
        jev.setdefault(q, {True: [], False: []})[bool(f[q])].append(p)

print(f'{len(records)} records, split {args.split or "all"}, model {args.model}')
print('status:', dict(sorted(((f"{a}={b}", n) for (a, b), n in status.items()))))
print('\nVerdicts against the cards:')
for t in sorted({k[0] for k in agree}):
    r, w = agree[(t, 'right')], agree[(t, 'wrong')]
    print(f'  {t:28s} right {r:4d}  wrong {w:3d}  {r / (r + w):.1%}')
print('\nJev against the cards (mean probability of yes when the fact is true and false; share on the right side of 0.5):')
for q, d in sorted(jev.items()):
    t, n = d[True], d[False]
    right = (sum(p >= .5 for p in t) + sum(p < .5 for p in n)) / max(len(t) + len(n), 1)
    print(f'  {q:24s} true {st.mean(t) if t else float("nan"):.2f} (n={len(t)})  false {st.mean(n) if n else float("nan"):.2f} (n={len(n)})  right side {right:.1%}')
print('\nWrong verdicts, up to 25:')
for row in wrong[:25]:
    print(' ', row[0], row[1], 'want', row[2], 'got', row[3], '|', (row[4] or '')[:110])
print('\nUnmapped documents reported:', Counter(u.get('document') for r in records for u in (r['first_pass'].get('output') or {}).get('unmapped_documents', [])).most_common(8))
print('Planted patterns:', Counter(p for r in records for p in cards[r['case_id']].get('planted', [])).most_common())

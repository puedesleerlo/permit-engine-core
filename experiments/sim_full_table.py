#!/usr/bin/env python3
"""Run simulated cases through every row of the decision table, at the design's case mix.

Answers review finding design-1-M4: what share of cases reaches each row, how does the severity ceiling change that,
and how many approvals would the test set hold? Offline, simulated answers, no API calls. Reality and evidence are not
separated here beyond the fact noise in sim_data_plan.py, so treat these as rough shares.
"""
import math, random, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sim_corrections as sc
m = sc.m
sc.DRIFT['on'] = False

def sample(rng, n, closure=0.7):
    out = []
    while len(out) < n:
        c = m.sample_case(rng)
        keep = closure if c['road_closure'] else 1 - closure
        if rng.random() < keep / max(closure, 1 - closure):
            sc.prep(c)
            u = rng.random()
            c['insurance'] = 'valid' if u < .70 else 'failed' if u < .85 else 'unmapped' if u < .925 else 'missing'
            c['basic_fail'] = rng.random() < .04
            c['contradict'] = c['road_closure'] and rng.random() < .05
            c['replies'] = rng.random() < .7
            out.append(c)
    return out

def highest_severity(model, c):
    return max(sc.expect(model[st_], c['r'][st_], m.S_A) for h, (lt, st_) in m.HAZARDS.items() if m.applies(h, c))

def risk_if_supported(model, c):
    """Risk with open evidence supported: the escort and ambulance readings set to their supported value."""
    r = dict(c['r'])
    tot = 0.0
    for h, (lt, st_) in m.HAZARDS.items():
        if not m.applies(h, c):
            continue
        L = sc.expect(model[lt], sc_reach(lt, c), m.L_A)
        S = sc.expect(model[st_], sc_reach(st_, c), m.S_A)
        tot += L * S
    return tot

def sc_reach(tree, c):
    obs = dict(c['obs'])
    for n in ('escort', 'ambulance'):
        if n in obs and obs[n] < .5:
            obs[n] = .9
    d = dict(c); d['obs'] = obs
    return m.reach(m.names_of(tree), d)

def route(model, c, tl, th, ceiling):
    if c['basic_fail']:
        return 'row0 basic'
    risk = sc.risk(model, c)
    if c['contradict'] or c['insurance'] == 'unmapped' or highest_severity(model, c) >= ceiling:
        return 'row1 ceiling' if (not c['contradict'] and c['insurance'] != 'unmapped') else 'row1 other'
    if c['insurance'] == 'failed':
        return 'row2 failed'
    letter = c['insurance'] == 'missing' or (risk >= tl and risk_if_supported(model, c) < tl)
    if letter:
        if not c['replies']:
            return 'letter, no reply'
        if c['insurance'] == 'missing' or risk_if_supported(model, c) >= tl:
            pass
        risk = risk_if_supported(model, c) if risk >= tl else risk
    if risk < tl:
        return 'row5 approved after letter' if letter else 'row5 approved'
    return 'row6 high' if risk >= th else 'row7 band'

def main():
    rows = {}
    keys = ['row0 basic', 'row1 other', 'row1 ceiling', 'row2 failed', 'letter, no reply', 'row5 approved', 'row5 approved after letter', 'row6 high', 'row7 band']
    risky_share = []
    for ceiling in (0.70, 0.85, 0.95, 9.0):
        tally = []
        for seed in range(20):
            rng = random.Random(seed)
            train = sample(rng, 180); val = sample(rng, 120); test = sample(rng, 2000)
            model = {t: m.fit(t, train)[0] for t in sc.TREES}
            eligible = [c for c in val if not c['basic_fail'] and highest_severity(model, c) < ceiling]
            tl, th = m.thresholds([(sc.risk(model, c), c['risky']) for c in eligible]) if len(eligible) > 5 else (0.0, 9.0)
            res = {k: 0 for k in keys}; risky = 0; appr = 0
            for c in test:
                r = route(model, c, tl, th, ceiling)
                res[r] += 1
                if r.startswith('row5'):
                    appr += 1; risky += c['risky']
            tally.append({**{k: v / len(test) for k, v in res.items()}, 'risky_appr': risky / max(appr, 1), 'elig': len(eligible), 'tl': tl, 'th': th})
            risky_share.append(sum(c['risky'] for c in test) / len(test))
        rows[ceiling] = tally
    print(f'Labelled risky at a cut of {m.TAU}, 70% road closure: {st.mean(risky_share):.3f}')
    print('Share of cases per route, mean of 20 seeds, 2000 test cases each. Ceiling 9.00 means no ceiling.\n')
    head = ''.join(f'{c:>9.2f}' for c in rows)
    print(f"{'route':>30}{head}")
    for k in keys:
        print(f"{k:>30}" + ''.join(f"{st.mean(t[k] for t in rows[c]):>9.3f}" for c in rows))
    print(f"{'all approved':>30}" + ''.join(f"{st.mean(t['row5 approved'] + t['row5 approved after letter'] for t in rows[c]):>9.3f}" for c in rows))
    print(f"{'risky among approved':>30}" + ''.join(f"{st.mean(t['risky_appr'] for t in rows[c]):>9.3f}" for c in rows))
    print(f"{'validation cases fitted':>30}" + ''.join(f"{st.mean(t['elig'] for t in rows[c]):>9.1f}" for c in rows))
    print(f"{'t_low':>30}" + ''.join(f"{st.mean(t['tl'] for t in rows[c]):>9.3f}" for c in rows))
    print(f"{'t_high':>30}" + ''.join(f"{st.mean(t['th'] for t in rows[c]):>9.3f}" for c in rows))
    print('\nApprovals in a 100-case test, and the standard error at a true 6% rate:')
    for c in rows:
        a = st.mean(t['row5 approved'] + t['row5 approved after letter'] for t in rows[c]) * 100
        print(f'  ceiling {c:.2f}: {a:.0f} approvals, standard error {math.sqrt(.06*.94/max(a,1)):.3f}')

if __name__ == '__main__':
    main()

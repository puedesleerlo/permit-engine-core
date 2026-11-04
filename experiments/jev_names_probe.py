#!/usr/bin/env python3
"""Can real Jev name the wrong tree and its right level, instead of an officer?

Uses the simulated world from sim_corrections.py. All cases are synthetic. For cases the trained system got wrong,
Jev sees the case facts, the system's estimates and the officer's finding (risky or not), plus plain definitions of
hazards and levels. It never sees the truth table. It answers two questions per applicable tree: is this estimate
wrong, and which level is right.

Run: python3 jev_names_probe.py --limit 3     (smoke test)
     python3 jev_names_probe.py               (40 cases after a world shift, 20 with no shift)
Results: results/jev_names_probe.json (raw answers, no key) and results/jev_names_probe.txt
"""
import json, random, statistics as st, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sim_corrections as sc
m = sc.m

API = 'https://api.typesafe.ai/v1/systemone'
MODEL = 'jev-latest'
ENV = HERE.parents[1] / 'jev_exp' / '.env'
ETA = 1.5
NAMES = {'traffic': 'traffic_conflict', 'crowd': 'crowd_pressure', 'medical': 'medical_emergency'}
HAZARD_TEXT = {
    'traffic_conflict': 'A vehicle and a runner or marshal collide or nearly collide on the race route.',
    'crowd_pressure': 'People are crushed or trapped because too many are packed into one place.',
    'medical_emergency': 'A runner or spectator needs urgent medical care during the event.',
}
LEVELS = {
    'L': {'rare': 'Not expected at an event like this one.', 'possible': 'Could well happen at an event like this one.', 'likely': 'Expected to happen at an event like this one, unless something changes.'},
    'S': {'minor': 'If it happens, treated on site, with no lasting harm.', 'serious': 'If it happens, people need hospital care but recover.', 'critical': 'If it happens, it is life-threatening or causes lasting harm.'},
}

def key():
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith('JEV_API_KEY') and '=' in line:
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    sys.exit('JEV_API_KEY not found in jev_exp/.env')

def yn(v):
    return 'yes' if v else 'no'

def facts(c):
    return {
        'expected_crowd': {'small': 'under 300', 'medium': '300 to 800', 'large': 'over 800'}[c['crowd']],
        'road_closure': yn(c['road_closure']), 'arterial_road': yn(c['arterial']), 'many_major_crossings': yn(c['crossings']),
        'police_escort_arranged': yn(c['escort']), 'traffic_plan_adequate': yn(c['traffic_plan']),
        'crowd_plan_adequate': yn(c['crowd_plan']), 'narrow_venue': yn(c['narrow']),
        'medical_plan_adequate': yn(c['medical_plan']), 'hot_date': yn(c['hot']),
        'ambulance_on_site': yn(c['ambulance']), 'hospital_far': yn(c['hospital_far']),
    }

def payload(c, base, finding):
    est, qs = {}, {}
    for h, (lt, st_) in m.HAZARDS.items():
        if not m.applies(h, c):
            continue
        name = NAMES[h]
        est[name] = {}
        for t, scale, word in ((lt, 'L', 'likelihood'), (st_, 'S', 'severity')):
            d = sc.dist(base[t], c['r'][t])
            est[name][word] = {lv: round(p, 2) for lv, p in zip(LEVELS[scale], d)}
            qs[f'wrong__{t}'] = {'type': 'noul', 'instructions': f'Judging from `case_facts` and `officer_finding`, is the system\'s {word} estimate for the {name} hazard (`system_estimates.{name}.{word}`) wrong for this case? {name} means: {HAZARD_TEXT[name]}'}
            qs[f'level__{t}'] = {'type': 'choice', 'instructions': f'Judging from `case_facts`, which {word} level is right for the {name} hazard at this event? {name} means: {HAZARD_TEXT[name]}', 'criteria': LEVELS[scale]}
    state = {'event': 'A street race that needs a city permit.', 'case_facts': facts(c), 'system_estimates': est, 'officer_finding': finding}
    return {'model': MODEL, 'state': state, 'questions': qs}

def call(body, k, tries=5):
    data = json.dumps(body).encode()
    for attempt in range(tries):
        req = urllib.request.Request(API, data=data, headers={'Authorization': f'Bearer {k}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f'Jev returned HTTP {e.code}: {e.read().decode()[:300]}')
        except urllib.error.URLError:
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

def wrong_cases(base, tl, th, pool, n):
    out = []
    for c in pool:
        R = sc.risk(base, c)
        if (R < tl and c['risky']) or (R >= th and not c['risky']):
            out.append(c)
        if len(out) == n:
            break
    return out

def finding(c):
    return ('The officer ruled this event risky, but the system had approved it automatically.' if c['risky']
            else 'The officer ruled this event not risky, but the system had rated it high risk.')

def run_set(cases, base, k):
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(lambda c: call(payload(c, base, finding(c)), k), cases))

def score(cases, answers, base):
    rows = []
    for c, a in zip(cases, answers):
        wrong = set(sc.named_trees(base, c))
        for t in sc.applicable(c):
            w = a['answers'][f'wrong__{t}']['noul']
            scale = 'L' if t.endswith('.L') else 'S'
            lv = list(LEVELS[scale]).index(a['answers'][f'level__{t}']['choice'])
            rows.append(dict(tree=t, truly_wrong=t in wrong, jev_wrong=w, jev_level=lv, level=c['y'][t], base_map=max(range(3), key=lambda j: sc.dist(base[t], c['r'][t])[j])))
    return rows

def rate(xs):
    return (sum(xs) / len(xs)) if xs else float('nan')

def summary(rows, label):
    pos = [r for r in rows if r['truly_wrong']]
    neg = [r for r in rows if not r['truly_wrong']]
    sens = rate([r['jev_wrong'] >= .5 for r in pos])
    spec = rate([r['jev_wrong'] < .5 for r in neg])
    lvl = rate([r['jev_level'] == r['level'] for r in rows])
    lvl_wrong = rate([r['jev_level'] == r['level'] for r in pos])
    base_lvl = rate([r['base_map'] == r['level'] for r in rows])
    print(f'{label}: {len(rows)} tree judgments, {len(pos)} truly wrong')
    print(f'  flags a truly wrong tree (sensitivity) {sens:.3f}; clears a right tree (specificity) {spec:.3f}')
    print(f'  picks the right level, all trees {lvl:.3f}; on truly wrong trees {lvl_wrong:.3f}; the trained system itself on all trees {base_lvl:.3f}')
    return sens, spec, lvl_wrong

def apply_updates(mode, base, base_counts, cases, answers, test, tl, th):
    model = {t: [list(d) for d in base[t]] for t in sc.TREES}
    logits = {t: sc.to_logits(base[t]) for t in sc.TREES}
    for c, a in zip(cases, answers):
        if mode == 'officer':
            for t in sc.named_trees(model, c):
                sc.grad_level(model, logits, t, c, ETA)
        elif mode == 'jev':
            for t in sc.applicable(c):
                if a['answers'][f'wrong__{t}']['noul'] >= .5:
                    scale = 'L' if t.endswith('.L') else 'S'
                    y = list(LEVELS[scale]).index(a['answers'][f'level__{t}']['choice'])
                    sc.grad_level(model, logits, t, c, ETA, y=y)
    o = sc.outcomes(model, test, tl, th)
    o['drift_loss'] = sc.tree_loss(model, sc.DRIFT_TREE, test)
    o['other_loss'] = st.mean(sc.tree_loss(model, t, test) for t in sc.TREES if t != sc.DRIFT_TREE)
    o['all_loss'] = st.mean(sc.tree_loss(model, t, test) for t in sc.TREES)
    return o

def main():
    k = key()
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    rng = random.Random(0)
    sc.DRIFT['on'] = False
    train = sc.sample(rng, 180); val0 = sc.sample(rng, 120)
    base, base_counts = {}, {}
    for t in sc.TREES:
        base[t], base_counts[t] = m.fit(t, train)
    tl, th = m.thresholds([(sc.risk(base, c), c['risky']) for c in val0])
    stable_pool = sc.sample(rng, 900)
    stable_cases = wrong_cases(base, tl, th, stable_pool, limit or 20)
    sc.DRIFT['on'] = True
    pool = sc.sample(rng, 900); test = sc.sample(rng, 800)
    drift_cases = wrong_cases(base, tl, th, pool, limit or 40)

    t0 = time.time()
    a_drift = run_set(drift_cases, base, k)
    a_stable = run_set(stable_cases, base, k)
    usage = [a['usage'] for a in a_drift + a_stable]
    models = sorted({a['model'] for a in a_drift + a_stable})
    print(f'requests {len(usage)}; input tokens {sum(u["input_tokens"] for u in usage)}; output tokens {sum(u["output_tokens"] for u in usage)}; returned model {models}; {time.time() - t0:.0f} s')

    r_drift = score(drift_cases, a_drift, base)
    r_stable = score(stable_cases, a_stable, base)
    sens, spec, lvl = summary(r_stable, 'No world shift')
    s2, sp2, l2 = summary(r_drift, 'After the world shift')
    d = [r for r in r_drift if r['tree'] == sc.DRIFT_TREE]
    print(f'  on the shifted tree alone: flagged {rate([r["jev_wrong"] >= .5 for r in d]):.3f}, right level {rate([r["jev_level"] == r["level"] for r in d]):.3f} (n={len(d)})')
    allr = r_stable + r_drift
    pos = [r for r in allr if r['truly_wrong']]; neg = [r for r in allr if not r['truly_wrong']]
    print(f'measured, all cases: --sens {rate([r["jev_wrong"] >= .5 for r in pos]):.3f} --spec {rate([r["jev_wrong"] < .5 for r in neg]):.3f} --level {rate([r["jev_level"] == r["level"] for r in pos]):.3f}')
    print(f'\nApplying the same {len(drift_cases)} corrections after the shift (one seed; gradient step {ETA}; thresholds fixed):')
    for mode in ('none', 'officer', 'jev'):
        o = apply_updates(mode, base, base_counts, drift_cases, a_drift, test, tl, th)
        print(f'  {mode:8s} shifted tree loss {o["drift_loss"]:.3f}, other trees {o["other_loss"]:.3f}, all {o["all_loss"]:.3f}; auto {o["auto"]:.3f}, wrong among approved {o["wrong"]:.3f}, band {o["band"]:.3f}')
    if not limit:
        out = {'model_returned': models, 'usage': usage,
               'drift': [{'facts': facts(c), 'finding': finding(c), 'labels': c['y'], 'answers': a['answers']} for c, a in zip(drift_cases, a_drift)],
               'stable': [{'facts': facts(c), 'finding': finding(c), 'labels': c['y'], 'answers': a['answers']} for c, a in zip(stable_cases, a_stable)]}
        (HERE / 'results' / 'jev_names_probe.json').write_text(json.dumps(out, indent=1))

if __name__ == '__main__':
    main()

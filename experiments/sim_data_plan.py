#!/usr/bin/env python3
"""Offline check of the proposed data plan. No API calls. LLM and Jev are replaced by noisy simulated answers.

World: one event type (street race), three reusable hazards, a likelihood tree and a severity tree per hazard.
Tree weights: each leaf holds a distribution over three levels. Training is soft counting (EM) from the
policy maker's first guess. risk = sum over applicable hazards of L x S. Two thresholds are picked on validation.
"""
import math, random, statistics as st

L_A = [.02, .10, .30]      # likelihood anchors: rare, possible, likely
S_A = [.10, .40, 1.00]     # severity anchors: minor, serious, critical
TAU = 0.10                 # a case is labelled risky if labelled risk >= TAU
NOISE = .08                # label noise: chance an expert label moves one level
KAPPA = 2.0                # strength of the policy maker's first guess, in pseudo-cases
FACT_OK = .92              # chance the LLM's verdict is right
EPS = 1e-9

# Tree: questions in order. Yes means the safe answer for "good" questions; the score functions say what counts.
TREES = {
    'traffic.L': dict(hazard='traffic', q=[('escort', 'fact'), ('traffic_plan', 'jev')]),
    'traffic.S': dict(hazard='traffic', q=[('arterial', 'rule'), ('large', 'rule')]),
    'crowd.L':   dict(hazard='crowd',   q=[('crowd_plan', 'jev'), ('large', 'rule')]),
    'crowd.S':   dict(hazard='crowd',   q=[('narrow', 'jev'), ('large', 'rule')]),
    'medical.L': dict(hazard='medical', q=[('medical_plan', 'jev'), ('hot', 'rule')]),
    'medical.S': dict(hazard='medical', q=[('ambulance', 'fact'), ('hospital_far', 'rule')]),
}
HAZARDS = {'traffic': ('traffic.L', 'traffic.S'), 'crowd': ('crowd.L', 'crowd.S'), 'medical': ('medical.L', 'medical.S')}
BAD_IF_NO = {'escort', 'traffic_plan', 'crowd_plan', 'medical_plan', 'ambulance'}

def bad(name, v):
    return (1 - v) if name in BAD_IF_NO else v

def true_level(tree, c):
    """The hidden truth. traffic.L also depends on 'crossings', which the first tree does not ask about."""
    s = sum(bad(n, c[n]) for n, _ in TREES[tree]['q'])
    if tree == 'traffic.L':
        s += c['crossings']
    return min(s, 2)

def first_guess_level(tree, bits):
    """The policy maker's first guess looks only at the first question, so it under-rates cases."""
    n = TREES[tree]['q'][0][0]
    return min(bad(n, bits[0]), 2)

def applies(h, c):
    return {'traffic': c['road_closure'], 'crowd': 1 if c['crowd'] != 'small' else 0, 'medical': 1}[h]

def sample_case(rng):
    c = {k: rng.randint(0, 1) for k in ('road_closure', 'escort', 'traffic_plan', 'crossings', 'arterial', 'crowd_plan',
                                         'narrow', 'medical_plan', 'hot', 'ambulance', 'hospital_far')}
    c['crowd'] = rng.choice(['small', 'medium', 'large'])
    c['large'] = 1 if c['crowd'] == 'large' else 0
    # What the models report
    obs = {}
    for t in TREES.values():
        for n, kind in t['q']:
            if n in obs:
                continue
            if kind == 'rule':
                obs[n] = float(c[n])
            elif kind == 'fact':
                said = c[n] if rng.random() < FACT_OK else 1 - c[n]
                obs[n] = .9 if said else .1
            else:
                obs[n] = rng.betavariate(6, 1.5) if c[n] else rng.betavariate(1.5, 6)
    obs['crossings'] = float(c['crossings'])
    c['obs'] = obs
    # Expert labels with noise
    y = {}
    for tree in TREES:
        v = true_level(tree, c)
        if rng.random() < NOISE:
            v = max(0, min(2, v + rng.choice([-1, 1])))
        y[tree] = v
    c['y'] = y
    c['true_risk'] = sum(L_A[y[HAZARDS[h][0]]] * S_A[y[HAZARDS[h][1]]] for h in HAZARDS if applies(h, c))
    c['risky'] = c['true_risk'] >= TAU
    return c

def leaves(k):
    return [tuple((i >> j) & 1 for j in range(k)) for i in range(2 ** k)]

def reach(names, c):
    out = []
    for bits in leaves(len(names)):
        p = 1.0
        for n, b in zip(names, bits):
            o = c['obs'][n]
            p *= o if b else 1 - o
        out.append(p)
    return out

def prior(tree, extra=()):
    k = len(TREES[tree]['q'])
    th = []
    for bits in leaves(k + len(extra)):
        lv = first_guess_level(tree, bits)
        d = [.1, .1, .1]
        d[lv] = .8
        th.append(d)
    return th

def names_of(tree, extra=()):
    return [n for n, _ in TREES[tree]['q']] + list(extra)

def fit(tree, cases, extra=(), labels=None, iters=6):
    names = names_of(tree, extra)
    p0 = prior(tree, extra)
    th = [list(d) for d in p0]
    use = [(c, c['y'][tree]) for c in cases if applies(TREES[tree]['hazard'], c)]
    if labels is not None:
        ys = [y for _, y in use]
        labels.shuffle(ys)
        use = [(c, y) for (c, _), y in zip(use, ys)]
    counts = None
    for _ in range(iters):
        counts = [[KAPPA * v for v in d] for d in p0]
        for c, y in use:
            r = reach(names, c)
            w = [ri * th[l][y] for l, ri in enumerate(r)]
            z = sum(w) or EPS
            for l, wi in enumerate(w):
                counts[l][y] += wi / z
        th = [[v / sum(d) for v in d] for d in counts]
    return th, counts

def pred(names, th, c):
    r = reach(names, c)
    return [sum(r[l] * th[l][j] for l in range(len(r))) for j in range(3)]

def case_risk(model, c, extra=None):
    extra = extra or {}
    tot = 0.0
    for h, (lt, st_) in HAZARDS.items():
        if not applies(h, c):
            continue
        pl = pred(names_of(lt, extra.get(lt, ())), model[lt], c)
        ps = pred(names_of(st_, extra.get(st_, ())), model[st_], c)
        tot += sum(p * a for p, a in zip(pl, L_A)) * sum(p * a for p, a in zip(ps, S_A))
    return tot

def thresholds(val, wrong_target=.05, high_target=.15):
    rows = sorted(val)
    cand = sorted({r for r, _ in rows})
    t_low = 0.0
    for t in cand:
        below = [k for r, k in rows if r < t]
        if below and sum(below) / len(below) <= wrong_target:
            t_low = t
    t_high = cand[-1] + EPS
    for t in reversed(cand):
        above = [k for r, k in rows if r >= t]
        if above and (len(above) - sum(above)) / len(above) <= high_target:
            t_high = t
    if t_high < t_low:
        t_low = t_high = (t_low + t_high) / 2
    return t_low, t_high

def evaluate(model, test, tl, th, extra=None):
    auto, band, high = [], [], []
    for c in test:
        r = case_risk(model, c, extra)
        (auto if r < tl else high if r >= th else band).append(c)
    n = len(test)
    return dict(auto=len(auto) / n, band=len(band) / n, high=len(high) / n,
                wrong_auto=(sum(c['risky'] for c in auto) / len(auto)) if auto else float('nan'),
                high_prec=(sum(c['risky'] for c in high) / len(high)) if high else float('nan'))

def logloss(model, tree, test, extra=()):
    names = names_of(tree, extra)
    vals = [-math.log(max(pred(names, model[tree], c)[c['y'][tree]], 1e-6)) for c in test if applies(TREES[tree]['hazard'], c)]
    return sum(vals) / len(vals)

def entropy(d):
    return -sum(p * math.log(p) for p in d if p > 0)

def fmt(x):
    return f'{x:.3f}'

def run(seed, n_train, n_val=60, n_test=800):
    rng = random.Random(seed)
    train = [sample_case(rng) for _ in range(n_train)]
    val = [sample_case(rng) for _ in range(n_val)]
    test = [sample_case(rng) for _ in range(n_test)]
    first = {t: prior(t) for t in TREES}
    trained = {t: fit(t, train)[0] for t in TREES}
    shuffled = {t: fit(t, train, labels=random.Random(seed + 999))[0] for t in TREES}
    out = {}
    for name, m in (('first guess', first), ('trained', trained), ('shuffled', shuffled)):
        tl, th = thresholds([(case_risk(m, c), c['risky']) for c in val])
        e = evaluate(m, test, tl, th)
        e['loss'] = st.mean(logloss(m, t, test) for t in TREES)
        e['tl'], e['th'] = tl, th
        out[name] = e
    return out

def main():
    rng = random.Random(1)
    big = [sample_case(rng) for _ in range(20000)]
    print(f"share labelled risky at TAU={TAU}: {sum(c['risky'] for c in big) / len(big):.3f}")
    rs = sorted(c['true_risk'] for c in big)
    print('labelled risk quantiles 10/50/90:', fmt(rs[2000]), fmt(rs[10000]), fmt(rs[18000]))

    print('\n=== Test-set result by training size (mean of 20 seeds; validation = 60; test = 800) ===')
    print(f"{'train':>6} {'model':>12} {'loss':>6} {'auto':>6} {'wrong|auto':>11} {'band':>6} {'high':>6} {'risky|high':>11} {'t_low':>6} {'t_high':>7}")
    for n in (40, 80, 120, 180, 300):
        rows = [run(s, n) for s in range(20)]
        for name in ('first guess', 'trained', 'shuffled'):
            g = lambda k: st.mean(x for x in (r[name][k] for r in rows) if x == x)
            print(f"{n:>6} {name:>12} {g('loss'):>6.3f} {g('auto'):>6.3f} {g('wrong_auto'):>11.3f} {g('band'):>6.3f} {g('high'):>6.3f} {g('high_prec'):>11.3f} {g('tl'):>6.3f} {g('th'):>7.3f}")

    print('\n=== Entropy and the planted gap (train = 180; traffic.L ignores crossings) ===')
    rng = random.Random(7)
    train = [sample_case(rng) for _ in range(180)]
    test = [sample_case(rng) for _ in range(4000)]
    model = {t: fit(t, train)[0] for t in TREES}
    counts = {t: fit(t, train)[1] for t in TREES}
    for t in TREES:
        print(f"  {t:10s} mean leaf entropy {st.mean(entropy(d) for d in model[t]):.3f}   test loss {logloss(model, t, test):.3f}")
    print('  traffic.L leaves (escort, plan): distribution over rare/possible/likely, entropy, soft count')
    for bits, d, cnt in zip(leaves(2), model['traffic.L'], counts['traffic.L']):
        print(f"    {bits} {[round(x, 2) for x in d]} H={entropy(d):.3f} n={sum(cnt):.1f}")
    th2, _ = fit('traffic.L', train, extra=('crossings',))
    m2 = dict(model); m2['traffic.L'] = th2
    print(f"  after adding the crossings question: mean leaf entropy {st.mean(entropy(d) for d in th2):.3f}, test loss {logloss(m2, 'traffic.L', test, ('crossings',)):.3f}")

    print('\n=== One correction, in real time (train = 180) ===')
    th, cnt = fit('medical.S', train)
    leaf = 3  # ambulance yes? see bits below
    bits = leaves(2)[leaf]
    before = th[leaf]
    c2 = list(cnt[leaf]); low = min(range(3), key=lambda j: before[j]); c2[low] += 1
    after = [v / sum(c2) for v in c2]
    print(f"  medical.S leaf {bits}: {[round(x, 3) for x in before]} H={entropy(before):.3f} n={sum(cnt[leaf]):.1f}")
    print(f"  one correction to its least likely level: {[round(x, 3) for x in after]} H={entropy(after):.3f}")
    print('\n=== A single confident mistake: entropy versus loss ===')
    d = [.90, .08, .02]
    print(f"  prediction {d}: entropy {entropy(d):.3f} (of max {math.log(3):.3f}), loss if the true level is the last one {-math.log(d[2]):.3f}, loss if the first {-math.log(d[0]):.3f}")

if __name__ == '__main__':
    main()

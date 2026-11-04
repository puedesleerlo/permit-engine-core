#!/usr/bin/env python3
"""Compare ways a correction can change tree weights. Offline. Simulated answers, no API calls.

Scenario: trees are trained, then the world shifts for one tree (crowd likelihood rises one level). Officers correct
cases the system got wrong. Which correction method repairs the tree that is really wrong, without damaging others?

Methods:
  none        no update
  level-all   officer gives a level for every applicable tree; soft count (+1 case share)
  level-named officer names only the trees that look wrong and gives their level; soft count
  grad-named  same input as level-named; gradient step on cross-entropy (backprop within that tree)
  grad-named-limit  grad-named, with each leaf level held within 0.10 of its released value
  grad-risk   officer gives only the outcome (risky or not); gradient through risk = sum(L x S) to every applicable tree
  bayes-outcome        officer gives only the outcome; a Bayesian network works back from it to each tree's level, by
                       exact enumeration, then adds those shares to leaf counts
  bayes-outcome-forget the same, discounting old counts on the leaves the case reached, so new evidence weighs more
  bayes-named-forget   officer names trees and levels; soft count with the same discount
  jev-sim-*            as grad-named, but a simulated Jev names the trees and levels, at a stated accuracy

Run: python3 sim_corrections.py [--sens S --spec S --level L]   (adds a jev-measured row at those accuracies)
"""
import math, random, sys, statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sim_data_plan as m

m.TAU = 0.30
TREES = list(m.TREES)
DRIFT_TREE = 'crowd.L'
_orig_true = m.true_level
DRIFT = {'on': False}

def true_level(tree, c):
    v = _orig_true(tree, c)
    if DRIFT['on'] and tree == DRIFT_TREE:
        v = min(2, v + 1)
    return v
m.true_level = true_level

SCALE = {t: (m.L_A if t.endswith('.L') else m.S_A) for t in TREES}

def prep(c):
    c['r'] = {t: m.reach(m.names_of(t), c) for t in TREES}
    return c

def sample(rng, n):
    return [prep(m.sample_case(rng)) for _ in range(n)]

def dist(th, r):
    return [sum(r[l] * th[l][j] for l in range(len(r))) for j in range(3)]

def expect(th, r, a):
    return sum(p * x for p, x in zip(dist(th, r), a))

def risk(model, c):
    tot = 0.0
    for h, (lt, st_) in m.HAZARDS.items():
        if m.applies(h, c):
            tot += expect(model[lt], c['r'][lt], m.L_A) * expect(model[st_], c['r'][st_], m.S_A)
    return tot

def softmax(z):
    mx = max(z); e = [math.exp(v - mx) for v in z]; s = sum(e)
    return [v / s for v in e]

def to_logits(th):
    return [[math.log(max(v, 1e-3)) for v in d] for d in th]

def applicable(c):
    out = []
    for h, pair in m.HAZARDS.items():
        if m.applies(h, c):
            out += list(pair)
    return out

def tree_loss(model, tree, cases):
    vals = [-math.log(max(dist(model[tree], c['r'][tree])[c['y'][tree]], 1e-6)) for c in cases if m.applies(m.TREES[tree]['hazard'], c)]
    return sum(vals) / max(len(vals), 1)

def named_trees(model, c):
    names = []
    for t in applicable(c):
        d = dist(model[t], c['r'][t])
        if max(range(3), key=lambda j: d[j]) != c['y'][t]:
            names.append(t)
    return names

def forget(counts, tree, r, gamma):
    if gamma is None:
        return
    for l in range(len(r)):
        f = gamma ** r[l]
        counts[tree][l] = [v * f for v in counts[tree][l]]

def soft_count(model, counts, tree, c, gamma=None):
    r = c['r'][tree]; y = c['y'][tree]; th = model[tree]
    w = [r[l] * th[l][y] for l in range(len(r))]
    z = sum(w) or 1e-9
    forget(counts, tree, r, gamma)
    for l, wi in enumerate(w):
        counts[tree][l][y] += wi / z
    model[tree] = [[v / sum(d) for v in d] for d in counts[tree]]

def grad_level(model, logits, tree, c, eta, y=None):
    r = c['r'][tree]; y = c['y'][tree] if y is None else y; th = model[tree]
    p = max(dist(th, r)[y], 1e-6)
    for l in range(len(r)):
        for i in range(3):
            delta = 1.0 if i == y else 0.0
            logits[tree][l][i] += eta * (1 / p) * r[l] * th[l][y] * (delta - th[l][i])
        th[l] = softmax(logits[tree][l])

def grad_risk(model, logits, c, target, c0, k, eta, ledger=None):
    R = risk(model, c)
    sig = 1 / (1 + math.exp(-max(min(k * (R - c0), 30), -30)))
    dL = k * (sig - (1.0 if target else 0.0))
    for h, (lt, st_) in m.HAZARDS.items():
        if not m.applies(h, c):
            continue
        L = expect(model[lt], c['r'][lt], m.L_A); S = expect(model[st_], c['r'][st_], m.S_A)
        for tree, other in ((lt, S), (st_, L)):
            a = SCALE[tree]; r = c['r'][tree]; th = model[tree]
            moved = 0.0
            for l in range(len(r)):
                A = sum(th[l][j] * a[j] for j in range(3))
                for j in range(3):
                    g = dL * other * r[l] * th[l][j] * (a[j] - A)
                    logits[tree][l][j] -= eta * g
                    moved += abs(eta * g)
                th[l] = softmax(logits[tree][l])
            if ledger is not None:
                ledger[tree] = ledger.get(tree, 0.0) + moved

def bayes_outcome(model, counts, c, target, c0, k, gamma=None):
    """Exact inference on the network: tree level nodes -> risk -> outcome. Then add expected counts to the leaves."""
    hz = [pair for h, pair in m.HAZARDS.items() if m.applies(h, c)]
    pi = {t: dist(model[t], c['r'][t]) for pair in hz for t in pair}
    q = {t: [0.0, 0.0, 0.0] for t in pi}
    def walk(i, weight, R, chosen):
        if i == len(hz):
            sig = 1 / (1 + math.exp(-max(min(k * (R - c0), 30), -30)))
            w = weight * (sig if target else 1 - sig)
            for t, j in chosen:
                q[t][j] += w
            return
        lt, st_ = hz[i]
        for a in range(3):
            for b in range(3):
                walk(i + 1, weight * pi[lt][a] * pi[st_][b], R + m.L_A[a] * m.S_A[b], chosen + [(lt, a), (st_, b)])
    walk(0, 1.0, 0.0, [])
    for t, row in q.items():
        z = sum(row) or 1e-9
        row = [v / z for v in row]
        r = c['r'][t]; th = model[t]
        forget(counts, t, r, gamma)
        for j in range(3):
            w = [r[l] * th[l][j] for l in range(len(r))]
            zz = sum(w) or 1e-9
            for l, wi in enumerate(w):
                counts[t][l][j] += row[j] * wi / zz
        model[t] = [[v / sum(d) for v in d] for d in counts[t]]

def run_stream(method, base, base_counts, pool, K, tl, th, eta=None, ledger=None, order_rev=False, jev=None, jrng=None):
    model = {t: [list(d) for d in base[t]] for t in TREES}
    counts = {t: [list(d) for d in base_counts[t]] for t in TREES}
    logits = {t: to_logits(base[t]) for t in TREES}
    c0 = (tl + th) / 2
    k = min(4 / max(th - tl, 1e-3), 40)
    made = 0
    seq = list(reversed(pool)) if order_rev else pool
    for c in seq:
        if made >= K:
            break
        R = risk(model, c)
        wrong = (R < tl and c['risky']) or (R >= th and not c['risky'])
        if not wrong:
            continue
        made += 1
        if method == 'none':
            continue
        if method == 'level-all':
            for t in applicable(c):
                soft_count(model, counts, t, c)
        elif method == 'level-named':
            for t in named_trees(model, c):
                soft_count(model, counts, t, c)
        elif method == 'grad-named':
            for t in named_trees(model, c):
                grad_level(model, logits, t, c, eta)
        elif method == 'grad-named-limit':
            for t in named_trees(model, c):
                grad_level(model, logits, t, c, eta)
                for l in range(len(model[t])):
                    d = [min(max(v, b - LIMIT), b + LIMIT) for v, b in zip(model[t][l], base[t][l])]
                    z = sum(d)
                    model[t][l] = [v / z for v in d]
                    logits[t][l] = [math.log(max(v, 1e-6)) for v in model[t][l]]
        elif method == 'grad-risk':
            grad_risk(model, logits, c, c['risky'], c0, k, eta, ledger)
        elif method == 'bayes-outcome':
            bayes_outcome(model, counts, c, c['risky'], c0, k)
        elif method == 'bayes-outcome-forget':
            bayes_outcome(model, counts, c, c['risky'], c0, k, gamma=eta)
        elif method == 'bayes-named-forget':
            for t in named_trees(model, c):
                soft_count(model, counts, t, c, gamma=eta)
        elif method.startswith('jev-'):
            sens, spec, lvl = jev
            wrong = set(named_trees(model, c))
            for t in applicable(c):
                flag = jrng.random() < (sens if t in wrong else 1 - spec)
                if flag:
                    y = c['y'][t] if jrng.random() < lvl else jrng.choice([j for j in range(3) if j != c['y'][t]])
                    grad_level(model, logits, t, c, eta, y=y)
    return model, made

def outcomes(model, test, tl, th):
    auto = [c for c in test if risk(model, c) < tl]
    high = [c for c in test if risk(model, c) >= th]
    return dict(auto=len(auto) / len(test), wrong=(sum(c['risky'] for c in auto) / len(auto)) if auto else float('nan'),
                band=1 - (len(auto) + len(high)) / len(test))

def one_seed(seed, K):
    rng = random.Random(seed)
    DRIFT['on'] = False
    train = sample(rng, 180); val0 = sample(rng, 120)
    base, base_counts = {}, {}
    for t in TREES:
        base[t], base_counts[t] = m.fit(t, train)
    tl, th = m.thresholds([(risk(base, c), c['risky']) for c in val0])
    DRIFT['on'] = True
    pool = sample(rng, 900); val = sample(rng, 200); test = sample(rng, 800)
    res = {}
    METHODS = [('none', [None], None), ('level-all', [None], None), ('level-named', [None], None), ('grad-named', [0.25, 1.0, 3.0], None), ('grad-named-limit', [0.25, 1.0, 3.0], None), ('grad-risk', [2.0, 10.0, 50.0], None),
               ('bayes-outcome', [None], None), ('bayes-outcome-forget', [0.85, 0.93, 0.98], None), ('bayes-named-forget', [0.85, 0.93, 0.98], None),
               ('jev-sim-random', [0.25, 1.0, 3.0], (0.5, 0.5, 0.33)), ('jev-sim-70', [0.25, 1.0, 3.0], (0.7, 0.7, 0.7)), ('jev-sim-90', [0.25, 1.0, 3.0], (0.9, 0.9, 0.9))]
    if JEV_MEASURED:
        METHODS.append(('jev-measured', [0.25, 1.0, 3.0], JEV_MEASURED))
    for method, etas, jev in METHODS:
        best = None
        for eta in etas:
            mdl, made = run_stream(method, base, base_counts, pool, K, tl, th, eta, jev=jev, jrng=random.Random(seed + 7))
            score = st.mean(tree_loss(mdl, t, val) for t in TREES)
            if best is None or score < best[0]:
                best = (score, eta, mdl, made)
        _, eta, mdl, made = best
        o = outcomes(mdl, test, tl, th)
        o['drift_loss'] = tree_loss(mdl, DRIFT_TREE, test)
        o['other_loss'] = st.mean(tree_loss(mdl, t, test) for t in TREES if t != DRIFT_TREE)
        o['all_loss'] = st.mean(tree_loss(mdl, t, test) for t in TREES)
        o['made'] = made; o['eta'] = eta if eta else 0
        res[method] = o
    # Where does grad-risk's change land, and does order matter?
    ledger = {}
    eta = next(o['eta'] for mth, o in res.items() if mth == 'grad-risk') or 10.0
    f, _ = run_stream('grad-risk', base, base_counts, pool, K, tl, th, eta, ledger)
    b, _ = run_stream('grad-risk', base, base_counts, pool, K, tl, th, eta, None, order_rev=True)
    tot = sum(ledger.values()) or 1e-9
    res['grad-risk']['drift_share'] = ledger.get(DRIFT_TREE, 0.0) / tot
    res['grad-risk']['order_gap'] = st.mean(abs(f[t][l][j] - b[t][l][j]) for t in TREES for l in range(4) for j in range(3))
    f2, _ = run_stream('level-named', base, base_counts, pool, K, tl, th)
    b2, _ = run_stream('level-named', base, base_counts, pool, K, tl, th, None, None, order_rev=True)
    res['level-named']['order_gap'] = st.mean(abs(f2[t][l][j] - b2[t][l][j]) for t in TREES for l in range(4) for j in range(3))
    return res

LIMIT = 0.10
NAMES = ['none', 'level-all', 'level-named', 'grad-named', 'grad-named-limit', 'grad-risk', 'bayes-outcome', 'bayes-outcome-forget', 'bayes-named-forget', 'jev-sim-random', 'jev-sim-70', 'jev-sim-90']
JEV_MEASURED = None

def main():
    global JEV_MEASURED
    if '--sens' in sys.argv:
        g = lambda f: float(sys.argv[sys.argv.index(f) + 1])
        JEV_MEASURED = (g('--sens'), g('--spec'), g('--level'))
    print(f'Scenario: trained on 180, then {DRIFT_TREE} truth rises one level. Mean of 20 seeds, test 800 per seed. Thresholds held fixed.')
    print(f"{'K':>3} {'method':>21} {'made':>5} {'drifted tree loss':>18} {'other trees loss':>17} {'all':>6} {'auto':>6} {'wrong|auto':>11} {'band':>6} {'eta':>5}")
    for K in (5, 20, 60):
        rows = [one_seed(s, K) for s in range(20)]
        for mth in NAMES + (['jev-measured'] if JEV_MEASURED else []):
            g = lambda k: st.mean(x for x in (r[mth][k] for r in rows) if x == x)
            print(f"{K:>3} {mth:>21} {g('made'):>5.1f} {g('drift_loss'):>18.3f} {g('other_loss'):>17.3f} {g('all_loss'):>6.3f} {g('auto'):>6.3f} {g('wrong'):>11.3f} {g('band'):>6.3f} {g('eta'):>5.1f}")
        print(f"     grad-risk: share of its change landing on the drifted tree {st.mean(r['grad-risk']['drift_share'] for r in rows):.3f}; "
              f"mean weight gap, forward v reverse order {st.mean(r['grad-risk']['order_gap'] for r in rows):.4f} (level-named {st.mean(r['level-named']['order_gap'] for r in rows):.4f})")

    print('\n=== Requirement mix (reviewer finding 3): share of cases reaching the risk rows ===')
    for valid, contradict in ((.20, .25), (.70, .05)):
        share = valid * (1 - contradict)
        print(f'  valid insurance {valid:.0%}, contradicting letter {contradict:.0%}: {share:.1%}, so {share*120:.0f} of 120 validation, {share*100:.0f} of 100 test; ~{share*100*.8:.0f} test approvals at 80%, SE at 6% wrong = {math.sqrt(.06*.94/(share*100*.8)):.3f}')

if __name__ == '__main__':
    main()

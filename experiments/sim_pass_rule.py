#!/usr/bin/env python3
"""How often would each candidate pass rule pass, on a test set of the planned size?

The review asked whether "equal or lower share of labelled-risky approvals than the first guess" is close to a coin flip
when both arms fit their thresholds to the same 5% target. This runs that test many times.

Every rule also needs lower loss than the first guess, which is checked and reported. The rules differ on approvals:
  A  more approvals than the first guess, and risky share among approved no higher (the current rule)
  B  more approvals, with a 95% interval on the difference excluding zero; risky share reported only
  C3, C5, C8  as B, and risky share no more than 3, 5 or 8 points above the first guess's
  D  as B, and the test does not clearly show risky share above the 5% target: the lower end of its 95% Wilson interval is at or below 5%

Scenarios:
  working   trained trees with thresholds fitted to the 5% target. A good rule should pass this
  loose     the same trees with thresholds fitted to a 15% target. A good rule should not pass this
  shuffled  trees trained on shuffled labels, as if training had failed. A good rule should not pass this

Test sizes: 100 is the planned test set in this simplified simulation, where about 80% of trained cases are approved.
54 scales that down to about 43 trained approvals, the number sim_full_table.py gives at a ceiling of 0.85.

No API calls. Standard library only. Run: python3 sim_pass_rule.py
"""
import random, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sim_data_plan as m
m.TAU = 0.30
SEEDS, N_TRAIN, N_VAL, BOOT = 300, 180, 120, 400

def share_interval(a, b, rng):
    """95% bootstrap interval on the paired difference in approval share, a minus b, resampling test cases."""
    n = len(a)
    diffs = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append((sum(a[i] for i in idx) - sum(b[i] for i in idx)) / n)
    diffs.sort()
    return diffs[int(.025 * BOOT)], diffs[int(.975 * BOOT)]

def wilson_low(k, n, z=1.96):
    if n == 0:
        return 0.0
    p = k / n
    den = 1 + z * z / n
    return ((p + z * z / (2 * n)) - z * (p * (1 - p) / n + z * z / (4 * n * n)) ** .5) / den

def risky_share(auto, test):
    k = sum(auto)
    return (sum(c['risky'] for x, c in zip(auto, test) if x) / k) if k else float('nan')

def main():
    tally = {}
    extras = {}
    for s in range(SEEDS):
        rng = random.Random(s)
        train = [m.sample_case(rng) for _ in range(N_TRAIN)]
        val = [m.sample_case(rng) for _ in range(N_VAL)]
        tests = {100: [m.sample_case(rng) for _ in range(100)]}
        tests[54] = tests[100][:54]
        first = {t: m.prior(t) for t in m.TREES}
        trained = {t: m.fit(t, train)[0] for t in m.TREES}
        shuffled = {t: m.fit(t, train, labels=random.Random(s + 999))[0] for t in m.TREES}
        fit = lambda model, target=.05: m.thresholds([(m.case_risk(model, c), c['risky']) for c in val], wrong_target=target)[0]
        tf = fit(first)
        arms = {'working': (trained, fit(trained)), 'loose': (trained, fit(trained, .15)), 'shuffled': (shuffled, fit(shuffled))}
        for n, test in tests.items():
            base = [m.case_risk(first, c) < tf for c in test]
            base_risky = risky_share(base, test)
            base_loss = st.mean(m.logloss(first, t, test) for t in m.TREES)
            for name, (model, tl) in arms.items():
                auto = [m.case_risk(model, c) < tl for c in test]
                r = risky_share(auto, test)
                more = sum(auto) > sum(base)
                lo, _ = share_interval(auto, base, rng)
                loss_ok = st.mean(m.logloss(model, t, test) for t in m.TREES) < base_loss
                no_higher = r == r and base_risky == base_risky and r <= base_risky
                margin = lambda pts: r == r and (base_risky != base_risky or r <= base_risky + pts)
                rules = {'loss lower': loss_ok, 'more approvals': more, 'risky share no higher': no_higher,
                         'A current': loss_ok and more and no_higher,
                         'B interval, risky reported': loss_ok and lo > 0,
                         'C3': loss_ok and lo > 0 and margin(.03), 'C5': loss_ok and lo > 0 and margin(.05), 'C8': loss_ok and lo > 0 and margin(.08),
                         'D target not clearly missed': loss_ok and lo > 0 and wilson_low(sum(c['risky'] for x, c in zip(auto, test) if x), sum(auto)) <= .05}
                for k, v in rules.items():
                    tally.setdefault((n, name, k), []).append(v)
                e = extras.setdefault((n, name), {'auto': [], 'base': [], 'r': [], 'br': []})
                e['auto'].append(sum(auto)); e['base'].append(sum(base))
                if r == r: e['r'].append(r)
                if base_risky == base_risky: e['br'].append(base_risky)
    print(f'{SEEDS} seeds, train {N_TRAIN}, validation {N_VAL}, {BOOT} bootstrap resamples. Share of seeds in which each condition holds. All synthetic.\n')
    names = ['loss lower', 'more approvals', 'risky share no higher', 'A current', 'B interval, risky reported', 'C3', 'C5', 'C8', 'D target not clearly missed']
    for n in (100, 54):
        print(f'=== Test set of {n} cases ===')
        print(f"{'condition':>30} {'working':>9} {'loose':>9} {'shuffled':>9}")
        for k in names:
            print(f"{k:>30} " + ' '.join(f"{st.mean(tally[(n, a, k)]):>9.3f}" for a in ('working', 'loose', 'shuffled')))
        for a in ('working', 'loose', 'shuffled'):
            e = extras[(n, a)]
            print(f"  {a}: approvals {st.mean(e['auto']):.1f} against first guess {st.mean(e['base']):.1f}; risky among approved {st.mean(e['r']):.3f} against first guess {st.mean(e['br']):.3f}")
        print()

if __name__ == '__main__':
    main()

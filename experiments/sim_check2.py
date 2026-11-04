import sys, random, statistics as st
sys.path.insert(0, sys.argv[1])
import sim_data_plan as m
print('=== Share labelled risky by tolerance ===')
rng = random.Random(1)
big = [m.sample_case(rng) for _ in range(20000)]
for tau in (.10, .20, .30, .40):
    print(f'  tau={tau:.2f}: risky share {sum(c["true_risk"] >= tau for c in big) / len(big):.3f}')
m.TAU = 0.30
print('\n=== tau=0.30, train=180: effect of validation size on the 5% wrong-approval target (40 seeds, test=800) ===')
print(f"{'val':>5} {'model':>12} {'auto':>6} {'wrong|auto':>11} {'sd':>6} {'over 10%':>9} {'band':>6} {'high':>6} {'risky|high':>11}")
for n_val in (30, 60, 120, 240):
    for name in ('first guess', 'trained', 'shuffled'):
        rows = []
        for s in range(40):
            rows.append(m.run(s, 180, n_val=n_val)[name])
        wa = [r['wrong_auto'] for r in rows if r['wrong_auto'] == r['wrong_auto']]
        g = lambda k: st.mean(x for x in (r[k] for r in rows) if x == x)
        print(f"{n_val:>5} {name:>12} {g('auto'):>6.3f} {st.mean(wa):>11.3f} {st.pstdev(wa):>6.3f} {sum(x > .10 for x in wa) / len(wa):>9.2f} {g('band'):>6.3f} {g('high'):>6.3f} {g('high_prec'):>11.3f}")
print('\n=== Test-set precision: what 60 test cases can show ===')
import math
for n_auto in (15, 25, 40, 80):
    p = .06
    print(f'  {n_auto} automatic approvals at a true wrong rate of 6%: expected wrong {n_auto * p:.1f}, standard error {math.sqrt(p * (1 - p) / n_auto):.3f}')

# 0003. What counts as passing

*   **Status:** Decided, 2026-11-03
*   **Decided by:** Alejandro Tabares (project owner)
*   **Decision:** The experiment passes on three conditions: lower loss than the first guess and the shuffled control, with intervals excluding zero; more approvals than the first guess, with an interval excluding zero; and it fails on safety only if the test clearly shows risky approvals above 5%, meaning the lower end of the 95% Wilson interval is above 5%. Jev asked directly stays reported only.

## The question

The final test runs once on 100 base cases, and its result is published as a pass or a fail. So the rule has to be set before the test opens, and it has to pass a system that works and fail one that does not, on a test that small.

## The old rule

The experiment passed if, on the sealed test set, both of these held:

*   Trained trees have lower loss than the first guess and the shuffled-label control, with each 95% interval on the difference excluding zero.
*   Trained trees approve a larger share of cases automatically than the first guess, at an equal or lower share of labelled-risky approvals.

## Why it fails

Both arms have `t_low` chosen on validation to aim at the same 5% target, so both should land near the same rate. `sim_check2.py` shows the tie: 5.8% and 5.8%. The second condition then compares two noisy numbers that are meant to be equal, with no interval and no margin.

On a test of this size, one or two cases decide it. In the simulation below the first guess approves about 45 of 100 cases, so one risky case moves its share by about 2 points. On the smaller test it approves about 24, and one case moves it by about 4 points.

The Stage 8 review estimated by hand that this condition would hold about 45% of the time. The simulation measured 58% to 61%. Either way, a system that works as designed could be published as a fail on chance alone.

## What we tested

`sim_pass_rule.py` ran each candidate rule on three simulated systems:

*   **Working:** trained trees, with thresholds fitted to the 5% target. A good rule should pass this.
*   **Too loose:** the same trees, with thresholds fitted to a 15% target. A good rule should not pass this.
*   **Failed training:** trees trained on shuffled labels. A good rule should not pass this.

It used 300 seeds, 180 training and 120 validation cases, and 400 bootstrap resamples. Test sizes were 100 cases, the planned set, and 54 cases, which scales the simulation down to about 43 trained approvals, the number `sim_full_table.py` gives at a ceiling of 0.85.

**How often each condition holds, on 100 cases / 54 cases:**

| Condition or rule | Working | Too loose | Failed training |
| --- | --- | --- | --- |
| Loss lower than the first guess | 100% / 100% | 100% / 100% | 100% / 97.7% |
| More approvals, no interval | 99.7% / 99.0% | 100% / 100% | 9.3% / 8.0% |
| Risky share no higher than the first guess | 58.0% / 61.3% | 5.3% / 9.0% | 48.0% / 53.0% |
| **A.** Old rule: more approvals, risky share no higher | 57.7% / 60.7% | 5.3% / 9.0% | 3.0% / 3.0% |
| **B.** More approvals with an interval, risky share reported only | 96.7% / 94.3% | 99.7% / 99.7% | 4.0% / 2.3% |
| **C3.** As B, and risky share at most 3 points above the first guess | 82.3% / 78.7% | 19.3% / 25.0% | 2.0% / 1.0% |
| **C5.** As B, at most 5 points above | 91.7% / 86.3% | 32.7% / 38.0% | 2.0% / 1.3% |
| **C8.** As B, at most 8 points above | 95.7% / 91.0% | 60.0% / 57.3% | 2.7% / 1.3% |
| **D. As B, and the test does not clearly show risky share above 5%** | **83.0% / 85.0%** | **17.3% / 35.0%** | **2.0% / 1.3%** |

Rules A to D all include the loss condition.

**What each system did on average:**

| System | Approvals, 100 cases | Risky among approved | Approvals, 54 cases | Risky among approved |
| --- | --- | --- | --- | --- |
| First guess | 44.5 | 6.4% | 24.2 | 6.6% |
| Working | 79.0 | 5.6% | 42.6 | 5.7% |
| Too loose | 92.9 | 13.4% | 50.2 | 13.7% |
| Failed training | 22.2 | 7.3% | 12.1 | 7.7% |

Loss against the first guess catches almost nothing here. Shuffled labels beat the first guess on loss in nearly every seed, because a flat distribution loses less than a confident poor guess. The approvals condition is what catches failed training.

## The decision

The experiment passes only if all three hold on the sealed test set, and otherwise it is published as a fail:

*   **Lower loss** than the first guess and the shuffled control, with each 95% interval on the difference excluding zero.
*   **More approvals** than the first guess, with a 95% interval on the difference excluding zero.
*   **No clear safety failure:** it fails only if the lower end of the 95% Wilson interval on the share labelled risky among approvals is above 5%.

Rule D was chosen over the others for these reasons:

*   **B** is what the review preferred, but it passes almost every system with thresholds that are too loose.
*   **C3, C5 and C8** compare with the first guess's rate, which is itself noisy, and the margin has no meaning of its own. C5 passes a working system more often than D on 100 cases, and lets through more systems that are too loose.
*   **D** compares with the target the policy owner actually set, and can be said in one sentence.

Jev asked directly stays reported only, as decision record [0002](0002-compare-the-trees-with-asking-jev-directly.md) explains.

## Trade-offs we accept

*   **A working system still fails about one time in six** (15% to 17%). The result is published as it falls.
*   **Thresholds that are too loose can pass:** 17% of the time on 100 cases and 35% on 54. The rule does not confirm the 5% target, and the test is too small to do so. The report gives the rate with its interval whichever way it goes.
*   **The third condition only catches a clear failure.** By the same Wilson formula, it takes 5 risky approvals in 43, or 6 in 52, for the lower end to pass 5%. These two figures are calculated by hand and are not in the results file.

## Limits of this evidence

*   All of this is synthetic, with a planted truth.
*   The simulation has no letters or requirement checks, so its approvals run higher than the full table's. The 54-case size is the attempt to allow for that. Those 54 cases are the first 54 of the 100, so the two columns are not independent.
*   The simulation checks loss as a plain "lower than the first guess", with no interval and no comparison with the control. The real rule asks for more on loss, which can only lower every pass rate shown.
*   With 300 seeds, each share has a standard error of up to about 3 points.
*   It fits one threshold, `t_low`, and has no officer routes. It does not test the rest of the decision table.

## How to reproduce this

Everything is in `experiments/`, using only the Python standard library. The results were produced with Python 3.9.6, and another version may give different numbers.

```sh
sh experiments/run_all.sh               # reruns every offline experiment and checks it matches
python3 experiments/sim_pass_rule.py    # this comparison alone
```

| Result file | Holds |
| --- | --- |
| `experiments/results/pass_rule.txt` | The tables above |
| `experiments/results/validation_size.txt` | The 5.8% tie |
| `experiments/results/full_table.txt` | About 43 approvals at a ceiling of 0.85 |

# 0001. How an officer's correction updates the trees

*   **Status:** Decided, 2026-11-03
*   **Decided by:** Alejandro Tabares (project owner)
*   **Decision:** One Bayesian network. The officer always gives the outcome. Naming a tree and its right level is optional, and adds stronger evidence on that tree.

## The question

Jev's weights are fixed, so what learns is the leaf weights in the likelihood and severity trees. When an officer says a past decision was wrong, how should that change those weights? Risk is likelihood times severity, summed across hazards, so one wrong outcome could be the fault of any of up to six trees.

## The options we discussed

The project owner first asked about backprop over the weights, then asked for two more experiments: a Bayesian network that works back from the evidence, and Jev naming the tree in place of an officer.

| Option | The officer gives | How weights change |
| --- | --- | --- |
| Backprop, named tree | Tree and right level | A gradient step on that tree only |
| Backprop, outcome only | Risky or not | A gradient through the risk sum into every tree that applied |
| Soft counts, named tree | Tree and right level | The case adds a share to leaf counts, as in training |
| Bayesian, named tree | Tree and right level | The same, with old counts discounted |
| Bayesian, outcome only | Risky or not | The network works back from the outcome to how likely each tree's level was, then adds those shares to leaf counts |
| **Bayesian, outcome + named tree** | Risky or not, and optionally a tree and level | The same network, with the named level fixed as evidence |
| Any of these with Jev naming | Nothing | Jev names the tree and level |

## What we tested

Trees are trained on 180 cases, thresholds are held fixed, and a simulated officer corrects cases the system got wrong. Each method runs in two worlds: a stable one, which is what the demo plans, and one where the truth for one tree shifts up one level. The officer is perfect unless stated. Settings are fixed in advance: a discount of 0.93 for Bayesian methods, and the stated step for backprop. Mean of 20 seeds, 800 test cases per seed.

**After 60 corrections:**

| Method | Stable: loss | Stable: risky among approved | Shift: loss | Shift: risky among approved |
| --- | --- | --- | --- | --- |
| No correction | 0.468 | 6.3% | 0.695 | 12.4% |
| Backprop, named, step 0.1 | 0.471 | 6.4% | 0.654 | 11.8% |
| Backprop, named, step 0.25 | 0.486 | 6.4% | 0.616 | 10.5% |
| Backprop, named, step 0.5 | 0.522 | 6.7% | 0.621 | 9.5% |
| Backprop, named, step 1.5 | 0.572 | 7.2% | 0.612 | 9.2% |
| Soft count, named | 0.475 | 6.3% | 0.609 | 10.3% |
| Bayesian, named only | 0.480 | 6.3% | 0.591 | 9.3% |
| Bayesian, outcome only | 0.474 | 5.4% | 0.636 | 8.6% |
| **Bayesian, outcome + named** | **0.478** | **5.5%** | **0.587** | **7.9%** |
| Same, officer names half the time | 0.476 | 5.4% | 0.603 | 8.3% |
| Same, officer 90% accurate | 0.479 | 5.6% | 0.596 | 8.4% |
| Same, officer 70% accurate | 0.491 | 6.0% | 0.620 | 9.4% |

Loss is the mean over all trees, on the expert labels.

**After 20 corrections, the picture is closer.** After a shift, the combined network has loss 0.642 and 11.1% risky, and backprop at step 1.5 has 0.643 and 9.1%. In a stable world, though, that backprop setting has already raised loss from 0.468 to 0.532, against 0.470 for the combined network.

**What one correction does to one fully reached leaf,** starting from [0.056, 0.858, 0.086] with the last level as the right one:

| Method | New leaf | Expected severity (was 0.435) |
| --- | --- | --- |
| Backprop, step 0.1 | [0.059, 0.840, 0.101] | 0.442 |
| Backprop, step 0.25 | [0.065, 0.809, 0.126] | 0.456 |
| Backprop, step 0.5 | [0.073, 0.746, 0.181] | 0.487 |
| Backprop, step 1.5 | [0.082, 0.378, 0.540] | 0.699 |
| Soft count, on a leaf of 47 cases | [0.055, 0.840, 0.105] | 0.447 |
| **Bayesian with discount 0.93, level named, same leaf** | **[0.055, 0.839, 0.106]** | **0.447** |

The last row is calculated by hand from the same leaf. The others are in `corrections_fixed_step.txt`.

## Could Jev name the tree?

`jev_names_probe.py` called the real Jev (`jev-1.14.0`) on 60 synthetic cases the trained system got wrong, using 93,484 input tokens. It flagged 16% of truly wrong trees, cleared 90% of correct ones, and picked the right level on 10% of the wrong trees.

Replaying those saved answers on one seed, with no new calls:

| 40 corrections after the shift | Loss | Risky among approved |
| --- | --- | --- |
| No correction | 0.679 | 14.6% |
| Bayesian, outcome only | 0.637 | 11.6% |
| Bayesian, outcome + Jev names | 0.640 | 11.8% |
| Bayesian, outcome + Jev's level probabilities on every tree | 0.642 | 11.7% |
| Bayesian, outcome + officer names | 0.589 | 10.6% |
| Backprop 1.5, Jev names | 0.713 | 15.7% |

Jev adds almost nothing over the outcome alone, because it rarely flags a tree and is rarely right when it does. A Bayesian network absorbs that without harm, while backprop gets worse than doing nothing. Simulating Jev at its measured accuracy over 20 seeds agrees: after 60 corrections following a shift, backprop has loss 0.918 and 18.6% risky, against 0.655 and 9.8% for the network.

## Why we changed our minds

The first comparison, in `sim_corrections.py`, favoured backprop with a named tree (loss 0.56, against 0.58 for Bayesian named). We first kept backprop on that result. A reviewer then found two flaws in it:

1.  It chose each method's step size per seed, using data from after the shift, which a real system would not have.
2.  It tested only after a shift, while the demo plans no shift. So in the demo, most "wrong" cases would be label noise that nothing can fix, and a large step would chase that noise.

With settings fixed in advance, no backprop step does well in both worlds. A small step does little after a shift, and a large one damages correct trees when nothing has shifted. A Bayesian update has no step to tune, and it moves less as a leaf gathers cases.

## The decision

Use one Bayesian network: tree levels lead to risk, and risk leads to the outcome.

*   **The officer always gives the outcome.** This alone teaches, at low risk to correct trees.
*   **Naming is optional.** If the officer names a tree and level, that level is fixed as evidence, and the network works out the rest. "Don't know" is a valid answer, not a dead end.
*   **Old counts are discounted** by 0.93 on the leaves a case reached, so new evidence can move a leaf that has seen many cases.
*   **An officer names, not Jev,** until a better-prompted Jev shows it can do this.

## Trade-offs we accept

*   **Slower repair of a shifted tree than a large backprop step.** After 60 corrections, loss on the shifted tree itself is 1.09, against 0.71. Backprop's speed costs damage elsewhere.
*   **One correction moves little,** which is honest but less striking in a demo. The screen must show the counts behind each weight, so the small change makes sense.
*   **The network needs a rule for what "risky" means in terms of risk.** It uses the midpoint between `t_low` and `t_high`, with a soft edge. This couples corrections to thresholds, and it needs rechecking when thresholds are released.

## Limits of this evidence

*   All of this is synthetic, with a planted truth and one kind of shift. It cannot show how real events behave.
*   The simulated officer is perfect unless stated. Real officers may be less accurate, or often answer "don't know", and the rows at 90%, 70% and half the time show how results fall off.
*   Thresholds stay fixed during corrections.
*   The discount of 0.93 is the middle of the three values the first comparison tried (0.85, 0.93 and 0.98). It was fixed before these runs and not tuned in them. No other value has been run with fixed settings, so another could do better or worse.
*   The combined network's lead over named-only is small on loss after a shift (0.587 against 0.591). Most of its lead is in risky approvals: 7.9% against 9.3% after a shift, and 5.5% against 6.3% in a stable world.
*   The Jev replay is one seed, 60 requests and an untuned prompt. Jev never saw an officer's written reason, which might help. Some of its misses come from label noise and an artificial shift that nobody could see in the facts.
*   In a stable world, starting from trained trees, corrections do not visibly improve anything. See decision record [0004](0004-how-the-demo-shows-learning.md).

## How to reproduce this

Everything is in `experiments/`, using only the Python standard library. The results were produced and checked with Python 3.9.6, and another version may give different numbers. `run_all.sh` takes several minutes, and on 2026-11-03 the six offline experiments that existed then matched their saved results exactly.

```sh
sh experiments/run_all.sh                                # reruns every offline experiment and checks it matches
python3 experiments/sim_corrections_combined.py          # the main tables here, and the Jev replay
python3 experiments/sim_corrections_fixed_step.py        # fixed step sizes, and the one-leaf table
python3 experiments/sim_corrections.py --sens 0.164 --spec 0.895 --level 0.104   # the first, flawed comparison
python3 experiments/jev_names_probe.py                   # calls the real Jev; needs JEV_API_KEY; uses tokens
```

| Result file | Holds |
| --- | --- |
| `experiments/results/corrections_combined.txt` | The main tables, and the Jev replay |
| `experiments/results/corrections_fixed_step.txt` | Fixed step sizes, and the one-leaf table |
| `experiments/results/corrections_comparison.txt` | The first comparison, kept to show what changed |
| `experiments/results/jev_names_probe.txt`, `.json` | The real Jev probe, with its raw answers and no key |

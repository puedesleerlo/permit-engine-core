# 0004. How the demo shows learning

*   **Status:** Decided, 2026-11-03
*   **Decided by:** Alejandro Tabares (project owner)
*   **Decision:** The demo is one finished run. An LLM officer, given the expert rubric and always labelled as simulated, rules on cases. Teaching starts from the first guess. Every review teaches, and thresholds are re-chosen every 10 reviews. Cards and plots lead with right risk level, with "Decided without an officer" and precision beside it.
*   **Changed the same night:** the project owner approved corrections-only teaching and "Decided without an officer" as the rising number. Real data broke both, as the next section shows, and the session building the demo changed them while the project owner slept, under their priority of showing results. Nothing else in the decision changed. The project owner has yet to confirm this change.

## What the real data changed

The simulation below used a first guess made poor on purpose and had no requirement rows. Two things changed when the blind first guess and the real reads arrived.

**Decided without an officer does not rise.** About a third of cases can never be automatic, because of failed or missing requirements, red flags and the ceiling. With re-chosen thresholds, the blind first guess already sits near that limit: 61% at the start, and 63% for trees trained on 90 labelled cases.

**Corrections alone made things worse.** `story_variants.py`, on real stored answers, with an officer ruling from labels at 90% accuracy, mean of 5 officer seeds, read on 90 set-aside train cases:

| After 100 reviews | Taught from | Loss (started at 0.748) | Right level (started at 69.6%) | Decided without officer (started at 61.1%) | Precision (started at 94.2%) |
| --- | --- | --- | --- | --- | --- |
| Corrections only | 17 | 0.798 | 72.5% | 56.7% | 93.3% |
| **Every review, discount 0.93** | 100 | **0.458** | **86.4%** | 61.1% | 95.4% |
| Every review, no discount | 100 | 0.470 | 86.2% | 61.3% | 95.8% |
| Refit with EM from officer labels | 100 | 0.468 | 86.2% | 61.3% | 95.8% |

For reference, trees trained with EM on the other 90 labelled cases reach loss 0.449 and right level 83.9%. Teaching only from disagreements shows the system only the cases it got wrong, which skews its counts. Every review is still the same Bayesian network from decision record 0001, with a level named for each tree that applies.

**The real run, with the LLM officer:**

| Reviews | Right level | Loss | Decided without officer | Precision |
| --- | --- | --- | --- | --- |
| 0 | 69.6% | 0.748 | 61.1% | 94.2% |
| 10 | 85.6% | 0.525 | 62.2% | 94.3% |
| 50 | 86.4% | 0.398 | 62.2% | 96.2% |
| 115 | 86.9% | 0.416 | 62.2% | 96.2% |

The officer's outcome matched the label on 95.7% of 117 reviews, and its tree levels on 92.0%. It disagreed with the system 5 times. Most of the gain comes in the first 10 reviews, because the first guess holds only 2 pseudo-cases per leaf, so early evidence moves it quickly. Loss rises slightly after 50 reviews.

The rest of this record is the reasoning from before those results, kept as written.

## The question

Each visitor should see the system improve as an officer corrects cases. What would that plot actually show, what should it start from, and who plays the officer?

The demo is two hours on 2026-11-04, and no person can rule on about half of 120 cases while visitors watch. In `sim_full_table.py`, at a ceiling of 0.85, about 53% of cases go to an officer, or about 38% if the ceiling share meets its 15% target. Those cases would otherwise sit waiting.

## What we tested

`sim_demo_curve.py` has an officer review decided cases one at a time and correct those it believes are wrong, using the Bayesian network from decision record [0001](0001-how-corrections-update-the-trees.md). An officer at accuracy a reaches the right outcome with probability a and names trees with the same accuracy, so an officer below 100% also corrects some decisions that were right. Each row is a mean over 20 seeds, read on 800 held-out cases, unless a smaller seed count is shown: a seed drops out of a row if it runs out of cases before reaching that many corrections.

**Share approved automatically, with thresholds re-chosen on 120 validation cases, and precision in brackets.** Precision is the share of automatic approvals not labelled risky.

| Corrections | Trained trees, officer 100% | First guess, officer 100% | First guess, officer 90% | First guess, officer 70% |
| --- | --- | --- | --- | --- |
| 0 | 80.9% (93.7%) | 46.4% (93.8%) | 46.4% (93.8%) | 46.4% (93.8%) |
| 10 | 81.0% (93.7%) | 69.1% (94.3%) | 64.9% (94.1%) | 52.9% (93.7%) |
| 20 | 81.0% (93.7%) | 77.8% (94.0%) | 71.9% (94.1%) | 61.6% (93.5%) |
| 40 | 81.0% (93.6%) | 80.2% (93.7%) | 76.9% (94.2%) | 69.8% (94.0%) |
| 60 | 80.8% (93.6%) | 80.2% (93.5%), 17 seeds | 77.3% (94.3%) | 69.3% (94.1%) |
| 120 | 84.6% (91.4%), 7 seeds | 80.9% (93.6%), 9 seeds | 77.9% (93.9%), 18 seeds | 69.9% (94.0%), 19 seeds |

**Cases reviewed and loss, from the first guess:**

| Corrections | Officer 100%: reviewed, loss | Officer 90%: reviewed, loss | Officer 70%: reviewed, loss |
| --- | --- | --- | --- |
| 0 | 0, 1.235 | 0, 1.235 | 0, 1.235 |
| 10 | 82, 0.898 | 54, 0.971 | 28, 1.075 |
| 20 | 134, 0.782 | 89, 0.857 | 52, 0.986 |
| 40 | 261, 0.760 | 156, 0.785 | 97, 0.884 |
| 60 | 381, 0.757 | 225, 0.765 | 141, 0.862 |
| 120 | 773, 0.765 | 440, 0.774 | 280, 0.825 |

**From the first guess with thresholds held at their start.** This is why they must be re-chosen:

| Corrections | Officer 100%: approved (precision) | Officer 90%: approved (precision) |
| --- | --- | --- |
| 0 | 46.4% (93.8%) | 46.4% (93.8%) |
| 10 | 28.9% (99.2%) | 22.1% (98.8%) |
| 20 | 29.5% (99.5%) | 23.0% (99.1%) |
| 40 | 34.1% (99.4%) | 24.3% (99.4%) |
| 60 | 38.3% (99.2%) | 24.9% (99.4%) |
| 120 | 46.2% (98.6%) | 27.2% (99.4%) |

## What the results show

*   **Trained trees give a flat line.** Approved stays at 81% and precision near 94% through 60 corrections, while loss rises from 0.468 to 0.478 with a perfect officer and to 0.502 with a 90% officer. The trees have already learned what labels can teach, and most remaining errors are label noise. The 84.6% at 120 corrections is 7 seeds only, and it comes with precision falling to 91.4%.
*   **From the first guess, the line moves.** Approved rises from 46% to 80% after 40 corrections by a perfect officer. A 90% officer reaches 77%, and a 70% officer about 70%.
*   **Precision stays flat near 94%, by design.** Across the first-guess rows with thresholds re-chosen, it stays between 93.5% and 94.3%. Re-chosen thresholds aim at the same 5% target each time, and fall about a point short of it. So the flat line shows that safety did not drop. It does not show that safety improved.
*   **Thresholds must be re-chosen.** Held at their start, approved falls from 46% to 29% after 10 corrections, even though loss is falling, because thresholds fitted to the first guess no longer fit the corrected weights.
*   **Other starts move less or need more.** With a planted change in one tree, and thresholds re-chosen, approved goes from 65.1% to 70.4% after 60 corrections by a perfect officer. Retraining from an officer's labels on every tree reaches 75.9% at 20 cases, but it asks far more of the officer per case, and is not the correction mechanism the design uses.

## The decision

*   **A finished run.** Cases are read, decided and ruled ahead of time. Each visitor's browser replays it, and a video comes from the same replay. Nothing waits for a person during the demo.
*   **An LLM officer with the expert rubric.** An LLM stands in for a person, and is always labelled "Simulated officer: an LLM following the expert rubric". It gets the rubric in words, writes a one-line reason for each ruling, and its measured accuracy is shown. A real deployment would use a person.
*   **Why a rubric.** With none, it would be scored partly on disagreeing with the author's truth table, so its accuracy would mix real errors with a different view of risk. Jev asked directly, with no rubric, got the right level 46% of the time ([0002](0002-compare-the-trees-with-asking-jev-directly.md)). An officer scripted from labels was rejected too, because nothing would read the documents, and any reason it wrote would be invented.
*   **Teaching starts from the first guess,** not from trained weights, and **every review teaches**.
*   **Thresholds are re-chosen every 10 reviews.**
*   **Cards and plots lead with right risk level.** "Decided without an officer" and precision sit beside it, to show that the system learned without losing safety.
*   **Real corrections from the project owner** come from a local file, and are logged as theirs.

## Trade-offs we accept

*   **The replay is not live.** A visitor watches a stored run. The screen says so.
*   **An LLM decides the cases sent to an officer in this demo,** which the design otherwise does not allow. The label and this record say so plainly.
*   **The curve is close to built in.** The rubric is the truth table in words, and the labels come from that table, so the plot shows the mechanism carrying a stated rule into the weights. It finds nothing new.
*   **The replay's weights are not the ones tested.** The final test measures the trained, released weights. The corrected first guess has no test result.

## Limits of this evidence

*   All of this is synthetic, with a planted truth. The 90% and 70% columns show what lower accuracy does, not what the LLM officer will score.
*   **Real numbers will be lower, because the simulation has no requirement rows.** It routes only to automatic, band or high. In `sim_full_table.py` at a ceiling of 0.85, all approvals are about 43% of cases, including 3.8 points approved after a letter, a step the demo no longer has. So 81% and 80% are not what the replay will show.
*   **One real run is noisier than a mean of 20.** The real curve is read on at most 120 validation cases, not 800, so one case moves it by about a point, and it need not rise at every step.
*   **The replay reviews about 120 cases.** Reading between the rows by hand, that means about 17 corrections and about 75% approved with a perfect officer, or about 29 corrections and about 74% with a 90% officer. The 80% needs 261 reviews. The simulation also skips cases inside the review band, so it counts only reviews outside that band, and 120 replay cases contain fewer of those.
*   **The simulation re-chooses thresholds only to read the result.** Its corrections keep using the starting thresholds, both to pick which decisions to review and for the midpoint in the network. The demo feeds re-chosen thresholds into later decisions, which has not been simulated.
*   **The real curve may flatter precision.** The simulation chooses thresholds on 120 validation cases and reads on 800 others. The demo has one validation set for both, unless cases are held apart. Only the sealed test gives an independent rate.
*   The officer's naming accuracy is tied to its outcome accuracy in the simulation, and a real LLM's two may differ.
*   The discount of 0.93 is unchanged from decision record 0001, and was not tuned here.

## How to reproduce this

Everything is in `experiments/`, using only the Python standard library. The results were produced with Python 3.9.6, and another version may give different numbers.

```sh
sh experiments/run_all.sh                # reruns every offline experiment and checks it matches
python3 experiments/sim_demo_curve.py    # this comparison alone
```

| Result file | Holds |
| --- | --- |
| `experiments/results/demo_curve.txt` | Every story at every accuracy, with fixed and re-chosen thresholds |
| `experiments/results/story_variants_real.txt`, `story_variants_simulated.txt` | The four ways of teaching, on real and simulated answers. Run with `uv run python experiments/story_variants.py --answers real`, which needs the stored reads and makes no model calls |
| `experiments/results/full_table.txt` | Route shares at the design's case mix |
| `experiments/results/jev_direct_pilot.txt` | The 46% for Jev asked directly |

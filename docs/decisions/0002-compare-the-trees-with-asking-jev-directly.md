# 0002. Compare the trees with simply asking Jev

*   **Status:** Decided, 2026-11-03
*   **Decided by:** Alejandro Tabares (project owner)
*   **Decision:** The final test includes Jev asked directly for each level, on the same cases and inputs as the trees. A pilot has already run on synthetic facts.

## The question

The design has Jev answer small questions, such as "is the traffic plan adequate?", and the trees combine those answers into a likelihood or severity level. The trees are what trains, so they are the point of the experiment.

There is a simpler system: skip the trees, and ask Jev, "How likely is a traffic conflict at this event: rare, possible or likely?" If that does as well, the trees add nothing. It is the strongest fair challenge to the design, and a skeptical reader would ask about it.

## What the pilot did

`jev_direct_pilot.py` called the real Jev (`jev-1.14.0`) on 240 synthetic cases: 120 to choose thresholds and 120 to compare, using 236,943 input tokens. Jev saw the case facts and plain definitions of the hazards and levels. It did not see the truth table, the system's estimates or an officer's finding.

Jev read true facts in this pilot, so the trees are shown two ways: reading noisy answers, as in the other simulations, and reading the same true facts Jev saw.

| Method | Loss | Right level | Approved automatically | Risky among approved | Review band |
| --- | --- | --- | --- | --- | --- |
| First guess, noisy inputs | 1.267 | 45% | 57% | 10.3% | 42% |
| Trained trees, noisy inputs | 0.460 | 87% | 83% | 13.0% | 3% |
| Trained trees, true inputs | 0.334 | 90% | 83% | 10.1% | 5% |
| Trained trees + crossings question, true inputs | 0.302 | 93% | 83% | 9.1% | 0% |
| **Jev asked directly, true inputs** | **1.385** | **46%** | 73% | 10.3% | 28% |

Against the trees on the same true facts, Jev's per-case loss is 1.05 higher, with a 95% interval of 0.90 to 1.20.

## What this does and does not show

**It does not show Jev is poor at judging risk.** The labels come from a truth table the author wrote, and the trees ask about the same factors that table uses, so trees trained on those labels are close to guaranteed to learn them. Jev has never seen that table. It may be applying a reasonable, different view of what makes a hazard likely or severe. This pilot measures how well each one matches this particular table, which is the point a skeptical reader should press on.

**It does show that training closes the gap on these labels.** Jev asked directly scores about the same as the untrained first guess, though that first guess was made poor on purpose. The trained trees do far better on the same cases.

**It corrects an earlier claim.** An earlier version of the design reported the first probe as if Jev had picked the right level 74% of the time from the facts alone, about as often as the trained trees. That probe also showed Jev the system's own estimates and the officer's finding, on cases selected because the system got them wrong. Without those, on ordinary cases, it is 46%. The two runs use different cases, so the gap between them is not a clean measure of how much the estimates helped, and the probe did not save the estimates, so it cannot be checked directly.

**Risky approvals are not separated by this pilot.** On 120 cases, about 100 approvals or fewer, the differences between 9.1% and 13.0% are within what chance could produce.

## The decision

*   **The final test includes this comparison,** in `evaluation/direct_jev.py`, on the sealed test set: about 100 to 160 Jev requests, depending on whether tone cases are read, and no LLM spending. Another 120 requests on validation cases choose its thresholds, so its approvals can be reported. Those 120 are the first of the comparison work to be cut if time runs short.
*   **It uses the pipeline's real inputs:** the form's typed values, evidence records and whole plan documents, the same as the tree questions read. Unlike the pilot, it reads documents, not true facts.
*   **The result is published whichever way it goes.** If Jev asked directly matches the trees on real documents, the design must say so.
*   **It is reported, not part of the pass rule.** The experiment passes or fails against the first guess and the shuffled-label control. Beating Jev says little while the labels are the author's own.
*   **A stronger test comes when labels stop being the author's own.** Only labels the author did not write, from real outcomes or an independent expert, can show whether the trees or Jev's judgment is closer to real risk. That is listed under Future Improvements.

## How to reproduce this

```sh
python3 experiments/jev_direct_pilot.py --limit 3   # a smoke test: 6 requests
python3 experiments/jev_direct_pilot.py             # the full pilot: calls the real Jev; needs JEV_API_KEY; uses tokens
```

The script uses only the Python standard library, and generates the same synthetic cases from its seed. A new call to Jev may answer differently, so the raw answers are saved.

| Result file | Holds |
| --- | --- |
| `experiments/results/jev_direct_pilot.txt` | The tables above, per-tree results and the interval |
| `experiments/results/jev_direct_pilot.json` | Raw answers, with the facts and labels, and no key |

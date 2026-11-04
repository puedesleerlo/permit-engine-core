# Experiments

Checks made while designing Permit Engine. Everything here is synthetic. The simulations replace the LLM and Jev with noisy answers and make no API calls. `jev_names_probe.py` and `jev_direct_pilot.py` call the real Jev on synthetic cases.

The decisions these support are in `docs/decisions/`: [0001, how corrections update the trees](../docs/decisions/0001-how-corrections-update-the-trees.md), and [0002, comparing the trees with asking Jev directly](../docs/decisions/0002-compare-the-trees-with-asking-jev-directly.md).

## Reproducing

```sh
sh experiments/run_all.sh    # reruns every offline experiment and checks it matches its saved result
```

It takes several minutes, makes no API calls and uses only the Python standard library. The results were produced and checked with Python 3.9.6, and another version may give different numbers. To choose the interpreter, set `PYTHON=/usr/bin/python3`.

The two scripts that call the real Jev are not rerun, because a new call may answer differently and uses tokens. They need `JEV_API_KEY`, and their raw answers are saved, with no key.

## Scripts

| Script | Question | Results |
| --- | --- | --- |
| `sim_data_plan.py` | Can leaf weights and two thresholds learn from labelled cases? Does a missing question show as high entropy? | `results/data_plan.txt`. It uses a risky cut of 0.10, which labels about 58% of cases risky, so its route percentages are not the ones the design quotes |
| `sim_check2.py` | With a risky cut of 0.30, how does validation size affect the 5% target? The design's route table comes from here. Run with this folder's path as its argument | `results/validation_size.txt` |
| `sim_corrections.py` | Which way of correcting weights repairs the tree that is really wrong? **Superseded:** it tuned settings on post-shift data, which favoured backprop. Kept to show what changed | `results/corrections_comparison.txt` |
| `sim_corrections_fixed_step.py` | The same comparison with settings fixed in advance, in a stable world as well as after a shift | `results/corrections_fixed_step.txt` |
| `sim_corrections_combined.py` | Does one Bayesian network that takes the outcome plus an optional named tree do best? Does Jev help as the namer? Part 2 replays the saved real Jev answers, with no new calls | `results/corrections_combined.txt` |
| `sim_full_table.py` | What share of cases reaches each row of the decision table at the design's case mix, and how does the severity ceiling change that? | `results/full_table.txt` |
| `sim_pass_rule.py` | How often would each candidate pass rule pass on a test set of the planned size, for a working system, for thresholds that are too loose, and for failed training? | `results/pass_rule.txt` |
| `sim_demo_curve.py` | What would a plot of the system improving as an officer corrects cases show, starting from trained trees, from a planted change, or from the first guess? | `results/demo_curve.txt` |
| `story_variants.py` | Which way of teaching from an officer reflects learning: corrections only, every review, or refitting? Uses the engine and stored reads, so it is not in `run_all.sh`. Run with `uv run python experiments/story_variants.py --answers real` | `results/story_variants_real.txt`, `results/story_variants_simulated.txt` |
| `jev_names_probe.py` | Can real Jev name the wrong tree and its right level, instead of an officer? | `results/jev_names_probe.txt`, `results/jev_names_probe.json` |
| `jev_direct_pilot.py` | Do the trained trees beat simply asking real Jev for each level? | `results/jev_direct_pilot.txt`, `results/jev_direct_pilot.json` |

## Limits

- The truth table is planted, the world shift is artificial, and thresholds stay fixed during corrections.
- `sim_data_plan.py` routes only to automatic, band or high. It has no requirement check, proof letter or red flag.
- The simulated officer is perfect unless a row says otherwise: it names exactly the wrong trees and their right levels. The rows at 90% and 70% show what lower accuracy does.
- In `sim_corrections.py`, step sizes and discount factors were chosen per seed on data from after the shift. The later scripts fix them in advance, using a discount of 0.93, the middle of the three values that script tried.
- The Jev probe is one seed and 60 requests, with an untuned prompt. It gave Jev the true case facts, the system's estimates and the officer's finding, and never the truth table. The "wrong" set includes 8% label noise and an artificial shift, which no reader of the facts could foresee, so it is a hard test. It did not save the estimates.
- The direct Jev pilot is one seed and 240 requests, with an untuned prompt and true facts rather than documents. Its labels come from the author's truth table, which Jev has never seen, so it measures agreement with that table and not real risk.

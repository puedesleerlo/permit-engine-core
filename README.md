# Permit Engine

An AI system you can trace and audit. It decides street-race permits on synthetic applications, and every decision shows the evidence it read, the risk it calculated and the rule that fired.

- **Site, with results and diagrams:** https://puedesleerlo.github.io/permit-engine/
- **Demo, a replay of one finished run:** https://permit-engine.bottomuplabs.com

## How a decision is made

1. **Basic checks.** Written rules check the fee, the form and the date.
2. **Reading.** An LLM reads the documents in two fixed passes with no tools. Code checks every quote and compares every field with the form.
3. **Tree questions.** Jev, a second model with fixed weights, answers narrow questions as probabilities.
4. **Risk.** Small trees turn those answers into likelihood and severity per hazard. `risk = Σ likelihood × severity`.
5. **Decision.** A decision table in Rego, run through Open Policy Agent, decides or sends the case to an officer. First match wins.
6. **Learning.** Officer reviews update the leaf weights through one Bayesian network. In this project an LLM plays the officer.

## Results

One sealed test on 100 synthetic cases, opened once under a pass rule set in advance. It ran on Claude Opus 5.5 as the LLM and Jev 1.14.0 as the second model. The full table is in [`reports/final.md`](reports/final.md).

| Arm | Right risk level | Approved with no officer | Risky among approved |
| --- | --- | --- | --- |
| Trained trees | 89.4% | 57% | 1 of 57 |
| Untrained first guess | 68.2% | 47% | 0 of 47 |
| Shuffled labels (control) | 54.9% | 25% | 0 of 25 |

The author wrote the answer key, so this shows the method can learn it, not that it predicts real risk.

## Where things are

| Folder | Holds |
| --- | --- |
| `src/permitengine/` | The engine: reading, trees, decisions, learning, evaluation and export |
| `rules/` | The ordinance, hazards, trees, evidence map and Rego policies |
| `settings/` | Every policy value, each with its limits and reason |
| `generator/` | The synthetic data generator and its truth table |
| `experiments/` | Simulations and probes, with saved results |
| `tests/` | The test suite, which uses recorded fixtures and makes no model calls |
| `reports/`, `weights/`, `ledger/` | The sealed test report, released weights and spending ledger |
| `web/`, `export/demo/` | The replay app, and the finished run it plays |
| `architecture/` | The C4 model, in Structurizr DSL |
| `docs/` | The design, decision records and video sources |

The generated data, the stored model answers and the run logs are not in this repository.

## Running it

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). The Rego tests also need the `opa` binary.

```sh
uv sync --extra dev --extra anthropic
uv run pytest
uv run permitengine --help
```

Commands that call a model need the keys named in `.env.example`.

## Changing the LLM vendor

Each vendor is one file in `src/permitengine/models/providers/`, and a test checks that nothing else in the engine names one. To change vendors, add a file there, then set its model and prices in `settings/settings.yaml`. Stored answers are kept per model, so a new model reads the cases again.

# Design documents

| Design | Date | Author | Components | Description |
| --- | --- | --- | --- | --- |
| [Permit Engine: architecture site and working platform](./permit-engine.md) | 2026-11-03 | Alejandro Tabares (puedesleerlo) | Data generator, rule files, tree engine, training, case pipeline, event log, static replay export, replay interface, Structurizr model, architecture site | Event-permit decisions where an LLM checks evidence, Jev answers tree questions, per-hazard risk is summed, and Rego decides. Tree weights and thresholds are trained on labelled synthetic permits |

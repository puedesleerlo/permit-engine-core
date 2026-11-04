# Permit Engine: build brief for the 2026-11-04 demo

The demo is on 2026-11-04 at 10:00 and lasts two hours. The priority is that it works and shows results. Where this brief and `permit-engine.md` disagree, this brief wins for tonight.

## What the demo is

Anyone with the link opens a page in which one finished run of synthetic street-race applications plays from the start at a slow pace, in their own browser. They can open any case and see how it was decided, watch an LLM officer correct cases, and watch the learning plots and cards move as the corrections arrive. The same replay is used for a video.

Nothing runs on the server during the demo. It is a folder of static files behind a Cloudflare tunnel, with no keys.

## Decided by the project owner

*   **Finished run:** cases are read and decided ahead of time. Each visitor's browser replays them.
*   **LLM officer:** an LLM stands in for a person and is always labelled "Simulated officer: an LLM following the expert rubric". It gets the expert rubric in words, writes a one-line reason for each ruling, and its measured accuracy is shown.
*   **Teaching starts from the first guess,** because already-trained trees show a flat line (`experiments/results/demo_curve.txt`).
*   **Every officer review teaches,** not only disagreements. Corrections alone made the blind first guess slightly worse, because they teach only from cases it got wrong (`experiments/results/story_variants_*.txt`, decision record 0004). A review that disagrees is still shown as a correction.
*   **Cards and plots:** "Right risk level" (how often a tree's most likely level is the expert's level) is the number that rises. "Decided without an officer" and precision are shown beside it. Both stay near flat: about a third of cases can never be decided automatically, and thresholds hold precision near its target. Say so plainly.
*   **Letter path is cut.** A missing requirement goes to an officer. There are no reply plans, waiting state or second read.
*   **No proposals screen and no What if.** A `release` command makes weights official.
*   **Admin is not public.** Real corrections from the project owner are entered from a local file.
*   **Pass rule:** lower loss than the first guess and the shuffled control (intervals exclude zero); more approvals than the first guess (interval excludes zero); and fail only if the test clearly shows risky approvals above 5% (the lower end of the 95% Wilson interval is above 5%). Jev asked directly is reported, and is not part of the rule.
*   **Public wording:** say "agentic LLM". Never name the LLM vendor or model in `web/`, `export/`, or public pages. Jev, TypeSafe, Rego, OPA and Structurizr may be named. Everything synthetic, simulated or stored is labelled on screen.

## Priority order

Build so that something can be shown at every point.

1.  Data and rules, with no API calls.
2.  Engine end to end on simulated answers, and the static export.
3.  Web replay on that export. **This is the first showable state.**
4.  Real readers, stopping at 5 cases for the project owner.
5.  Full real read, training, the LLM officer run, the final test, and a new export.
6.  Tunnel. The project owner creates DNS and starts it.
7.  Architecture site on the poster's URL, published only with the project owner's approval.

**Cut for tonight, in this order if time runs short:** tone variants (generated, read only if budget remains); the Jev direct comparison's validation requests; the custom architecture viewer (use a simple stepper or Structurizr's static export); moving `gov_design/site` into this repository (edit it where it is).

**Never cut:** labels kept apart from trees, the sealed test with one look, the shuffled control, the labels saying what is simulated.

## Rules for everyone

*   Work only in your own folders, listed below. Do not edit another agent's folder. If a contract here is wrong, say so in your final report.
*   Do not read, print or copy any `.env` file. `scripts/with_keys.sh` is the only thing that reads keys.
*   **No agent calls the LLM or Jev.** Real calls are made only by the session that owns this brief, after the project owner has seen the 5-case stop. Use fixtures in tests.
*   Do not commit, push, publish, or change anything on Cloudflare.
*   Python 3.12 through `uv run` from the repository root. Dependencies: the LLM SDK, `pyyaml`, `jsonschema`, `pytest`. Ask before adding others.
*   Write plain code with few comments. No speculative options. Reuse the listed code by copying and adapting it.
*   Do not leave long-running servers behind. Do not use ports 8765, 8766 or 5173, which belong to other programs.

## Layout

| Folder | Owner | Holds |
| --- | --- | --- |
| `generator/`, `rules/`, `settings/`, `schemas/`, `tests/test_generator.py`, `tests/test_rules.py` | Data agent | Synthetic data generator, ordinance, evidence map, hazards, trees, Rego, settings |
| `src/permitengine/`, `tests/` (other files), `scripts/` | Engine agent | Trees, risk, training, pipeline, readers, officer, corrections, event log, export, commands |
| `web/` | Web agent | The replay interface. Reads only `web/public/data/` |
| `data/`, `cache/`, `runs/` | Generated | Ignored by git |
| `export/demo/` | Generated by the engine | The JSON the interface plays. `make-export` copies it to `web/public/data/` |
| `weights/`, `reports/`, `ledger/` | Generated, committed later | Released weights, reports, spend meter and test ledger |

## Data contract

**Trees and questions.** Six trees, each with two yes-or-no questions and so four leaves:

| Tree id | Hazard id | Question | Kind | Source |
| --- | --- | --- | --- | --- |
| `traffic.likelihood` | `traffic_conflict` | `escort_confirmed` | evidence | `police_escort_letter` or `police_escort_email` |
| | | `traffic_plan_adequate` | jev | whole traffic plan, route |
| `traffic.severity` | `traffic_conflict` | `arterial_road` | rule | form |
| | | `crowd_over_800` | rule | runners + extracted spectators |
| `crowd.likelihood` | `crowd_pressure` | `crowd_plan_adequate` | jev | whole crowd plan |
| | | `crowd_over_800` | rule | |
| `crowd.severity` | `crowd_pressure` | `narrow_venue` | jev | whole race plan |
| | | `crowd_over_800` | rule | |
| `medical.likelihood` | `medical_emergency` | `medical_plan_adequate` | jev | whole medical plan |
| | | `hot_date` | rule | June, July or August |
| `medical.severity` | `medical_emergency` | `ambulance_on_site` | evidence | `ambulance_agreement` |
| | | `hospital_far` | rule | `hospital_distance_km` over 10 |

**Hazards apply** by rules only: traffic when the road closes, crowd when crowd is 300 or more, medical always. Crowd means runners plus expected spectators.

**Planted gap.** The truth table raises traffic likelihood with many major crossings (3 or more), which the first traffic tree does not ask. `rules/proposals/traffic.likelihood.crossings.yaml` adds `many_major_crossings`, a `rule` question from the form, giving eight leaves.

**Tree file format** (`rules/trees/<tree id>.yaml`):

```yaml
id: traffic.likelihood
version: 1
owner: policy_owner
hazard: traffic_conflict
scale: likelihood            # or severity
questions:
  - id: escort_confirmed
    kind: evidence           # evidence | rule | jev
    evidence_types: [police_escort_letter, police_escort_email]
    clause: ORD-12.4
  - id: traffic_plan_adequate
    kind: jev
    instructions: Does the traffic plan cover every road closure on the route?
    needs: [route, traffic_plan]
    clause: ORD-12.2
leaves:                      # every combination of the questions, in order; true first
  - when: { escort_confirmed: true, traffic_plan_adequate: true }
    levels: [0.8, 0.1, 0.1]  # rare, possible, likely; or minor, serious, critical
```

A `rule` question's `id` is the name of a Rego rule in `data.permit.questions`.

**Anchors.** Likelihood rare 0.02, possible 0.10, likely 0.30. Severity minor 0.1, serious 0.4, critical 1.0. `risk = sum over applicable hazards of (likelihood x severity)`, each the sum of level probability times anchor.

**`data/cards.jsonl`**, hidden facts, one case per line:

```json
{"case_id":"R0001-plain","base_id":"R0001","split":"train","tone":"plain","families":{"race_plan":"a"},
 "facts":{"runners":400,"spectators_mentioned":0,"crowd":400,"road_closure":true,"arterial_road":false,"major_crossings":1,"many_major_crossings":false,
          "event_date":"2027-06-12","hot_date":true,"narrow_venue":false,"hospital_distance_km":3,"hospital_far":false,"fee_paid":true,"form_complete":true,"date_allowed":true,
          "escort_arranged":true,"escort_evidence":"letter","ambulance_arranged":true,"ambulance_evidence":"letter",
          "traffic_plan_adequate":true,"crowd_plan_adequate":true,"medical_plan_adequate":true,"insurance":"valid"}}
```

`escort_evidence` is `letter`, `email`, `none` or `contradicting`. `ambulance_evidence` is `letter` or `none`. `insurance` is `valid`, `expired`, `wrong_venue`, `broker_letter` or `missing`.

**`data/applications/<case_id>/`:** `form.json`, `cover_letter.txt`, and `attachments/<name>.txt`. `form.json` holds organizer, event_type, event_date, expected_runners, description, route (road_closure, arterial_road, major_crossings), hospital_distance_km, fee_paid, attachments (names). No label words appear in any document.

**`data/labels.jsonl`:**

```json
{"case_id":"R0001-plain","applies":{"traffic_conflict":true,"crowd_pressure":true,"medical_emergency":true},
 "levels":{"traffic.likelihood":1,"traffic.severity":0,"crowd.likelihood":0,"crowd.severity":0,"medical.likelihood":1,"medical.severity":1},
 "requirements":{"event_insurance":"met"},"allowed":true,"risk":0.07,"risky":false,"right_route":"approve"}
```

Levels are 0, 1 or 2, and `null` for a tree whose hazard does not apply. `right_route` is `returned`, `denial`, `officer` or `approve`.

**`data/splits.json`:** `{"train":[case ids],"validation":[...],"test":[...],"tone":[...]}`. `data/manifest.json`: seed, generator version, dataset hash.

**Sizes:** 180 train, 120 validation, 100 test, and 60 tone cases (20 test requests in 3 more tones), with the mix in `permit-engine.md` under "The case mix", minus "Reply to a letter". Some written variant families appear only in test.

**Targets the balance report must show as met,** or say which was missed: about 20% labelled risky; at most about 15% at the severity ceiling of 0.85; at least about 50 approvals expected in the test set; at least 15 training cases per leaf of every tree, including the crossings tree. Raise the road-closure share or stratify the draw if the crossings tree needs it.

## Decision table

First match wins. Implemented in Rego (`rules/rego/decision.rego`, `data.permit.decision`), as a pure function of its input.

| Row | If | Route | Reason code |
| --- | --- | --- | --- |
| 0 | Basic check failed: fee, form or date | `returned` for an incomplete form; otherwise `proposed_denial` | `form_returned`, `basic_rule_failed` |
| 1 | Evidence contradicted; requirement unclear; unmapped documents; model failed; policy failed; stop switch on; highest severity at or above the ceiling | `officer` | `red_flag`, `requirement_unclear`, `unmapped_evidence`, `model_failure`, `policy_unavailable`, `stop_switch`, `severity_ceiling` |
| 2 | A requirement failed | `proposed_denial` | `requirement_failed` |
| 3 | A requirement is missing | `officer` | `requirement_missing` |
| 4 | Risk under `t_low` | `approved` | `approved` |
| 5 | Risk at or over `t_high` | `officer` | `high_risk` |
| 6 | Anything else | `officer` | `review_band` |

**Requirement status:** `met`, `failed`, `missing`, `unclear`, as in `permit-engine.md`.

**Rego contract.** Run with `opa eval` and `rules/rego/capabilities.json`. The data agent writes the policies, `opa test` tests, and these exact inputs and outputs. The engine agent calls them.

| Query | Input | Output |
| --- | --- | --- |
| `data.permit.basic.result` | `{"form":{...},"fee_paid":true}`, using the fields of `form.json` | `{"form_complete":bool,"fee_paid":bool,"date_allowed":bool,"failed":[check ids],"clauses":{check id: clause}}` |
| `data.permit.questions.answers` | `{"form":{...},"extracted":{"expected_spectators":int or null}}` | `{question id: bool}` for every `rule` question, including `many_major_crossings` |
| `data.permit.screen.applies` | The same | `{hazard id: bool}` |
| `data.permit.requirements.status` | `{"records":{evidence type: {"status":"found or absent","verdict":"supported, unsupported or contradicted, or null","field_failed":bool,"field_mismatch":bool}}}` | `{requirement id: {"status":"met, failed, missing or unclear","clause":str,"evidence_type":str}}` |
| `data.permit.decision.result` | `{"basic":{...},"requirements":{id: status},"evidence_contradicted":bool,"unmapped_documents":int,"model_failure":bool,"policy_failure":bool,"stop_switch":bool,"highest_severity":num,"ceiling":num,"risk":num,"t_low":num,"t_high":num}` | `{"row":int,"route":str,"reason_code":str,"clauses":[str],"text":str}` |

`text` is one plain sentence a visitor can read. `route` is `returned`, `proposed_denial`, `officer` or `approved`.

**Who writes what in `rules/`.** The data agent writes everything except the first-guess `leaves` and `rules/prompts/`. Tree files start with `leaves: []`. A fresh agent with no project history then writes the first guess from the ordinance, hazards and question lists alone. The engine agent owns `rules/prompts/`. The expert rubric, `generator/expert_rubric.md`, is the truth table in plain words, written by the data agent. Only the LLM officer reads it.

## Export contract

The engine writes this. The interface reads only this, from `data/` next to the page. All files are static JSON. No file names the LLM vendor or model, and no file contains a key.

**`manifest.json`**

```json
{"run_id":"demo-1","created_at":"2026-11-04T01:00:00-05:00","source":"simulated","synthetic":true,
 "officer_label":"Simulated officer: an LLM following the expert rubric","jev_model":"jev-1.14.0",
 "case_count":120,"event_count":900,"officer_accuracy":0.91,"notes":["All applications are synthetic."]}
```

`source` is `simulated` until real answers replace simulated ones, and `real` after. The interface shows it.

**`events.json`:** the replay, in order. The interface plays it.

```json
[{"seq":1,"sim_time":"2027-01-04T09:00:00","case_id":"R0123-plain","type":"case.submitted","actor":"script","simulated":true,"summary":"Riverside Runners applied for a 5K with 400 runners."}]
```

Types: `case.submitted`, `checks.done`, `evidence.linked`, `evidence.judged`, `requirements.checked`, `hazards.screened`, `trees.evaluated`, `risk.computed`, `decision.made`, `officer.ruled`, `correction.made`, `weights.updated`, `thresholds.rechosen`, `permit.issued`, `change.released`. A `correction.made` or `thresholds.rechosen` event also has `"learning_index"`, the index into `learning.curve` that is now current. In `learning.curve`, `corrections` counts every officer review that taught so far, and `correction.bucket` in a case file is `ai_wrong` or `confirmed`. A case's `correction` is present whenever its review moved weights.

**`cases.json`:** one row per case, in replay order.

```json
[{"case_id":"R0123-plain","title":"Riverside Runners 5K","first_seq":1,"decided_seq":9,"route":"approved","reason_code":"approved","row":4,"risk":0.06,"t_low":0.08,"t_high":0.25,
  "weights_version":"first-guess+3","officer":false,"corrected":false,"label_risky":false,"agreed_with_label":true}]
```

**`cases/<case_id>.json`:** everything about one case.

```json
{"case_id":"R0123-plain","title":"...","documents":{"form":{},"cover_letter":"...","attachments":[{"name":"...","text":"..."}]},
 "checks":[{"id":"fee_paid","passed":true,"clause":"ORD-3.1"}],
 "evidence":[{"evidence_type":"certificate_of_insurance","status":"found","document":"insurance.txt","fields":[{"name":"venue","value":"...","quote":"...","verified":true,"matches_form":true}],"verdict":"supported","reason":null,"source":"stored"}],
 "unmapped_documents":[{"document":"...","why":"..."}],
 "requirements":[{"id":"event_insurance","status":"met","clause":"ORD-7.1","evidence_type":"certificate_of_insurance"}],
 "hazards":[{"id":"traffic_conflict","name":"Traffic conflict","applies":true,"why":"The road closes.",
   "likelihood":{"tree_id":"traffic.likelihood","value":0.217,"entropy":0.71,"levels":[0.2,0.6,0.2],"level_names":["rare","possible","likely"],
     "questions":[{"id":"escort_confirmed","kind":"evidence","text":"Is the police escort confirmed?","answer":0.1,"clause":"ORD-12.4"}],
     "leaves":[{"when":{"escort_confirmed":true,"traffic_plan_adequate":true},"reach":0.08,"levels":[0.7,0.2,0.1],"count":12.4,"entropy":0.8,"contribution":0.01}]},
   "severity":{"same shape":true},"product":0.061}],
 "risk":0.102,"highest_severity":0.4,"t_low":0.08,"t_high":0.25,"ceiling":0.85,
 "decision":{"row":6,"route":"officer","reason_code":"review_band","clauses":["ORD-12.4"],"text":"Risk is inside the review band, so an officer decides."},
 "officer":{"label":"Simulated officer: an LLM following the expert rubric","ruling":"approve","outcome_risky":false,"reason":"...","named":[{"tree_id":"traffic.likelihood","level":0}],"agrees_with_label":true},
 "correction":{"bucket":"ai_wrong","outcome_risky":true,"named":[],"changes":[{"tree_id":"traffic.likelihood","leaf":{},"before":[0.1,0.8,0.1],"after":[0.09,0.75,0.16],"count_before":4.2,"count_after":4.9}]},
 "manifest":{"weights_version":"first-guess+3","thresholds":"...","rules_hash":"...","source":"stored"},
 "events":[1,2,3]}
```

`officer` and `correction` are `null` when absent. `hazards[].likelihood` and `severity` are `null` when the hazard does not apply.

**`learning.json`**

```json
{"curve":[{"index":0,"corrections":0,"seq":1,"right_level":0.68,"decided_without_officer":0.62,"precision":0.92,"loss":0.78,"t_low":0.20,"t_high":0.22,"held_out_cases":90}],
 "cards":{"first":{"right_level":0.68,"decided_without_officer":0.62,"precision":0.92},"final":{"right_level":0.84,"decided_without_officer":0.62,"precision":0.94}},
 "arms":[{"name":"First guess","loss":1.2,"approved":0.46,"risky_among_approved":0.06,"interval":[0.02,0.14]},{"name":"Trained on labelled cases"},{"name":"Shuffled labels (control)"},{"name":"One LLM reads and decides (baseline)"},{"name":"Jev asked directly"}],
 "final_test":{"status":"not_run","verdict":null,"conditions":[{"name":"...","passed":null,"detail":"..."}],"forbidden_permits":null,"risky_approvals":null},
 "trees":[{"tree_id":"traffic.likelihood","mean_leaf_entropy":0.69,"flagged":true,"loss":0.8,"leaves":[{"when":{},"count":12.4,"entropy":0.8,"levels_first":[0.8,0.1,0.1],"levels_now":[0.5,0.3,0.2]}]}],
 "crossings":{"status":"released","loss_before":0.8,"loss_after":0.58,"text":"..."},
 "corrections":[{"case_id":"...","seq":44,"bucket":"ai_wrong","outcome_risky":true,"reason":"...","tree_ids":["traffic.likelihood"]}],
 "officer":{"reviewed":117,"corrections":12,"accuracy":0.91,"level_accuracy":0.90,"label":"Simulated officer: an LLM following the expert rubric"}}
```

**`rules.json`:** read-only display. `{"ordinance":[{"id","text"}],"evidence_types":[...],"requirements":[...],"does_not_count":[...],"settings":[{"key","value","limits","owner","why","if_raised"}],"hazards":[...]}`.

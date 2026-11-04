# Permit Engine: explainer video transcripts

Two narrated explainers, each heard once at a confident pace, and each under 2 minutes. Numbers come from the finished run: `export/demo/`, `reports/final.json`, `reports/tone.json` and `experiments/results/story_variants_real.txt`. The worked example is case `R0229-plain`, which is synthetic like every case.

Spoken decimals are written as words for the voice. Digits stay on screen.

## Video 1: What it is and why it matters

The same diagram runs through this video: four boxes in a row, each a question.

1.  **What supports it?** The agentic LLM reads and quotes, and code checks.
2.  **What could go wrong?** Small risk trees.
3.  **What do the rules say?** Written rules.
4.  **Does it need a person?** An officer.

| # | Narration | What the viewer sees |
| --- | --- | --- |
| 1.1 | A city office gets a request to hold a street race. One AI model could answer yes or no. But when it's wrong, there's nothing to check or fix. | An application goes into a single sealed box. "Approved?" comes out. A question mark sits over the box. |
| 1.2 | Permit Engine splits that decision into parts you can inspect. It's automatic and AI assisted, yet every step leaves a trace. | The box opens into the four question boxes. As each lights up, a line is added to a log that grows beneath them. |
| 1.3 | First, evidence. The AI must quote its source. This police letter promises an escort, but for the wrong date. A separate check compares the dates, and rejects the letter. | Box 1 lights up. A police letter with one sentence highlighted, labelled "agentic LLM". A tick on "the quote is in the document". Then the form's date and the letter's date side by side, labelled "code check", a cross on "the date matches", and the stamp "contradicted". |
| 1.4 | Second, escalation. Small question trees score risk. A contradiction, missing insurance, or a risk that isn't clearly low goes to an officer, with the reason attached. | Boxes 2, 3 and 4 light up. Three labelled paths lead to an officer's desk. A separate path, low risk with clean evidence, goes straight to "approved". |
| 1.5 | Third, learning. Officer reviews adjust the numbers inside those trees. The written rules never change by themselves. | An arrow returns from box 4 to box 2. A small tree appears with labelled bars, and the branches this case reached shift. A padlock sits over box 3. |
| 1.6 | In this demo, an AI plays the officer. On cases set aside, the trees matched our answer key 70 percent of the time at first, and 87 percent after 115 reviews. | Label: "Simulated officer: an LLM following the expert rubric". A line rises from 70% to 87%, flattening early. Caption: "Right risk level on 90 set-aside cases. The officer's rubric is the source of the answer key." |
| 1.7 | This pattern isn't only for races. In a bank, income papers are the evidence, fraud and default are the risks, and a mismatch goes to an analyst. | The four boxes, relabelled for a loan file. Caption: "Same pattern. Not built or tested here." |
| 1.8 | In government benefits, the law supplies the rules, and a caseworker takes the hard cases. | The four boxes, relabelled for a benefit claim. Same caption. |
| 1.9 | And when an AI agent is about to move money or delete data, treat that action as an application. What supports it? What could go wrong? Does it need a person? | The four boxes, with an agent's action as the application. Boxes 1, 2 and 4 light up as their questions are spoken. Same caption. |
| 1.10 | We've only tested on made-up permits, so it shows the method can learn, not that it predicts real risk. Automatic where it can be, traceable every time, and a person for the hard cases. | "Synthetic data. Answer key written by the author." Then the four boxes together, with the three closing phrases appearing. |

## Video 2: Inside one decision, and how we tested it

A scoreboard stays on one side of the screen from 2.3 onward and fills in as the numbers are reached:

```
traffic   L ___ × S ___ = ___
crowd     (same steps) = ___
medical   (same steps) = ___
total risk ___   approval line 0.185
```

"Figures rounded." shows on the scoreboard from 2.6 onward.

| # | Narration | What the viewer sees |
| --- | --- | --- |
| 2.1 | Let's follow one made-up application: a race with 900 runners and a closed road. | The application form, with those two facts highlighted. |
| 2.2 | Written rules pick three hazards: traffic, crowd pressure, medical. | Three hazard cards appear one at a time, each with its rule beside it: "a road closes", "crowd of 300 or more", "every race". |
| 2.3 | Each hazard gets two small question trees: how likely, and how bad. Take one: how likely is a traffic conflict? | Six small trees, two per hazard, labelled "likelihood" and "severity (how bad)". All fade except traffic likelihood, which grows. The empty scoreboard appears. |
| 2.4 | First: is the police escort confirmed? The letter names the wrong date, so a fixed low value applies: point zero five. | The first question lights up. The letter's wrong date, stamped "contradicted". The bar sets to 0.05, labelled "yes 0.05, no 0.95. Fixed value, set by a code check. No AI." |
| 2.5 | Second: is the traffic plan adequate? An AI model, Jev, reads the whole plan and returns one probability: point nine six. | The plan's text slides past. A label reads "Jev: AI model. Slowed down to show the idea. Answer stored ahead of time." The probability climbs in even steps across this scene, and settles at 0.96. |
| 2.6 | So the case splits, like water through pipes. 91 percent reaches one leaf: no confirmed escort, but a good plan. | The tree draws, with "leaf" labelled. Flows run down the branches, in proportion. On the thick one: 0.95 × 0.96 = 0.91. |
| 2.7 | Each leaf holds a mix of three levels: rare, possible, likely. Blended by flow, that's 12, 60 and 28 percent. | Each leaf shows a numbered bar and its flow. The bars blend into one: 12% rare, 60% possible, 28% likely. |
| 2.8 | Each level stands for a fixed number. Multiply each share by its number, and add. That's the likelihood. | rare = 0.02, possible = 0.10, likely = 0.30 appear under the bar. Then L = 0.120 × 0.02 + 0.598 × 0.10 + 0.282 × 0.30 = 0.147, one term at a time, each joined to its bar segment. The scoreboard fills L for traffic. |
| 2.9 | Severity works the same way. Multiply the two for this hazard's risk. | S = 0.40 appears. Then 0.147 × 0.40 = 0.0588. The scoreboard fills the traffic row. |
| 2.10 | Add all three hazards, and total risk falls below the approval line. | The crowd and medical rows fill: 0.0506 and 0.0419. Risk = 0.0588 + 0.0506 + 0.0419 = 0.151, on a meter with the approval line at 0.185. |
| 2.11 | So, approved? No. Rules outrank arithmetic: the wrong-date letter sends it to an officer. | The meter dims. A rule card, "A document disagrees with the application", sends the case to the officer. |
| 2.12 | Our simulated officer calls it risky, so this leaf moves: from 27 percent likely to 35. That's the learning. | Label: "Simulated officer: an LLM following the expert rubric". "Below the line, but the officer disagrees." The leaf's bar moves from 27% to 35% likely, with a direction arrow. Caption: "Smaller shifts in the other leaves." |
| 2.13 | We ran three tests. First, does training help? On a sealed test, trained trees matched our answer key 89 percent of the time. Untrained, 68. Trained on shuffled answers, 55. | Three bars: "Trained on labelled cases 89%", "Untrained first guess 68%", "Trained on shuffled answers (control) 55%". A seal reads "Fixed in advance. Run once." Caption: "100 sealed cases. Scored: top-share level, not the final decision." |
| 2.14 | Second: learning only from disagreements made its probabilities worse. Learning from agreements too made them much better. | Two labelled lines. "Disagreements only" rises from 0.75 to 0.80. "Every review" falls from 0.75 to 0.46, tagged "what we use". Axis: "Loss, lower is better". Caption: "Side experiment: 100 reviews, officer scripted from labels at 90% accuracy." |
| 2.15 | Third, does a pushy cover letter help? In 60 comparisons, no decision changed. All made-up data, so this shows the method can learn, not that it predicts real risk. | Three cover letters in different tones lead to one decision. Caption: "Evidence readings shifted in 11 of 60, close to the 3 of 20 from re-reading the same letters." Then "Synthetic data. Answer key written by the author." |

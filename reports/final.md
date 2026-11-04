# Final test report

All applications are synthetic.

**Verdict: pass.** Weights version `v1`, on answers marked `real`.

## The pass rule

| Condition | Passed | Detail |
| --- | --- | --- |
| Lower loss than the first guess | yes | Difference in mean loss -0.390, 95% interval -0.436 to -0.345. |
| Lower loss than the shuffled control | yes | Difference in mean loss -0.510, 95% interval -0.578 to -0.440. |
| More approvals than the first guess | yes | Difference in share approved +0.100, 95% interval +0.040 to +0.170. |
| Risky approvals not clearly above 5% | yes | 1 of 57 approvals labelled risky, Wilson interval 0.003 to 0.093. This fails only if the lower end is above 5%. |

## Arms

| Arm | Loss | Right level | Approved | Risky among approved | Wilson interval |
| --- | --- | --- | --- | --- | --- |
| First guess | 0.766 | 68.2% | 47.0% | 0.0% | 0.0% to 7.6% |
| Trained on labelled cases | 0.372 | 89.4% | 57.0% | 1.8% | 0.3% to 9.3% |
| Shuffled labels (control) | 0.909 | 54.9% | 25.0% | 0.0% | 0.0% to 13.3% |
| One LLM reads and decides (baseline) | n/a | n/a | 11.0% | 0.0% | 0.0% to 25.9% |
| Jev asked directly | 1.468 | 30.9% | 42.7% | 0.0% | 0.0% to 8.6% |

Forbidden permits: 0. Risky approvals: 1 of 57 approvals.

## What this test cannot show

About 3 risky approvals in 52 gives a Wilson interval of roughly 2% to 16%, so this test cannot confirm a 5% target. It can only show when risky approvals are clearly above it.

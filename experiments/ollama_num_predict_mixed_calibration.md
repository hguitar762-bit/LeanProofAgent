# qwen3:8b mixed-difficulty `num_predict` calibration

## Question

Does `num_predict=4096` reduce local Ollama latency without breaking proof
generation on problems that qwen3:8b has previously verified?

## Controlled setup

- Model/backend: `qwen3:8b` through local Ollama 0.34.4.
- Conditions: Ollama default versus `num_predict=4096`.
- Fixed: prompts, benchmark, ProofAgent, Lean verifier, Mathlib environment,
  temperature, context length, evaluation logic, three formalization attempts,
  three proof attempts, two equivalence attempts per direction, and a
  120-second Lean timeout.
- Git commit: `96a0a53e1ef4e40de9f245130d976abe2038f5e8`.
- Benchmark SHA-256:
  `7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7`.

The seven-problem calibration set was:

| Difficulty | Problems |
| --- | --- |
| Historically verified / easy | `arith_add_zero`, `logic_implication_trans` |
| Medium | `algebra_square_sum`, `func_injective_comp` |
| Current hard subset | `algebra_mul_inv_cancel`, `ineq_square_nonnegative`, `sets_preimage_inter` |

The two historically verified problems were then repeated once per condition.
Repeat results are reported separately and are not mixed into the primary
seven-problem rates.

## Validity note

Initial runs under long experiment directory names produced Windows paths above
260 characters. Lean then returned `no such file or directory (error code:
4058)` for files that existed. Those runs were discarded as invalid. The valid
runs used `experiments/c/d`, `experiments/c/k`, `experiments/c/de`, and
`experiments/c/ke`; generated Lean paths stayed below the Windows limit. No
verifier or experiment logic was changed.

## Primary seven-problem results

Rates for output-shape diagnostics use completed generations. Token-limit rate
uses issued requests, including empty responses with `done_reason=length`.

| Metric | Default | `num_predict=4096` |
| --- | ---: | ---: |
| First-pass formalization | 4/7 (57.1%) | 2/7 (28.6%) |
| Final formalization | 5/7 (71.4%) | 5/7 (71.4%) |
| Average formalization attempts | 1.71 | 1.86 |
| First-pass proof | 1/7 (14.3%) | 2/7 (28.6%) |
| Final verified proof | 2/7 (28.6%) | 3/7 (42.9%) |
| Proof repair gain | +1 (+14.3 pp) | +1 (+14.3 pp) |
| Average proof attempts | 1.71 | 0.71* |
| Malformed output | 5/39 (12.8%) | 2/24 (8.3%) |
| Token-limit termination | 0/40 (0%) | 6/29 (20.7%) |
| Code-fence output | 4/39 (10.3%) | 0/24 (0%) |
| Explanatory-text output | 5/39 (12.8%) | 0/24 (0%) |
| Lean/API hallucination | 12/39 (30.8%) | 8/24 (33.3%) |
| Median generation latency | 27.95 s | 16.81 s |
| Maximum generation latency | 277.44 s | 78.48 s |
| Sum of completed generation latency | 1,500.64 s | 612.42 s |
| Total pipeline latency | 2,917.72 s | 1,490.75 s |
| Median completed output length | 1,648 tokens | 1,000 tokens |
| Recorded output tokens | 87,215 | 34,578** |
| Recorded input/output/total tokens | 11,952 / 87,215 / 99,167 | 5,499 / 34,578 / 40,077** |
| Semantic equivalent / unknown | 1 / 6 | 1 / 6 |

`*` The lower average is not purely an efficiency gain: token-cap backend
failures prevented later attempts on several problems.

`**` Lower bound. Five empty cap-ended requests reported no token usage, and
their early termination also prevented downstream generations.

Operational definitions follow the prior stability report: malformed means an
artifact rejected by existing safety/format checks; hallucination means Lean
reported an unknown identifier, constant, field, or tactic. These labels are
not semantic-correctness judgments.

## Per-problem changes

| Problem | Difficulty | Default | 4096 | Change |
| --- | --- | --- | --- | --- |
| `arith_add_zero` | easy | not verified; 3 proof attempts | not verified; proof call cap-ended before a persisted attempt | no score change, but 4096 removed the repair opportunity |
| `logic_implication_trans` | easy | not verified; 3 attempts | verified on first proof | 4096 gained one verified problem |
| `algebra_square_sum` | medium | verified on first proof | verified on first proof | unchanged success |
| `func_injective_comp` | medium | formalization failed after 3 attempts | formalization failed; third call cap-ended | unchanged score, reduced repair coverage |
| `algebra_mul_inv_cancel` | hard | formalization failed | formalization failed | unchanged |
| `ineq_square_nonnegative` | hard | verified after proof repair | verified after proof repair | unchanged success |
| `sets_preimage_inter` | hard | not verified after 3 proof attempts | not verified; second proof call cap-ended | unchanged score, reduced repair coverage |

The 4096 main run therefore improved the observed verified rate from 28.6% to
42.9%, while preserving both default successes. It nevertheless truncated an
easy proof request and two other problem-stage requests. Additional cap events
occurred during equivalence checking after proof status was already fixed.

## Easy-problem repeat

| Metric | Default | `num_predict=4096` |
| --- | ---: | ---: |
| Problems | 2 | 2 |
| First/final formalization | 2/2 / 2/2 | 2/2 / 2/2 |
| First-pass proof | 0/2 | 0/2 |
| Final verified proof | 2/2 (100%) | 0/2 (0%) |
| Proof repair gain | +2 | 0 |
| Total latency | 607.81 s | 609.95 s |
| Recorded output tokens | 21,898 | 16,748** |
| Recorded total tokens | 25,265 | 18,918** |
| Token-limit termination | 0/12 | 3/11 (27.3%) |

In the repeat, default repaired both `arith_add_zero` and
`logic_implication_trans` to verified proofs. With 4096, `arith_add_zero`
completed one failed proof attempt and then its repair call ended at the token
limit; `logic_implication_trans` used all three proof attempts but did not
verify. Thus the simple-set regression is not attributable entirely to
truncation, but the arithmetic regression includes direct proof truncation.

## Latency and token effect

On the primary set, 4096 reduced total pipeline latency by 48.9%, completed
generation time by 59.2%, median generation latency by 39.9%, and maximum
generation latency by 71.7%. Recorded output tokens fell 60.4%, but this is a
lower bound rather than an exact efficiency comparison.

Across the primary run plus easy repeat, total latency fell from 3,525.53 to
2,100.70 seconds (40.4%). On the easy repeat alone, however, 4096 was 0.4%
slower because failed proofs consumed more downstream attempts. Shorter output
therefore does not guarantee lower end-to-end latency.

## Decision

Keep Ollama default for the next 15--20-problem benchmark. Although 4096 was
faster and scored one additional success in the primary run, the controlled
easy repeat changed from 2/2 verified under default to 0/2 under 4096, with a
direct token-limit termination during `arith_add_zero` proof repair. This meets
the predeclared condition for rejecting the explicit cap.

The project limitation should be recorded explicitly: default preserves proof
completion but has high-variance long outputs, including a 277-second completed
generation and one 600-second Ollama HTTP timeout in the primary run. A larger
benchmark can proceed with default as the fixed configuration, but its runtime
budget must account for this long tail.

## Verification

- `lake build`: passed (`8925 jobs`).
- `pytest -q`: passed (`64 passed in 313.33s`).

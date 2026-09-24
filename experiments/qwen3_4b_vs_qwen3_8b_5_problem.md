# qwen3:4b vs qwen3:8b — 5-problem controlled comparison

## Setup

- Date: 2026-09-24 UTC
- Git commit: `ac2379b5711df728eee465f0797091806b24cf0c`
- Backend: Ollama HTTP (`ollama 0.34.3`)
- Models: `qwen3:4b` and `qwen3:8b`
- Benchmark hash recorded by both runs: `7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7`
- Problems: `arith_add_zero`, `algebra_mul_inv_cancel`, `logic_implication_trans`, `ineq_square_nonnegative`, `sets_preimage_inter`
- Maximum attempts: formalization 3, proof 3, semantic-equivalence 2 per direction
- Lean timeout: 120 seconds; toolchain: `leanprover/lean4:v4.34.0`
- Explicit model parameters: none. Both runs used the same prompts and Ollama defaults.

The qwen3:4b baseline is stored locally in `experiments/q4s2` and `experiments/q4m5`; their configs are identical apart from experiment name, timestamp, and problem selection. The qwen3:8b run is stored locally in `experiments/q8m5`. Large per-attempt artifacts are intentionally not versioned.

## Aggregate results

These are the persisted pipeline metrics. A qwen3:8b timeout during the third algebra proof request caused that whole problem to be represented as a backend failure, so the pipeline summary records zero attempts and no tokens for that problem. The executed-attempt evidence is described below rather than silently imputed into these metrics.

| Metric | qwen3:4b | qwen3:8b |
| --- | ---: | ---: |
| Formalization first-pass success | 4/5 (80%) | 2/5 (40%) |
| Final formalization success | 4/5 (80%) | 4/5 (80%) |
| Formalization repair gain | +0 (+0 pp) | +2 (+40 pp) |
| Proof first-pass success | 0/5 (0%) | 2/5 (40%) |
| Final verified success | 2/5 (40%) | 2/5 (40%) |
| Proof repair gain | +2 (+40 pp) | +0 (+0 pp) |
| Semantic equivalent | 0/5 (0%) | 0/5 (0%) |
| Semantic unknown | 5/5 (100%) | 5/5 (100%) |
| Average formalization attempts (pipeline) | 1.40 | 1.20 |
| Average proof attempts (pipeline) | 2.00 | 1.60 |
| Average latency | 493.13 s | 858.59 s |
| Total latency | 2,465.64 s | 4,292.94 s |
| Input tokens (pipeline) | 9,144 | 8,510* |
| Output tokens (pipeline) | 99,114 | 62,115* |
| Total tokens (pipeline) | 108,258 | 70,625* |

`*` The qwen3:8b token totals exclude the algebra problem after its backend timeout. Completed algebra artifacts add 579 input and 5,100 output tokens, making the known lower bound 9,089 input, 67,215 output, and 76,304 total tokens. The timed-out third request did not return usage, so the exact qwen3:8b total is unavailable.

Artifact evidence shows that qwen3:8b actually executed 7 formalization attempts (average 1.40) and 11 proof requests (average 2.20), including the timed-out algebra request. The persisted pipeline averages are lower because the backend-failure record resets that problem's stage counts to zero.

## Per-problem comparison

Attempts are formalization/proof requests. The qwen3:8b algebra entry uses artifact-observed attempts because the pipeline-level backend-failure record reports `0/0` after discarding partial stage metrics.

| Problem | 4B verified | 8B verified | 4B attempts | 8B attempts | 4B latency | 8B latency |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `arith_add_zero` | yes | yes | 1/2 | 2/1 | 449.95 s | 928.34 s |
| `algebra_mul_inv_cancel` | no | no | 1/3 | 1/3* | 635.28 s | 873.97 s |
| `logic_implication_trans` | yes | yes | 1/2 | 1/1 | 528.70 s | 723.16 s |
| `ineq_square_nonnegative` | no | no | 1/3 | 1/3 | 628.31 s | 866.73 s |
| `sets_preimage_inter` | no | no | 3/0 | 2/3 | 223.39 s | 900.73 s |

`*` The third qwen3:8b algebra proof request timed out at the Ollama HTTP boundary and produced no Lean attempt file or token report.

| Problem | 4B equivalence | 8B equivalence |
| --- | --- | --- |
| `arith_add_zero` | forward verified; backward unknown | forward failed (backend timeout); backward verified |
| `algebra_mul_inv_cancel` | forward unknown; backward unknown | not run after backend failure |
| `logic_implication_trans` | forward verified; backward unknown | forward unknown; backward verified |
| `ineq_square_nonnegative` | forward unknown; backward unknown | forward unknown; backward unknown |
| `sets_preimage_inter` | not run because formalization failed | forward unknown; backward unknown |

Every final equivalence result is `unknown`. This is not evidence of semantic incorrectness: failure to prove equivalence is not proof of inequivalence, and no human semantic-review result was added.

## Failure analysis

### `arith_add_zero`

- qwen3:4b: the statement was well formed on the first attempt. Its first proof failed and compiler feedback enabled the second attempt to verify.
- qwen3:8b: the first formalization improperly included a proof body (`:= Nat.add_zero n`) and was rejected by the statement-only safety check. The second statement was accepted and the first proof (`by rfl`) verified.
- Categories: malformed model output (8B first formalization); semantic-equivalence search/backend failure. Both final proofs verified.

### `algebra_mul_inv_cancel`

- qwen3:4b: the statement was well formed, but all three proofs failed. The last attempt misused `mul_inv_eq_one` as a function.
- qwen3:8b: the first statement was well formed and matched the reference shape. Proof 1 (`simp [mul_inv_cancel]`) made no progress; proof 2 hallucinated `Field.mul_inv`; proof request 3 timed out after about ten minutes. The pipeline conservatively recorded a backend failure for the problem.
- Categories: wrong theorem/lemma; Lean/API name hallucination; failed proof search; provider/backend timeout.

### `logic_implication_trans`

- qwen3:4b: formalization passed first try; compiler feedback repaired the first proof failure and the second proof verified.
- qwen3:8b: formalization and proof both passed first try. It expressed the hypotheses as nested implications instead of named hypothesis binders.
- Categories: semantic-equivalence search failure only. The automatic result remains `unknown`; no human semantic claim is made.

### `ineq_square_nonnegative`

- qwen3:4b: formalization passed, but proof search ended with the nonexistent `real.square_nonneg`.
- qwen3:8b: formalization passed. Proof attempts used nonexistent `Real.sq_nonneg`, then returned a long explanatory/non-Lean answer, then used nonexistent `Real.mul_self_nonneg`.
- Categories: Lean/API name hallucination; wrong theorem/lemma; malformed proof output; failed proof search; semantic-equivalence search failure.

### `sets_preimage_inter`

- qwen3:4b: all three formalizations omitted explicit type binders, which `set_option autoImplicit false` rejected; proof generation was therefore not entered.
- qwen3:8b: attempt 1 hallucinated `f.preimage`; compiler feedback repaired the statement on attempt 2. All three proofs failed: invalid tactic syntax and nonexistent membership helpers, with the second attempt returning a long tutorial/code-fence answer instead of a proof term.
- Categories: 4B formalization failure; 8B Lean/API name hallucination, malformed proof output, and failed proof search; semantic-equivalence search failure.

No observed case was classified as wrong type/domain or missing assumption. Those categories remain valid taxonomy entries, but assigning them here would overstate the evidence.

## Conclusions

- qwen3:8b did not solve more problems: both models verified 2/5, specifically arithmetic and logic.
- The 8B improvement was in first-pass proof generation and formalization repair, not final proof coverage. It converted two malformed statements after compiler feedback, but did not repair any failed proof. The 4B model repaired two failed proofs but no failed formalization.
- Compiler feedback rescued 2 final successes for qwen3:4b (both proof-stage) and 2 final formalizations for qwen3:8b (formalization-stage), but those 8B repairs did not add verified proofs.
- qwen3:8b cost 1,827.30 seconds more total latency: 4,292.94 s versus 2,465.64 s, a 1.74x / 74.1% increase. Exact token cost cannot be compared because the timed-out 8B request returned no usage; its known lower bound is 76,304 tokens versus 108,258 for 4B.
- A 15–20 problem expansion is not yet justified under the current runtime behavior. The next controlled check should first determine whether the 8B backend timeout and long reasoning outputs are reproducible without changing prompts or proof strategy. If stable resource limits can be established, a stratified 15–20 problem comparison would then be worthwhile.

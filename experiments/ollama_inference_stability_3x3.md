# Ollama inference stability: qwen3:4b vs qwen3:8b

Date: 2026-09-25
Git commit used for every run: `0b67f0da6910768b29d17f479557f6aee44bace6`

## Research question

Are the long qwen3:8b generations and the previously observed 600-second
Ollama HTTP timeout reproducible under unchanged evaluation conditions?

## Controlled setup

- Models: Ollama `qwen3:4b` (`359d7dd4bcda`) and `qwen3:8b`
  (`500a1f067a9f`), Ollama 0.34.3.
- Problems: `algebra_mul_inv_cancel`, `ineq_square_nonnegative`, and
  `sets_preimage_inter`.
- Three repetitions per model, alternated as 4B-r1, 8B-r1, 4B-r2, 8B-r2,
  4B-r3, 8B-r3.
- Unchanged benchmark hash:
  `7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7`.
- Unchanged limits: three formalization attempts, three proof attempts, two
  equivalence attempts per direction, 120-second Lean timeout, and 600-second
  Ollama HTTP timeout.
- No explicit temperature, `num_predict`, `keep_alive`, or context-length
  override was sent. Prompts, benchmark statements, Lean/Mathlib, ProofAgent,
  verification, and equivalence logic were unchanged.
- Host observation: Intel Core Ultra 9 275HX, 31.4 GiB RAM, RTX 5070 Laptop
  GPU with 8,151 MiB reported VRAM. Hardware utilization was not instrumented,
  so resource causality is not claimed.

The rates below use completed model generations as the denominator for
malformed-output, code-fence, explanatory-text, and Lean/API-hallucination
classifications. A malformed output is an artifact rejected by the existing
safety/format checks. A hallucination is a Lean diagnostic for an unknown or
invalid identifier, constant, tactic, or API-style name. These are operational
diagnostic labels, not semantic-correctness judgments.

## Aggregate results

| Metric | qwen3:4b | qwen3:8b |
|---|---:|---:|
| Runs / problem-runs | 3 / 9 | 3 / 9 |
| HTTP timeouts | 0 / 53 issued requests | 0 / 67 issued requests |
| Other backend failures | 1 / 9 problem-runs | 0 / 9 problem-runs |
| First-pass formalization | 3/9 (33.3%) | 5/9 (55.6%) |
| Final formalization | 5/9 (55.6%) | 8/9 (88.9%) |
| Formalization repair gain | +2 (+22.2 pp) | +3 (+33.3 pp) |
| Final verified proof | 0/9 (0%) | 0/9 (0%) |
| Proof repair gain | 0 | 0 |
| Semantic equivalent / unknown | 0 / 9 | 1 / 8 |
| Average formalization attempts | 1.89 | 1.67 |
| Average proof attempts | 1.67 | 2.67 |
| Median / max problem latency | 661.5 / 1,020.1 s | 911.4 / 1,212.8 s |
| Total latency | 5,111.1 s (85.2 min) | 7,515.6 s (125.3 min) |
| Median / max generation latency | 60.3 / 120.8 s | 46.0 / 228.2 s |
| Median output tokens per generation | 3,279.5 | 1,584 |
| Longest generation output | 6,149 tokens | 7,732 tokens |
| Median generation throughput | 53.6 tok/s | 34.2 tok/s |
| Input / output / total tokens | 16,220 / 169,006 / 185,226 | 21,911 / 157,934 / 179,845 |
| Malformed-output rate | 10/52 (19.2%) | 18/67 (26.9%) |
| Code-fence rate | 10/52 (19.2%) | 16/67 (23.9%) |
| Explanatory-text rate | 6/52 (11.5%) | 16/67 (23.9%) |
| Lean/API-hallucination rate | 26/52 (50.0%) | 19/67 (28.4%) |

The 8B total was 47.0% slower despite reporting 2.9% fewer total tokens. This
is partly because it reached the proof and equivalence stages more often, and
partly because its median output throughput was lower. Output-token count and
generation time were almost perfectly correlated in these runs (Pearson
`r=0.997` for 4B and `r=0.998` for 8B).

## Per-run results

| Run | First/final formalization | Verified | Equivalent/unknown | Latency (s) | Input/output tokens | Malformed | Hallucination |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4B-r1 | 1/2 | 0 | 0/3 | 2,184.9 | 6,126/66,504 | 3/20 | 9/20 |
| 4B-r2 | 1/1 | 0 | 0/3 | 1,236.4 | 4,271/45,433 | 5/14 | 7/14 |
| 4B-r3 | 1/2 | 0 | 0/3 | 1,689.8 | 5,823/57,069 | 2/18 | 10/18 |
| 8B-r1 | 1/3 | 0 | 1/2 | 2,558.8 | 6,836/53,351 | 5/25 | 7/25 |
| 8B-r2 | 2/3 | 0 | 0/3 | 3,043.4 | 8,182/58,382 | 7/23 | 7/23 |
| 8B-r3 | 2/2 | 0 | 0/3 | 1,913.4 | 6,893/46,201 | 6/19 | 5/19 |

## Per-problem repetitions

`F/P` is formalization/proof attempts. Generation latency is the sum of
completed model calls for that problem, including equivalence assistance.

| Run | Problem | F/P | Verified | Equivalence | Generation / total latency (s) | Input/output tokens | Timeout | Malformed / hallucination |
|---|---|---:|:---:|:---:|---:|---:|:---:|---:|
| 4B-r1 | algebra | 2/3 | no | unknown | 624.4 / 1,020.1 | 2,767/33,215 | no | 2/3 |
| 4B-r1 | inequality | 1/3 | no | unknown | 452.4 / 873.0 | 1,930/23,710 | no | 0/4 |
| 4B-r1 | sets | 3/0 | no | unknown | 184.1 / 291.8 | 1,429/9,579 | no | 1/2 |
| 4B-r2 | algebra | 3/0 | no | unknown | 216.9 / 303.3 | 829/11,273 | no | 1/2 |
| 4B-r2 | inequality | 1/3 | no | unknown | 454.5 / 661.5 | 1,954/24,309 | no | 3/3 |
| 4B-r2 | sets | 3/0 | no | unknown | 184.8 / 271.6 | 1,488/9,851 | no | 1/2 |
| 4B-r3 | algebra | 3/3 | no | unknown | 633.1 / 1,001.1 | 4,045/33,555 | no | 1/6 |
| 4B-r3 | inequality | 1/3 | no | unknown | 419.8 / 684.8 | 1,778/23,514 | no | 1/4 |
| 4B-r3 | sets | 0/0 | no | unknown | 0.0 / 4.0 | unavailable | no | 0/0 |
| 8B-r1 | algebra | 2/3 | no | equivalent | 460.1 / 916.4 | 2,246/15,828 | no | 0/4 |
| 8B-r1 | inequality | 3/3 | no | unknown | 574.3 / 808.4 | 2,158/19,508 | no | 4/3 |
| 8B-r1 | sets | 1/3 | no | unknown | 546.3 / 833.9 | 2,432/18,015 | no | 1/0 |
| 8B-r2 | algebra | 2/3 | no | unknown | 622.2 / 919.2 | 2,740/20,690 | no | 2/4 |
| 8B-r2 | inequality | 1/3 | no | unknown | 429.7 / 1,212.8 | 1,914/14,416 | no | 2/2 |
| 8B-r2 | sets | 1/3 | no | unknown | 694.6 / 911.4 | 3,528/23,276 | no | 3/1 |
| 8B-r3 | algebra | 3/0 | no | unknown | 92.6 / 215.8 | 853/2,984 | no | 0/3 |
| 8B-r3 | inequality | 1/3 | no | unknown | 453.6 / 698.6 | 2,464/15,542 | no | 2/1 |
| 8B-r3 | sets | 1/3 | no | unknown | 815.4 / 999.0 | 3,576/27,675 | no | 4/1 |

## Stability and failure analysis

- The earlier isolated 8B HTTP timeout did **not** reproduce: all three 8B
  repetitions completed without a backend timeout. Consequently, no
  single-variable timeout or output-limit intervention was run.
- Long-tail generation **did** reproduce. The longest 8B request took 228.2
  seconds and emitted 7,732 tokens. Every 8B repetition contained a request
  above 211 seconds. The strong output-length/latency correlation and lower 8B
  throughput make long output the best-supported cause. Larger-model resource
  cost is a plausible secondary factor; a pipeline timeout is not the primary
  cause in this sample because the 600-second threshold was never reached.
- 8B was materially more reliable at producing a final well-formed statement,
  especially for the set problem, but neither model verified any final proof on
  this deliberately difficult three-problem subset.
- Common malformed outputs were fenced Lean embedded in explanations, repeated
  final-answer blocks, and prose in place of code-only output.
- Common Lean/API hallucinations included `inv`, invented reciprocal lemmas such
  as `inv_mul_self_eq_one`, invented nonnegativity names such as
  `Real.mul_self_nonneg`, and attempts to invoke `sets_preimage_inter` as if it
  were already available.
- Proof-search failures included incorrect lemma selection, applying hypotheses
  with incompatible shapes, and tactic misuse on set-extensionality goals.
- 4B-r3 had one non-timeout backend failure: Ollama returned no generated text
  for the set problem. The prior two problems' completed attempts and token
  metrics remained persisted; the failed call correctly has unavailable usage.
- Eight 8B equivalence results and all nine 4B results remained `unknown`.
  Search failure is not treated as inequivalence or semantic incorrectness.

## Decision

Do not expand this unchanged setup directly to 15--20 problems yet. At observed
rates, the two-model expansion would consume many hours while this hard subset
produced no verified proofs. A future, separately controlled experiment should
first test one inference variable such as `num_predict`, but this run did not do
so because the stated prerequisite (reproducible 8B timeout) was absent.

Keep both models for research comparison: use 4B as the faster iteration
baseline and 8B as the stronger formalization comparator. The data do not
support replacing 4B with 8B as the default proof pipeline because both had a
0% verified rate here and 8B cost 47% more wall time.

## Verification

- `lake build`: passed (`Build completed successfully (8925 jobs)`).
- `pytest -q`: 60 passed in 471.43 seconds.

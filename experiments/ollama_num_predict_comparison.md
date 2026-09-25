# Ollama `num_predict` comparison for qwen3:8b

## Research question

How does Ollama's output-token cap affect qwen3:8b latency, output length, and
verified Lean performance in the existing LeanProofAgent pipeline?

## Controlled setup

- Model: `qwen3:8b` through the local Ollama backend.
- Problems: `algebra_mul_inv_cancel`, `ineq_square_nonnegative`, and
  `sets_preimage_inter`.
- Conditions: default (`num_predict` omitted), `num_predict=2048`, and
  `num_predict=4096`.
- Repetitions: two per condition. The first round used default, 2048, 4096;
  the second used the reverse order to reduce ordering bias.
- Fixed across conditions: prompts, benchmark, ProofAgent, Lean verifier,
  proof/formalization strategy, Mathlib environment, attempt limits,
  temperature, and context length.
- Attempt limits: 3 formalization attempts, 3 proof attempts, and 2 semantic
  equivalence attempts.

The default/2048/4096 conditions issued 45/23/25 generations respectively.
Runs with an explicit cap can terminate a problem early when Ollama returns an
empty response at the cap, so token totals for those conditions are lower
bounds rather than directly comparable complete totals.

## Aggregate results

Rates use the six problem-runs in each condition unless the denominator is
shown as generations.

| Metric | Default | 2048 | 4096 |
| --- | ---: | ---: | ---: |
| First-pass formalization success | 3/6 (50.0%) | 3/6 (50.0%) | 3/6 (50.0%) |
| Final formalization success | 5/6 (83.3%) | 6/6 (100.0%) | 4/6 (66.7%) |
| Formalization repair gain | +2 (+33.3 pp) | +3 (+50.0 pp) | +1 (+16.7 pp) |
| Final verified proof | 0/6 (0.0%) | 0/6 (0.0%) | 0/6 (0.0%) |
| Average formalization attempts | 1.67 | 1.50 | 1.50 |
| Average proof attempts | 2.50 | 1.00 | 1.00 |
| Malformed/cap-ended output | 8/45 (17.8%) | 7/23 (30.4%) | 6/25 (24.0%) |
| Code-fence output | 7/45 (15.6%) | 0/23 (0.0%) | 1/25 (4.0%) |
| Explanatory-text output | 7/45 (15.6%) | 0/23 (0.0%) | 2/25 (8.0%) |
| Lean/API hallucination | 5/45 (11.1%) | 4/23 (17.4%) | 4/25 (16.0%) |
| Token-cap hit | 0/45 (0.0%) | 7/23 (30.4%) | 5/25 (20.0%) |
| Median generation latency | 25.58 s | 15.80 s | 22.04 s |
| Mean generation latency | 33.41 s | 19.19 s | 27.80 s |
| Longest generation | 99.88 s | 38.25 s | 73.63 s |
| Median completed output length | 1,330 tokens | 892 tokens | 1,338 tokens |
| Mean completed output length | 1,852 tokens | 1,067 tokens | 1,603 tokens |
| Total experiment latency | 1,866.36 s | 923.31 s | 1,265.00 s |
| Input tokens recorded | 14,097 | 4,643* | 5,513* |
| Output tokens recorded | 83,341 | 19,204* | 35,266* |
| Total tokens recorded | 97,438 | 23,847* | 40,779* |
| Semantic equivalence | 0 equivalent, 6 unknown | 0 equivalent, 6 unknown | 0 equivalent, 6 unknown |

`*` Lower bound: Ollama did not report usage for empty responses terminated by
the token cap. The smaller capped totals also reflect fewer downstream proof
generations after those backend failures.

The malformed/cap-ended row is a conservative union: it includes malformed
non-empty responses and empty cap-ended responses. Pure format rejection was
8/45 for default, 0/23 for 2048, and 2/25 for 4096.

## Per-run results

| Condition | Run | First/final formalization | Verified | Formalization/proof attempts | Total latency | Completed generations | Recorded input/output tokens | Malformed | Fence | Explanation | Hallucination |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Default | 1 | 1/3, 2/3 | 0/3 | 6 / 6 | 788.41 s | 20 | 6,146 / 30,358 | 3 | 2 | 2 | 3 |
| Default | 2 | 2/3, 3/3 | 0/3 | 4 / 9 | 1,077.95 s | 25 | 7,951 / 52,983 | 5 | 5 | 5 | 2 |
| 2048 | 1 | 2/3, 3/3 | 0/3 | 4 / 3 | 478.86 s | 7 | 1,688 / 9,005* | 5 | 0 | 0 | 2 |
| 2048 | 2 | 1/3, 3/3 | 0/3 | 5 / 3 | 444.45 s | 11 | 2,955 / 10,199* | 2 | 0 | 0 | 2 |
| 4096 | 1 | 2/3, 2/3 | 0/3 | 5 / 3 | 589.61 s | 12 | 2,994 / 18,854* | 2 | 0 | 1 | 3 |
| 4096 | 2 | 1/3, 2/3 | 0/3 | 4 / 3 | 675.39 s | 10 | 2,519 / 16,412* | 4 | 1 | 1 | 1 |

## Findings

### Latency and output length

Compared with default, 2048 reduced observed total experiment latency by
50.5%, mean generation latency by 42.5%, longest-generation latency by 61.7%,
and mean completed output length by 42.4%. The corresponding reductions for
4096 were 32.2%, 16.8%, 26.3%, and 13.4%.

These are large observed effects, but two repetitions per condition are not
enough to claim statistical significance. Recorded token totals must not be
interpreted as exact savings because capped empty responses have unavailable
usage and stop later pipeline work.

### Output shape and truncation

Both caps reduced code fences and explanatory text among persisted outputs.
That does not by itself indicate improved quality: 2048 hit the cap in 30.4%
of issued generations, and 4096 hit it in 20.0%. Every persisted non-empty
truncated proof attempt failed. Ollama also returned empty responses with
`done_reason=length` at both explicit caps, causing early backend failure.

Thus 2048 is too aggressive for this workload. It shortens the long tail but
frequently cuts off proof generations. 4096 is a better balance among the two
explicit caps, although its 20% cap-hit rate remains material.

### Verification and semantic status

All conditions verified 0/6 problem-runs. Therefore the experiment does not
show a numerical decrease in final verification, but this is a floor effect,
not evidence that truncation is harmless. Proof attempts fell from 15 under
default to 6 under each capped condition because backend failures prevented
the remaining attempts. All semantic equivalence checks remained `unknown`;
none is treated as semantic incorrectness.

## Recommendation and limitations

`num_predict=4096` is the best tested explicit cap: it substantially reduces
the latency tail and unwanted extra text while being less destructive than
2048. It is not yet a safe formal-benchmark default. The 20% cap-hit rate,
zero verified successes, incomplete capped token accounting, and only two
repetitions make a 15–20-problem expansion premature.

Before scaling, validate 4096 on a small set that includes previously
successful proofs and confirm that cap-ended empty responses no longer erase
useful downstream coverage. Keep the uncapped default as the completeness
control and retain 2048 only as an intentionally aggressive latency condition.

## Verification

- `lake build`: passed (`8925 jobs`).
- `pytest -q`: passed (`64 passed in 270.38s`).

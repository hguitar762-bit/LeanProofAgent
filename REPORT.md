# LeanProofAgent: Compiler-Guided Verifiable Mathematical Reasoning with Lean 4

## Abstract

LeanProofAgent is a small-scale reproducible experimental system for studying
whether compiler feedback and lightweight premise retrieval improve verifiable
mathematical reasoning with small local language models. The system translates
natural-language propositions into Lean 4 statements, validates them in a pinned
Mathlib environment, generates proofs, and returns exact Lean diagnostics for
bounded statement and proof repair. An optional deterministic lexical retriever
adds a small list of real Mathlib declaration names and signatures to the proof
prompt. Lean's kernel is the only proof-success oracle.

On a frozen 18-problem benchmark, qwen3:4b and qwen3:8b verified 5/18 and 6/18
problems respectively; the 8B run took 12.0% longer and did not show a reliable
model-size advantage. For qwen3:4b, top-10 Mathlib retrieval produced an observed
increase from 5/18 to 7/18 verified problems and reduced proof-stage Lean/API
hallucination signals from 31.0% to 16.2%. The same retrieval run caused three
regressions, increased wrong-lemma application, raised latency by 17.3%, and
substantially enlarged proof prompts. The evidence supports compiler feedback
and premise context as useful research directions, but not a statistical claim
or a state-of-the-art result.

## 1. Introduction

Large language models can write Lean-like text, yet surface plausibility does
not imply elaboration or proof correctness. Common failures include extra prose,
unknown declarations, incompatible lemma applications, invalid tactics, and
unfinished goals. A proof assistant offers a precise distinction: a candidate
is either accepted in the pinned environment or it is accompanied by a concrete
diagnostic.

This project studies the question:

> Can compiler feedback and lightweight premise retrieval improve verifiable
> mathematical reasoning for small local language models?

LeanProofAgent operationalizes this question with bounded generate-check-repair
loops, conservative semantic-equivalence search, local Ollama models, immutable
benchmark inputs, and persisted artifacts. Its intended contribution is a
compact and auditable experimental implementation. It does not claim to invent
LLM-assisted proof repair, premise selection, or autoformalization.

Two correctness boundaries are kept separate. Lean verification establishes
that a proof term inhabits the generated Lean proposition. It does not establish
that the proposition preserves the intended meaning of the natural-language
input. Human semantic review therefore remains independent of proof success.

## 2. Related Work

[Lean 4](https://lean-lang.org/doc/reference/latest/) is an interactive theorem
prover and programming language based on dependent type theory. Its elaborator
translates user syntax to core terms, while the small trusted kernel checks those
terms; tactics do not enlarge the proof trust boundary. LeanProofAgent uses this
kernel check, through the pinned project environment, as its sole verification
criterion.

[Mathlib](https://leanprover-community.github.io/mathlib4_docs/Mathlib/) is the
community mathematical library for Lean. It supplies the definitions, theorems,
and tactics available to generated proofs. Mathlib's scale also creates a premise
selection problem: models may know the mathematical fact but hallucinate its Lean
name or apply a real theorem with the wrong signature.

[LeanDojo and ReProver](https://arxiv.org/abs/2306.15626) provide tooling,
benchmarks, proof-environment interaction, and a learned retrieval-augmented
prover. Their work demonstrates the importance of accessible-premise analysis
and learned premise selection at much larger scale. LeanProofAgent's retriever is
intentionally more modest: local lexical matching, no learned embeddings, no
vector database, and no training.

[Lean Copilot](https://arxiv.org/abs/2404.12534) integrates model inference,
tactic suggestion, proof search, and premise selection into Lean's interactive
workflow. LeanProofAgent instead evaluates a standalone, whole-statement and
whole-proof pipeline with saved compiler-feedback attempts.

[DeepSeek-Prover](https://arxiv.org/abs/2405.14333) studies large-scale synthetic
Lean data and model specialization, while
[DeepSeek-Prover-V1.5](https://arxiv.org/abs/2408.08152) adds proof-assistant
feedback and search. LeanProofAgent trains no model and uses much smaller local
qwen3 models; direct performance comparisons would therefore be inappropriate.

[ProofNet](https://arxiv.org/abs/2302.12433) introduced a benchmark for
autoformalizing and proving undergraduate-level mathematics. It motivates the
separation of natural-language formalization from downstream theorem proving.
LeanProofAgent uses a small custom benchmark designed for controlled local
experiments rather than claiming ProofNet-scale coverage.

Compiler-guided repair and iterative proof search also appear in prior systems
such as [COPRA](https://arxiv.org/abs/2310.04353). Accordingly, this project makes
no priority claim for combining language models with Lean feedback. Its position
is a **small-scale reproducible experimental system** that exposes the complete
attempt history and preserves conservative interpretation boundaries.

## 3. System Design

### 3.1 Autoformalization

The autoformalizer receives natural language, a required theorem name, and
imports. It must return exactly one theorem declaration without a proof body.
Code fences, extra commands, `sorry`, `admit`, `axiom`, `where`, and `:=` are
rejected before elaboration. Rejected or invalid statements can be repaired for
a fixed number of attempts using the exact prior diagnostic.

### 3.2 Lean statement validation

A structurally safe statement is elaborated in a temporary Lean source file with
`set_option autoImplicit false`. The temporary declaration is used only to ask
Lean whether names and types elaborate. A Lean metaprogram then checks that the
declaration type is a proposition. This stage never counts an axiom as a proof
and never passes the temporary declaration to proof generation.

### 3.3 ProofAgent

`ProofAgent` appends a candidate proof to a theorem-only declaration and invokes
`lake env lean` with an argument list. Exit code zero is the only success
condition. Every attempt saves the generated source, normalized proof, command,
exit code, stdout, stderr, duration, and provider usage when available.

### 3.4 Compiler-guided repair

After a failed attempt, the next proof prompt includes the previous proof and
Lean's compiler feedback. Repair is bounded rather than open-ended. This design
allows first-pass success and repair gain to be measured separately and prevents
an unsuccessful model from looping indefinitely.

### 3.5 Semantic-equivalence checking

The checker closes the explicit binders of generated and reference statements
and independently asks the same kernel-verified proof loop to establish both
implications. Two verified directions yield `equivalent`. Exhausted proof search
yields `unknown`, never `not_equivalent`. This mechanism is incomplete and is
not a replacement for human evaluation of natural-language fidelity.

### 3.6 Premise retrieval

`MathlibRetriever` extracts identifiers, qualified names, theorem-name tokens,
and symbolic aliases from the generated theorem. It asks the exact imported
local Lean environment for matching declarations, deterministically ranks the
names, uses Lean `isProp` to retain proposition-valued declarations, and records
the pretty-printed signature and source module. Work is bounded to avoid broad
high-frequency searches, and no more than top-k candidates are returned.

The candidates are auxiliary prompt context only. They do not bypass Lean and
do not change the verifier. There is no embedding model, vector store, remote
retrieval service, or benchmark answer table. Retrieval is off by default; when
enabled, the exact candidates are written to `premises.json`.

## 4. Experimental Setup

### 4.1 Software and models

- Lean toolchain: `leanprover/lean4:v4.34.0`.
- Mathlib release: `v4.34.0`; manifest commit
  `5ed2965256430c3649e86755f9576b54eca72435`.
- Python: 3.11+ supported; final local verification used Python 3.12.10.
- Local backend: Ollama 0.34.3 for early studies and 0.34.4 for the formal
  18-problem benchmark and retrieval ablation.
- Models: `qwen3:4b` and `qwen3:8b`.
- Formal-run generation configuration: Ollama defaults, with no explicit
  temperature, context length, or `num_predict` override.

The hardware inventory recorded during the stability study was an Intel Core
Ultra 9 275HX, 31.4 GiB RAM, and an RTX 5070 Laptop GPU with 8,151 MiB reported
VRAM. Utilization was not instrumented, so the experiments do not attribute
latency differences to a particular component and do not claim portability.

### 4.2 Benchmark

The formal benchmark contains 18 problems: easy, medium, and hard entries in
arithmetic, algebra, logic, inequalities, sets, and functions. It was frozen
before the formal runs. The directory SHA-256 is
`7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7`;
the curated source file SHA-256 is
`ec0baf9b54a8a06e1c4ae5b3e88821833500ba1bc44b380ed9438e2d0efe408c`.

The suite is intentionally small. It supports paired diagnostic analysis, not
strong category estimates or statistical performance claims.

### 4.3 Attempts and metrics

Formal experiments allowed at most three formalization attempts, three proof
attempts, and two equivalence attempts in each direction, with a 120-second Lean
timeout. Main metrics were first-pass and final formalization, first-pass and
final proof success, repair gain, failure signals, attempts, latency, and
provider-reported token usage.

Success always means a real Lean exit code of zero. Diagnostic signals such as
malformed output, API hallucination, wrong lemma, and tactic misuse are
artifact-level heuristics that can overlap. Missing usage is not imputed; totals
with absent provider data are reported as lower bounds.

## 5. Experiments

### 5.1 qwen3:4b vs qwen3:8b

An initial five-problem controlled comparison used identical prompts, attempts,
toolchain, benchmark hash, and Ollama defaults. Both models verified 2/5. The 4B
model needed proof repair for both successes; the 8B model verified both on the
first proof attempt but required more formalization repair. The 8B run took
4,292.94 seconds versus 2,465.64 seconds for 4B, a 1.74x increase. One 8B request
timed out, so its exact token total is unavailable and the recorded total is a
lower bound.

### 5.2 Inference stability

Three difficult problems were repeated three times per model in alternating
order. Neither model verified any of the nine problem-runs. The previously seen
600-second 8B timeout did not reproduce, but long-tail generation did: every 8B
repetition contained a request above 211 seconds, with a maximum of 228.2
seconds. The 8B condition took 47.0% more total wall time even though its
reported total token count was slightly lower. This study demonstrated both
stochastic output variance and the danger of inferring speed from token count
alone.

### 5.3 `num_predict` experiment

On the same hard subset, Ollama default, `num_predict=2048`, and
`num_predict=4096` each verified 0/6 problem-runs. The caps shortened output and
latency, but 2048 terminated 30.4% and 4096 terminated 20.0% of issued
generations at the token limit. Capped calls sometimes returned no usable text,
preventing later repair attempts and making token totals lower bounds.

A subsequent seven-problem mixed-difficulty calibration observed 2/7 verified
with default and 3/7 with 4096. However, an easy-problem repeat changed from 2/2
verified under default to 0/2 under 4096, including direct truncation of an
`arith_add_zero` repair call. The predeclared decision was therefore to keep
Ollama defaults for the formal benchmark. This negative result is retained
rather than selecting the faster primary calibration outcome.

### 5.4 Formal 18-problem benchmark

The formal comparison ran qwen3:4b and qwen3:8b serially with the same prompts,
limits, benchmark, verifier, and default generation configuration. The official
raw runs each contain 18 records. An earlier path-length-invalid 4B attempt was
discarded in full before comparison; no individual problem was rerun by outcome.

| Metric | qwen3:4b | qwen3:8b |
| --- | ---: | ---: |
| First-pass formalization | 10/18 (55.6%) | 10/18 (55.6%) |
| Final formalization | 16/18 (88.9%) | 17/18 (94.4%) |
| Formalization repair gain | +6 (+33.3 pp) | +7 (+38.9 pp) |
| First-pass proof | 3/18 (16.7%) | 3/18 (16.7%) |
| Final verified proof | 5/18 (27.8%) | 6/18 (33.3%) |
| Proof repair gain | +2 (+11.1 pp) | +3 (+16.7 pp) |
| Total latency | 7,083.47 s | 7,934.87 s |

The 8B model gained three cases and lost two relative to 4B. The observed net
gain of one problem is not compelling on 18 cases; a paired two-sided sign view
of the five discordant outcomes gives p = 1.0. Both conditions ended with 11
well-formed but unverified statements, locating the principal bottleneck in
proof generation rather than statement syntax.

### 5.5 Mathlib retrieval ablation

The saved qwen3:4b formal baseline was reused. The retrieval arm used the same
model, benchmark hash, prompts except for premise context, attempt counts,
toolchain, timeout, and Ollama defaults. Top-k 10 was fixed before the run. Two
implementation pilots that exceeded the retrieval timeout were stopped and
excluded in full; bounded retrieval was then fixed before the complete official
run. No top-k sensitivity tuning was performed.

| Metric | Baseline | Retrieval | Change |
| --- | ---: | ---: | ---: |
| First-pass proof | 3/18 (16.7%) | 3/18 (16.7%) | 0 |
| Final verified proof | 5/18 (27.8%) | 7/18 (38.9%) | +2 / +11.1 pp |
| Proof repair gain | +2 (+11.1 pp) | +4 (+22.2 pp) | +2 |
| Proof-stage API hallucination | 13/42 (31.0%) | 6/37 (16.2%) | -14.7 pp |
| Wrong/incompatible lemma | 2/42 (4.8%) | 9/37 (24.3%) | +19.6 pp |
| Tactic misuse | 9/42 (21.4%) | 6/37 (16.2%) | -5.2 pp |
| End-to-end latency | 7,083.47 s | 8,309.55 s | +17.3% |

Five problems became newly verified: `arith_add_zero`,
`algebra_real_mul_comm`, `algebra_mul_inv_cancel`, `ineq_lt_of_lt_of_le`, and
`func_injective_comp`. Three baseline successes regressed:
`algebra_square_sum`, `logic_and_comm`, and `sets_diff_membership`. Every one of
the seven retrieval-arm successes used an exact retrieved declaration name, but
every nonempty top-k list also contained clearly irrelevant candidates.

The aggregate first-pass rate was unchanged. The net final gain appeared in the
increase in repair gain, even though three of the five newly successful
individual cases happened to pass on their first retrieval proof attempt.

## 6. Results

| Study | Principal result | Cost or caution |
| --- | --- | --- |
| Initial 4B vs 8B, 5 problems | both 2/5 verified | 8B 1.74x slower; one timeout |
| Stability, 3 problems × 3 runs/model | both 0/9 verified | large stochastic and latency variance |
| Hard-subset `num_predict` | all conditions 0/6 | caps removed repair opportunities |
| Mixed `num_predict` calibration | 4096 observed 3/7 vs default 2/7 | easy repeat regressed from 2/2 to 0/2 |
| Formal 18-problem model comparison | 4B 5/18; 8B 6/18 | 8B +12.0% latency; no reliable size effect |
| Retrieval ablation | 5/18 to 7/18; hallucination 31.0% to 16.2% | 3 regressions; wrong-lemma rate and cost rose |

Compiler feedback mattered at both stages. In the formal benchmark it rescued
six 4B and seven 8B formalizations, then added two and three verified proofs
respectively. Retrieval did not improve aggregate first-pass proof success; its
net gain was realized through the bounded repair loop.

The retrieval result is best interpreted as an observed tradeoff. It reduced
invented APIs but shifted errors toward real declarations used incorrectly.
Returned proof-attempt input tokens increased from 13,187 over 42 attempts to
32,257 over 37 attempts: +177.7% per returned attempt. Total tokens per returned
proof attempt rose 10.9%. Full retrieval totals are lower bounds because two
provider failures lacked complete usage.

## 7. Failure Analysis

### Malformed and explanatory output

Models sometimes returned Markdown fences, tutorials, multiple answer blocks,
or a proof body where a statement-only declaration was required. In the formal
18-problem comparison, code-fence signals occurred in 16/72 main-stage 4B
generations and 7/71 8B generations. Safety checks rejected these outputs rather
than attempting to interpret arbitrary prose as trusted code.

### Formalization failure

For `sets_preimage_inter`, one 4B run repeatedly omitted explicit type binders;
`set_option autoImplicit false` correctly rejected the statements. In another
case, 8B used an unqualified `inv` and never produced a final statement for
`algebra_mul_inv_cancel`. These are elaboration failures, not proof failures.

### Mathlib API hallucination

Representative nonexistent or inappropriate names included
`Data.Real.mul_comm`, `Even.two_mul`, `Real.mul_self_nonneg`, `Real.sq_nonneg`,
and `inv_mul_self_eq_one`. Returning exact compiler errors helped some cases,
but repeated name invention remained common without premise context.

### Wrong lemma or theorem

Retrieval replaced some nonexistent names with genuine but misapplied lemmas.
For `logic_and_comm`, the candidate list contained `and_comm`, yet the model
misapplied it as `and_comm P Q` and regressed from the baseline success. For
`sets_diff_membership`, the model over-focused on `Set.mem_diff*` declarations
instead of the direct constructor proof `⟨hA, hB⟩`.

### Tactic misuse

Proofs used invalid tactic syntax, invoked tactics that did not close the goal,
or performed rewrites with incompatible hypotheses. `algebra_square_sum`
illustrates retrieval distraction: irrelevant `IsSquare.*` candidates displaced
the baseline first-pass `by ring` proof and led to repeated failed rewrites.

### Retrieval irrelevance and regression

Lexical overlap does not establish applicability. Natural-number goals received
integer and bit-vector lemmas; a polynomial expansion received `IsSquare.*`
facts; implication transitivity received graph and category declarations; and a
polymorphic identity goal received homomorphism-specific `id_apply` lemmas. Such
noise plausibly contributes to the three observed regressions.

### Semantic equivalence unknown

Most equivalence checks remained `unknown`: 16/18 for 4B and 13/18 for 8B in
the formal benchmark. The generated `logic_contraposition` statement in one 4B
run was plausibly stronger than the reference, but bounded search did not
certify a relationship and no human label was substituted. Unknown is evidence
of search incompleteness, not semantic incorrectness.

## 8. Limitations

- The formal benchmark has only 18 problems, with three problems per category.
- The main model and retrieval comparisons contain one stochastic run per
  condition; local model result variance is substantial.
- Equivalence proof search is incomplete and logical equivalence of closed
  propositions is not full natural-language semantic validation.
- Lexical retrieval can return irrelevant premises and caused verified
  regressions.
- The system trains and fine-tunes no model.
- No improvement is claimed to be statistically significant.
- Diagnostic failure labels are operational heuristics, may overlap, and are
  not substitutes for expert semantic review.
- Some failed Ollama calls did not report usage, so affected token totals are
  unavailable or lower-bounded rather than estimated.
- Latency reflects one local Windows host and is not portable.
- LeanProofAgent is not a state-of-the-art theorem prover.

## 9. Conclusion

The experiments support three bounded conclusions. First, Lean compiler
feedback materially rescues both malformed statements and invalid proofs, so
first-pass metrics alone understate useful verified coverage. Second, increasing
the tested local model from qwen3:4b to qwen3:8b did not reliably solve the proof
generation bottleneck: the formal verified rates were 5/18 and 6/18, with
regressions and higher 8B latency. Third, deterministic lexical Mathlib
retrieval produced an observed qwen3:4b gain from 5/18 to 7/18 and halved the
proof-stage API-hallucination signal, but it also increased wrong-lemma use,
added cost, and caused three regressions.

These results justify retrieval as an opt-in experimental capability, not as a
universally beneficial v1.0 default. The v1.0 contribution is therefore the
reproducible, kernel-verified experimental pipeline and its documented evidence,
not a claim of superior theorem-proving performance.

## 10. Future Work

Future studies could evaluate type- and head-symbol-aware premise filters,
theorem embeddings, proof-state-aware search, larger replicated benchmarks,
models trained specifically for theorem proving, and stronger human semantic
formalization evaluation. Top-k sensitivity should be studied only after the
main result is replicated. None of these directions is implemented in v1.0.

## Reproducibility artifacts

- [Formal 18-problem report](experiments/qwen3_4b_vs_qwen3_8b_18_problem_benchmark.md)
- [Retrieval ablation report](experiments/mathlib_retrieval_ablation_18.md)
- [Inference stability report](experiments/ollama_inference_stability_3x3.md)
- [`num_predict` comparison](experiments/ollama_num_predict_comparison.md)
- [Mixed calibration](experiments/ollama_num_predict_mixed_calibration.md)
- [Frozen benchmark manifest](experiments/qwen3_4b_vs_qwen3_8b_18_problem_manifest.json)
- [Reproduction commands](EXPERIMENTS.md)

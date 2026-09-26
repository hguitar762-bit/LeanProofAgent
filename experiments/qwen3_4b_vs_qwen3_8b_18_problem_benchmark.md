# qwen3:4b vs qwen3:8b — 18-problem formal benchmark

## 1. Research question

Does increasing the local Ollama model from qwen3:4b to qwen3:8b improve natural-language-to-Lean formalization, compiler-guided proof repair, and final Lean-kernel-verified success under an otherwise frozen pipeline?

This experiment measures verifiability and conservative Lean-based equivalence. It does not treat provability as semantic correctness, and it does not treat failure to prove equivalence as inequivalence.

## 2. Experimental setup

- Date: 2026-09-26 to 2026-09-27 UTC.
- Frozen Git commit: `96a0a53e1ef4e40de9f245130d976abe2038f5e8`.
- Backend/models: local Ollama HTTP (`ollama 0.34.4`), `qwen3:4b` followed serially by `qwen3:8b`.
- Benchmark directory SHA-256: `7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7`.
- Curated benchmark-file SHA-256: `ec0baf9b54a8a06e1c4ae5b3e88821833500ba1bc44b380ed9438e2d0efe408c`.
- Attempts: at most 3 formalizations, 3 proofs, and 2 equivalence proofs per direction.
- Lean timeout/toolchain: 120 seconds; `leanprover/lean4:v4.34.0`.
- Explicit model parameters: none for either run. In particular, no `num_predict`, temperature, or context override was sent.
- The prompts, ProofAgent, Lean verifier, Mathlib environment, benchmark, and evaluation logic were unchanged.
- Official local raw runs: `e/4` and `e/8`. They are intentionally not versioned.

An earlier 4B attempt under a longer artifact root encountered Windows path error 4058 on the final problem and was excluded in full before comparison. Both official runs were then repeated from the shorter root; each contains 18 result records, uses the frozen hash, has a maximum artifact path of 242/250 characters, and contains zero path-4058 errors. No individual problem was rerun or selected by outcome.

### Frozen 18-problem set

| Category | Easy | Medium | Hard |
| --- | --- | --- | --- |
| arithmetic | `arith_add_zero` | `arith_nat_add_assoc` | `arith_even_double` |
| algebra | `algebra_real_mul_comm` | `algebra_square_sum` | `algebra_mul_inv_cancel` |
| logic | `logic_and_comm` | `logic_implication_trans` | `logic_contraposition` |
| inequalities | `ineq_nat_le_add` | `ineq_lt_of_lt_of_le` | `ineq_square_nonnegative` |
| sets | `sets_union_comm` | `sets_diff_membership` | `sets_preimage_inter` |
| functions | `func_id_apply` | `func_injective_comp` | `func_left_inverse_injective` |

## 3. Aggregate results

| Metric | qwen3:4b | qwen3:8b |
| --- | ---: | ---: |
| First-pass formalization success | 10/18 (55.6%) | 10/18 (55.6%) |
| Final formalization success | 16/18 (88.9%) | 17/18 (94.4%) |
| Formalization repair gain | +6 (+33.3 pp) | +7 (+38.9 pp) |
| First-pass proof success | 3/18 (16.7%) | 3/18 (16.7%) |
| Final verified success | 5/18 (27.8%) | 6/18 (33.3%) |
| Proof repair gain | +2 (+11.1 pp) | +3 (+16.7 pp) |
| Semantic equivalent | 2/18 (11.1%) | 5/18 (27.8%) |
| Semantic unknown | 16/18 (88.9%) | 13/18 (72.2%) |
| Semantic not-equivalent | 0/18 | 0/18 |
| Average formalization attempts | 1.67 | 1.56 |
| Average proof attempts | 2.33 | 2.39 |

The 8B model gained one final verified problem, or +5.6 percentage points. This is not a compelling significant improvement on 18 paired cases: it gained three problems (`algebra_real_mul_comm`, `func_id_apply`, `func_injective_comp`) but lost two that 4B verified (`arith_nat_add_assoc`, `ineq_nat_le_add`). Both models retained three shared successes (`algebra_square_sum`, `logic_and_comm`, `sets_diff_membership`). An exact paired sign/McNemar view of the five discordant outcomes gives no evidence of a model-size effect (two-sided p = 1.0).

The small net gain was not isolated to one stage. Final formalization improved by one problem and proof repair rescued one additional problem, while first-pass formalization and proof success were identical.

## 4. Per-category results

`F/P gain` is the number newly rescued by compiler feedback at the formalization/proof stage. Latency and tokens cover the complete pipeline for the three problems in that category.

| Category | 4B first/final F | 8B first/final F | 4B first/final proof | 8B first/final proof | 4B F/P gain | 8B F/P gain | 4B eq | 8B eq | 4B latency/tokens | 8B latency/tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| arithmetic | 2/3 → 3/3 | 3/3 → 3/3 | 1/3 → 1/3 | 0/3 → 0/3 | +1/+0 | +0/+0 | 1/3 | 1/3 | 1,132.0 s / 70,655 | 1,630.2 s / 43,423* |
| algebra | 2/3 → 3/3 | 2/3 → 2/3 | 1/3 → 1/3 | 0/3 → 2/3 | +1/+0 | +0/+2 | 0/3 | 1/3 | 1,271.6 s / 80,750 | 1,055.8 s / 44,247 |
| logic | 2/3 → 3/3 | 3/3 → 3/3 | 0/3 → 1/3 | 0/3 → 1/3 | +1/+1 | +0/+1 | 0/3 | 0/3 | 1,436.2 s / 110,767 | 1,215.3 s / 53,867 |
| inequalities | 3/3 → 3/3 | 1/3 → 3/3 | 0/3 → 1/3 | 0/3 → 0/3 | +0/+1 | +2/+0 | 1/3 | 2/3 | 1,117.9 s / 66,033 | 1,133.7 s / 47,711 |
| sets | 0/3 → 2/3 | 1/3 → 3/3 | 1/3 → 1/3 | 1/3 → 1/3 | +2/+0 | +2/+0 | 0/3 | 1/3 | 1,011.0 s / 67,872 | 1,478.4 s / 70,256 |
| functions | 1/3 → 2/3 | 0/3 → 3/3 | 0/3 → 0/3 | 2/3 → 2/3 | +1/+0 | +3/+0 | 0/3 | 0/3 | 1,114.8 s / 74,102 | 1,421.5 s / 66,362 |

`*` The 8B arithmetic token total excludes one timed-out equivalence request whose provider usage was unavailable.

Arithmetic and inequalities were the hardest categories by pooled final verification (one success each across six model/problem observations). The category pattern was not monotone with model size: 8B improved algebra and functions, but lost the two 4B successes in arithmetic and inequalities.

## 5. Per-problem results

Attempts are formalization/proof. `F` and `P` under repair identify the stage whose compiler-feedback attempt changed failure into stage success. Equivalence `unknown` is not a semantic-incorrect label.

| Problem | Cat. | 4B F/P | 4B verified/EQ | 8B F/P | 8B verified/EQ | Repair changed result | 4B/8B latency | 4B/8B tokens |
| --- | --- | ---: | --- | ---: | --- | --- | ---: | ---: |
| `arith_add_zero` | arithmetic | 1/3 | no/unknown | 1/3 | no/unknown | none | 431.4 s / 955.1 s | 27,837 / 15,459* |
| `arith_nat_add_assoc` | arithmetic | 1/1 | yes/unknown | 1/3 | no/unknown | none | 274.9 s / 421.5 s | 16,302 / 19,975 |
| `arith_even_double` | arithmetic | 2/3 | no/equivalent | 1/3 | no/equivalent | 4B F | 425.7 s / 253.5 s | 26,516 / 7,989 |
| `algebra_real_mul_comm` | algebra | 1/3 | no/unknown | 1/3 | yes/equivalent | 8B P | 360.4 s / 480.5 s | 19,107 / 21,603 |
| `algebra_square_sum` | algebra | 1/1 | yes/unknown | 1/2 | yes/unknown | 8B P | 353.1 s / 439.2 s | 23,902 / 18,100 |
| `algebra_mul_inv_cancel` | algebra | 3/3 | no/unknown | 3/0 | no/unknown | 4B F | 558.1 s / 136.0 s | 37,741 / 4,544 |
| `logic_and_comm` | logic | 1/3 | yes/unknown | 1/2 | yes/unknown | 4B P, 8B P | 418.6 s / 276.2 s | 29,500 / 9,754 |
| `logic_implication_trans` | logic | 1/3 | no/unknown | 1/3 | no/unknown | none | 510.6 s / 456.7 s | 39,100 / 20,614 |
| `logic_contraposition` | logic | 2/3 | no/unknown | 1/3 | no/unknown | 4B F | 507.0 s / 482.4 s | 42,167 / 23,499 |
| `ineq_square_nonnegative` | inequalities | 1/3 | no/unknown | 2/3 | no/unknown | 8B F | 473.1 s / 409.0 s | 28,993 / 16,849 |
| `ineq_lt_of_lt_of_le` | inequalities | 1/3 | no/equivalent | 1/3 | no/equivalent | none | 277.4 s / 355.4 s | 16,799 / 15,601 |
| `ineq_nat_le_add` | inequalities | 1/3 | yes/unknown | 2/3 | no/equivalent | 4B P, 8B F | 367.5 s / 369.3 s | 20,241 / 15,261 |
| `sets_union_comm` | sets | 2/3 | no/unknown | 1/3 | no/equivalent | 4B F | 405.7 s / 299.7 s | 26,255 / 10,593 |
| `sets_diff_membership` | sets | 2/1 | yes/unknown | 2/1 | yes/unknown | 4B F, 8B F | 462.0 s / 518.3 s | 31,707 / 26,878 |
| `sets_preimage_inter` | sets | 3/0 | no/unknown | 2/3 | no/unknown | 8B F | 143.3 s / 660.4 s | 9,910 / 32,785 |
| `func_id_apply` | functions | 3/3 | no/unknown | 2/1 | yes/unknown | 4B F, 8B F | 500.0 s / 298.5 s | 31,682 / 12,931 |
| `func_injective_comp` | functions | 1/3 | no/unknown | 2/1 | yes/unknown | 8B F | 440.8 s / 438.0 s | 29,157 / 19,762 |
| `func_left_inverse_injective` | functions | 3/0 | no/unknown | 3/3 | no/unknown | 8B F | 174.0 s / 685.0 s | 13,263 / 33,669 |

`*` The timed-out 8B equivalence request has no provider token report.

### Final generated statements

| Problem | qwen3:4b generated statement | qwen3:8b generated statement |
| --- | --- | --- |
| `arith_add_zero` | `theorem arith_add_zero (n : ℕ) : n + 0 = n` | `theorem arith_add_zero (n : Nat) : n + 0 = n` |
| `arith_nat_add_assoc` | `theorem arith_nat_add_assoc (a b c : Nat) : (a + b) + c = a + (b + c)` | `theorem arith_nat_add_assoc (a b c : Nat) : (a + b) + c = a + (b + c)` |
| `arith_even_double` | `theorem arith_even_double : ∀ (x : ℤ), Even (2 * x)` | `theorem arith_even_double (n : ℤ) : Even (2 * n)` |
| `algebra_real_mul_comm` | `theorem algebra_real_mul_comm (x y : ℝ) : x * y = y * x` | `theorem algebra_real_mul_comm (x y : ℝ) : x * y = y * x` |
| `algebra_square_sum` | `theorem algebra_square_sum (x y : ℝ) : (x + y) * (x + y) = x * x + 2 * x * y + y * y` | `theorem algebra_square_sum (x y : ℝ) : (x + y) * (x + y) = x * x + 2 * x * y + y * y` |
| `algebra_mul_inv_cancel` | `theorem algebra_mul_inv_cancel (x : ℝ) (h : x ≠ 0) : x * x⁻¹ = 1` | `<none>` |
| `logic_and_comm` | `theorem logic_and_comm (P Q : Prop) : (P ∧ Q) ↔ (Q ∧ P)` | `theorem logic_and_comm (P Q : Prop) : P ∧ Q ↔ Q ∧ P` |
| `logic_implication_trans` | `theorem logic_implication_trans (P Q R : Prop) : ((P → Q) ∧ (Q → R)) → (P → R)` | `theorem logic_implication_trans (P Q R : Prop) : (P → Q) → (Q → R) → (P → R)` |
| `logic_contraposition` | `theorem logic_contraposition (P Q : Prop) : (P → Q) ↔ (¬Q → ¬P)` | `theorem logic_contraposition {P Q : Prop} (h : P → Q) : ¬Q → ¬P` |
| `ineq_square_nonnegative` | `theorem ineq_square_nonnegative : ∀ (r : ℝ), 0 ≤ r * r` | `theorem ineq_square_nonnegative (x : ℝ) : x * x ≥ 0` |
| `ineq_lt_of_lt_of_le` | `theorem ineq_lt_of_lt_of_le (x y z : ℝ) (h1 : x < y) (h2 : y ≤ z) : x < z` | `theorem ineq_lt_of_lt_of_le (x y z : ℝ) : (x < y) → (y ≤ z) → (x < z)` |
| `ineq_nat_le_add` | `theorem ineq_nat_le_add (m n : Nat) : m ≤ m + n` | `theorem ineq_nat_le_add (m n : ℕ) : m ≤ m + n` |
| `sets_union_comm` | `theorem sets_union_comm {α : Type} (A B : Set α) : A ∪ B = B ∪ A` | `theorem sets_union_comm {α : Type} (A B : Set α) : A ∪ B = B ∪ A` |
| `sets_diff_membership` | `theorem sets_diff_membership {α : Type} (A B : Set α) (x : α) (hA : x ∈ A) (hB : ¬(x ∈ B)) : x ∈ (A \ B)` | `theorem sets_diff_membership {α : Type} (x : α) (A B : Set α) : (x ∈ A ∧ x ∉ B) → x ∈ (A \ B)` |
| `sets_preimage_inter` | `<none>` | `theorem sets_preimage_inter {α β} (f : α → β) (A B : Set β) : f ⁻¹' (A ∩ B) = f ⁻¹' A ∩ f ⁻¹' B` |
| `func_id_apply` | `theorem func_id_apply {α : Type} : ∀ (x : α), id x = x` | `theorem func_id_apply {α : Type} (x : α) : id x = x` |
| `func_injective_comp` | `theorem func_injective_comp {α β γ : Type*} (f : α → β) (g : β → γ) (h_f : Function.Injective f) (h_g : Function.Injective g) : Function.Injective (g ∘ f)` | `theorem func_injective_comp {α β γ} (f : α → β) (g : β → γ) (hf : Function.Injective f) (hg : Function.Injective g) : Function.Injective (g ∘ f)` |
| `func_left_inverse_injective` | `<none>` | `theorem func_left_inverse_injective {α β} (f : α → β) (g : β → α) (h : ∀ x, g (f x) = x) : Function.Injective f` |

## 6. Compiler-feedback repair analysis

Formalization feedback rescued six 4B problems and seven 8B problems. The rescued 4B IDs were `arith_even_double`, `algebra_mul_inv_cancel`, `logic_contraposition`, `sets_union_comm`, `sets_diff_membership`, and `func_id_apply`. The rescued 8B IDs were `ineq_square_nonnegative`, `ineq_nat_le_add`, `sets_diff_membership`, `sets_preimage_inter`, `func_id_apply`, `func_injective_comp`, and `func_left_inverse_injective`.

Proof feedback rescued two 4B problems (`logic_and_comm`, `ineq_nat_le_add`) and three 8B problems (`algebra_real_mul_comm`, `algebra_square_sum`, `logic_and_comm`). These are genuine added verified successes after Lean feedback, not merely changed proof text.

Compiler feedback therefore materially improved both stages, but most well-formed statements still failed proof generation: 11 well-formed problems remained unverified for each model.

## 7. Failure analysis

The following diagnostic rates use returned main-stage generations only: 72 for 4B and 71 for 8B. They exclude equivalence generations so that proof/formalization behavior is not obscured. Diagnostics can overlap and are not semantic ground truth.

| Failure signal | qwen3:4b | qwen3:8b | Interpretation |
| --- | ---: | ---: | --- |
| Malformed/safety-rejected output | 16/72 (22.2%) | 10/71 (14.1%) | 8B improved format compliance. |
| Code fence detected | 16/72 (22.2%) | 7/71 (9.9%) | Large 8B reduction, but not elimination. |
| Explanatory text detected | 14/72 (19.4%) | 8/71 (11.3%) | 8B was more concise at the main stages. |
| Proof body inserted into statement | 0/72 | 3/71 (4.2%) | 8B cases: `ineq_square_nonnegative`, `ineq_nat_le_add`, `func_id_apply`. |
| Lean/API hallucination | 20/72 (27.8%) | 23/71 (32.4%) | Unknown identifiers/constants/tactics remained frequent and were slightly worse for 8B. |
| Wrong theorem/lemma application | 2/72 (2.8%) | 4/71 (5.6%) | Signature/type-mismatch evidence; non-exclusive with other proof failures. |
| Tactic misuse | 9/72 (12.5%) | 19/71 (26.8%) | Unknown/failed tactics or unresolved tactic goals. |
| Final formalization failure | 2/18 (11.1%) | 1/18 (5.6%) | 4B: `sets_preimage_inter`, `func_left_inverse_injective`; 8B: `algebra_mul_inv_cancel`. |
| Final proof-search failure | 11/18 (61.1%) | 11/18 (61.1%) | Well-formed statement but no verified proof after three attempts. |
| Backend failure/timeout | 0/18 | 1/18 (5.6%) | One 8B forward-equivalence HTTP timeout on `arith_add_zero`; 1/126 observed requests (0.8%). |
| Semantic equivalence unknown | 16/18 (88.9%) | 13/18 (72.2%) | Unknown is preserved as unknown, not semantic incorrectness. |

No final case was conservatively assigned `missing assumption` or `wrong type/domain`; doing so from equivalence search failure alone would overstate the evidence. The 4B `logic_contraposition` statement changed the reference implication into a biconditional and is a plausible stronger-statement candidate, but its automatic equivalence result remains `unknown` and human semantic review remains unreviewed.

Representative failures include nonexistent `Data.Real.mul_comm`, `Even.two_mul`, and `Real.mul_self_nonneg`; wrong use of `Nat.le_add_left`; invalid or hallucinated tactics; tutorial-style prose/code fences instead of Lean; and an unqualified `inv` that prevented 8B from producing a final algebra statement.

## 8. Efficiency and latency comparison

| Metric | qwen3:4b | qwen3:8b | 8B change |
| --- | ---: | ---: | ---: |
| Main-stage generation median | 30.59 s | 22.16 s | -27.6% |
| Main-stage generation maximum | 76.08 s | 220.23 s | +189.5% |
| Full-pipeline generation median | 37.45 s | 30.39 s | -18.9% |
| Full-pipeline generation maximum | 79.55 s | 220.23 s | +176.9% |
| Total pipeline latency | 7,083.47 s | 7,934.87 s | +851.41 s (+12.0%) |
| Average latency/problem | 393.53 s | 440.83 s | +12.0% |
| Reported input tokens | 37,536 | ≥37,227* | unavailable exact delta |
| Reported output tokens | 432,643 | ≥288,639* | reported lower bound is -33.3% |
| Reported total tokens | 470,179 | ≥325,866* | reported lower bound is -30.7% |

`*` One 8B timeout returned no usage. Its exact input/output/total token totals are unavailable, so the apparent token reduction is not an exact cost comparison. The latency result is complete: 8B had a lower median generation time but a much heavier tail, one timeout, and 12.0% higher end-to-end latency.

## 9. Limitations

- There is one stochastic run per model. The changed success set shows that a larger model is not a deterministic superset of a smaller one.
- Eighteen problems are enough for a baseline, not for a strong statistical claim by category.
- Automatic equivalence proves some positive cases but cannot certify all semantically correct restatements. `unknown` remains unresolved.
- Diagnostic regexes for explanatory text, hallucination, wrong-lemma use, and tactic misuse are artifact-level signals, not human semantic labels.
- Provider token usage is exact only for returned Ollama calls; the one timed-out 8B request makes its aggregate a lower bound.
- The run measures this local hardware/Ollama/toolchain configuration. Latency is not portable to other machines.

## 10. Conclusions

- qwen3:8b did not significantly improve final verified rate: 6/18 versus 5/18, with three gains and two regressions.
- Model-size benefit was small at both stages rather than concentrated: +1 final formalization and +1 proof-repair rescue, with identical first-pass rates.
- Compiler feedback was essential: it rescued 6/7 formalizations and 2/3 verified proofs for 4B/8B respectively.
- 8B reduced main-stage malformed output, code fences, and explanatory text, but did not reduce the dominant Lean proof reliability problem; hallucination and tactic-misuse signals were at least as frequent.
- The performance tradeoff is mixed: lower median generation time and fewer reported tokens, but 12.0% higher total latency, a 2.9× main-stage latency maximum, and one HTTP timeout.
- The single highest-value bottleneck is reliable Lean proof generation after a well-formed statement, especially correct Mathlib API/lemma selection and tactic use. Both models ended with 11 well-formed-but-unverified problems, so improving this bottleneck is more promising than further optimizing formalization syntax alone.

# Mathlib Premise Retrieval Ablation — 18-problem benchmark

## 1. Conclusion

Deterministic local Mathlib premise retrieval improved final Lean-verified success from **5/18 (27.8%)** to **7/18 (38.9%)**, a gain of **2 problems / 11.1 percentage points**. Proof-stage Lean/API hallucination signals fell from **13/42 returned proof attempts (31.0%)** to **6/37 (16.2%)**.

The gain is promising but not sufficient to make this the final v1.0 method. Retrieval added five successes but also caused three verified regressions, increased wrong/misapplied-lemma signals from 2/42 to 9/37, often returned irrelevant type- or domain-specific lemmas, and added material latency and prompt-token cost. It should remain an opt-in candidate method until it has a cheaper index, an applicability filter, regression controls, and replicated runs.

## 2. Frozen comparison

| Condition | Baseline | Retrieval |
| --- | --- | --- |
| Raw run | `e/4` | `e/r3` |
| Git commit | `96a0a53e1ef4e40de9f245130d976abe2038f5e8` | `62f38e38c5da4ae5b40e3dfa165421a8f032df8e` |
| Model/backend | qwen3:4b / Ollama 0.34.4 | same |
| Explicit generation parameters | none | none |
| Formalization / proof / equivalence attempts | 3 / 3 / 2 per direction | same |
| Lean timeout/toolchain | 120 s / `leanprover/lean4:v4.34.0` | same |
| Benchmark SHA-256 | `7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7` | same |
| Premise retrieval | disabled | deterministic lexical, top-k 10 |

The saved formal baseline was reused; it was not cherry-picked or rerun. Tests assert that disabling retrieval preserves the prior proof prompt and artifacts. The formalization prompt, verifier, attempts, benchmark, model, and Ollama defaults were unchanged. The retrieval code commit necessarily differs from the baseline commit, but retrieval is an independent optional layer and Lean remains the only success oracle.

Two earlier implementation pilots, `e/r` and `e/r2`, were stopped and excluded in full after high-frequency lexical terms exceeded the first retrieval timeout. The final implementation bounds work deterministically: it ranks declaration names first, examines at most 128 names, stops after 24 proposition-valued declarations, and then returns at most 10. The complete official run is `e/r3`; no problem was selected or rerun by outcome.

## 3. Retrieval design

`MathlibRetriever` is local, deterministic, and explanation-friendly:

1. Extract identifiers, qualified names, theorem-name compounds, and symbolic aliases from the generated Lean theorem.
2. Ask the exact imported local Lean environment for lexically matching declarations.
3. Rank names by lexical overlap with deterministic name/module tie-breaking.
4. Use Lean `isProp` to retain only proposition-valued declarations and Lean's pretty-printer for their real signatures.
5. Return at most 10 entries containing declaration name, type signature, source module, and score.
6. Add the candidates only to proof-generation prompts and save the exact list as `premises.json` beside each proof run.

There is no vector database, embedding, remote service, benchmark answer table, or change to kernel verification. A theorem that never reaches proof generation has no premise retrieval. An empty lexical result is not padded with invented or arbitrary declarations.

## 4. Aggregate results

| Metric | Baseline | Retrieval | Change |
| --- | ---: | ---: | ---: |
| First-pass formalization | 10/18 (55.6%) | 10/18 (55.6%) | 0 |
| Final formalization | 16/18 (88.9%) | 16/18 (88.9%) | 0 |
| First-pass proof success | 3/18 (16.7%) | 3/18 (16.7%) | 0 |
| Final verified success | 5/18 (27.8%) | 7/18 (38.9%) | **+2 / +11.1 pp** |
| Proof repair gain | +2 / +11.1 pp | +4 / +22.2 pp | **+2 / +11.1 pp** |
| Total returned proof attempts | 42 | 37 | -5 |
| Average proof attempts/problem | 2.33 | 2.06 | -0.28 |
| End-to-end latency | 7,083.47 s | 8,309.55 s | **+1,226.08 s / +17.3%** |
| Average latency/problem | 393.53 s | 461.64 s | +68.12 s |
| Reported full-pipeline input tokens | 37,536 | ≥56,437 | **≥+18,901 / ≥+50.4%** |
| Reported full-pipeline output tokens | 432,643 | ≥385,355 | lower bound; exact delta unavailable |
| Reported full-pipeline total tokens | 470,179 | ≥441,792 | lower bound; exact delta unavailable |

The retrieval arm had two provider calls with unavailable usage: one failed equivalence generation on `func_id_apply` (`eval_count=40960`) and one proof-generation response without usable text on `func_left_inverse_injective` (`eval_count=5479`). Therefore all retrieval full-pipeline token totals are lower bounds; the apparent lower reported total is not evidence of a token saving.

For returned proof attempts only, reported input tokens rose from 13,187 over 42 attempts to 32,257 over 37 attempts: **+144.6% total and +177.7% per returned attempt**. Output tokens per returned proof attempt fell 4.9%, while total tokens per returned attempt rose 10.9%. This isolates the expected premise-context prompt cost better than the full-pipeline total.

On 14 retrieval calls without a missing provider-duration event, the residual wall time after subtracting recorded LLM-generation and Lean-verification durations was 764.79 s total, mean 54.63 s and median 50.84 s per call. This is an approximate retrieval overhead, not a directly instrumented timer. The two excluded residuals also contain unrecorded failed-provider latency.

## 5. Successes, regressions, and repair

### Newly verified with retrieval

| Problem | Attempt | Verified proof | Retrieved declaration used |
| --- | ---: | --- | --- |
| `arith_add_zero` | 2 | `by exact Nat.add_zero n` | `Nat.add_zero` |
| `algebra_real_mul_comm` | 2 | `by { apply mul_comm }` | `mul_comm` |
| `algebra_mul_inv_cancel` | 1 | `by apply Field.mul_inv_cancel` | `Field.mul_inv_cancel` |
| `ineq_lt_of_lt_of_le` | 1 | `by exact lt_of_lt_of_le h1 h2` | `lt_of_lt_of_le` |
| `func_injective_comp` | 1 | `by apply Function.Injective.comp hg hf` | `Function.Injective.comp` |

Every retrieval-arm success, including the two shared successes `arith_nat_add_assoc` and `ineq_nat_le_add`, used an exact retrieved declaration name in its final proof: **7/7 successful proofs**. This is strong usage evidence, but one stochastic paired run does not by itself establish that retrieval caused every success.

### Verified regressions

| Problem | Baseline | Retrieval failure pattern |
| --- | --- | --- |
| `algebra_square_sum` | first-pass `by ring` | irrelevant `IsSquare.*` candidates; repeated failed `rw [mul_add, ...]` |
| `logic_and_comm` | repaired with `and_comm` | retrieved `and_comm`, then misapplied it as `and_comm P Q` |
| `sets_diff_membership` | first-pass constructor proof `⟨hA, hB⟩` | over-focused on retrieved `Set.mem_diff*` declarations and misapplied all three attempts |

The five gains and three regressions give the net +2 result. Aggregate first-pass success stayed at 3/18, while proof-repair gain increased from +2 to +4. Thus the **net verified-rate improvement comes from compiler-feedback repair**, even though three of the five newly successful individual problems passed on their first retrieval proof attempt.

## 6. Failure-signal ablation

The diagnostic unit below is a returned proof attempt, excluding formalization and equivalence. Signals can overlap and are not semantic ground truth.

| Proof-stage signal | Baseline | Retrieval | Change |
| --- | ---: | ---: | ---: |
| Lean/API hallucination (`unknownIdentifier`, unknown constant/tactic) | 13/42 (31.0%) | 6/37 (16.2%) | **-14.7 pp** |
| Wrong/incompatible lemma or theorem application | 2/42 (4.8%) | 9/37 (24.3%) | **+19.6 pp** |
| Tactic misuse/failure or unresolved tactic goal | 9/42 (21.4%) | 6/37 (16.2%) | -5.2 pp |

Across formalization plus proof generations, the broader hallucination signal fell from 20/72 (27.8%) to 14/66 (21.2%). The proof-only view is more causally relevant because retrieval is not used during formalization.

Retrieval therefore did reduce invented Mathlib/API names, but it did not eliminate proof unreliability. A substantial part of the error mass shifted from nonexistent declarations to real declarations used with the wrong implicit/explicit arguments or incompatible types. `logic_and_comm`, `ineq_square_nonnegative`, `sets_union_comm`, and `sets_diff_membership` are representative.

## 7. Category analysis

| Category | Baseline verified | Retrieval verified | Net | Retrieval first/final proof | Retrieval repair gain |
| --- | ---: | ---: | ---: | ---: | ---: |
| arithmetic | 1/3 | 2/3 | +1 | 0/3 → 2/3 | +2 |
| algebra | 1/3 | 2/3 | +1 | 1/3 → 2/3 | +1 |
| logic | 1/3 | 0/3 | -1 | 0/3 → 0/3 | 0 |
| inequalities | 1/3 | 2/3 | +1 | 1/3 → 2/3 | +1 |
| sets | 1/3 | 0/3 | -1 | 0/3 → 0/3 | 0 |
| functions | 0/3 | 1/3 | +1 | 1/3 → 1/3 | 0 |

Arithmetic, algebra, inequalities, and functions tie for the largest gain at +1 verified problem each. Logic and sets regress by one each. With only three problems per category, these are descriptive rather than stable category estimates.

## 8. Retrieved top-k premises

Top-k is a maximum. `arith_even_double` and `sets_preimage_inter` failed formalization before retrieval; `logic_contraposition` produced no matching proposition-valued declaration and saved an empty list.

| Problem | Retrieved premises in rank order | Successful proof used |
| --- | --- | --- |
| `arith_add_zero` | `Nat.add_zero`; `ofAdd_zero`; `add_zero`; `Int.add_zero`; `Rat.add_zero`; `Num.add_zero`; `Int8.add_zero`; `ZNum.add_zero`; `ISize.add_zero`; `Int16.add_zero` | `Nat.add_zero` |
| `arith_nat_add_assoc` | `Nat.add_assoc._f`; `Nat.add_assoc`; `vadd_add_assoc`; `Vector.add_assoc`; `add_assoc`; `Int.add_assoc`; `Rat.add_assoc`; `Int8.add_assoc`; `ISize.add_assoc`; `Int16.add_assoc` | `Nat.add_assoc` |
| `arith_even_double` | not invoked: no final theorem | — |
| `algebra_real_mul_comm` | `EReal.mul_comm`; `neg_mul_comm`; `ppow_mul_comm`; `mul_smul_comm`; `mul_comm`; `Int.mul_comm`; `Nat.mul_comm`; `Rat.mul_comm`; `Fin.mul_comm`; `Int8.mul_comm` | `mul_comm` |
| `algebra_square_sum` | `IsSquare.isSumSq`; `NNReal.isSquare`; `IsSquare.sq`; `IsSquare.one`; `Complex.isSquare`; `IsSquare.zero`; `IsSquare.inv`; `isSquare_inv`; `IsSquare.eq_1`; `IsSquare.pow` | — |
| `algebra_mul_inv_cancel` | `ENNReal.mul_inv_cancel`; `CauSeq.mul_inv_cancel`; `mul_inv_cancel`; `Rat.mul_inv_cancel`; `Complex.mul_inv_cancel`; `mul_inv_cancel_left`; `mul_inv_cancel_comm`; `Field.mul_inv_cancel`; `mul_inv_cancel_right`; `IsUnit.mul_inv_cancel` | `Field.mul_inv_cancel` |
| `logic_and_comm` | `and_comm`; `Nat.and_comm`; `Int8.and_comm`; `Bool.and_comm`; `ISize.and_comm`; `Int16.and_comm`; `Int32.and_comm`; `Int64.and_comm`; `UInt8.and_comm`; `USize.and_comm` | — |
| `logic_implication_trans` | `Trans.simple.eq_1`; `Equiv.simpleGraph_trans`; `Trans.trans.congr_simp`; `Std.Do.PredTrans.mk.congr_simp`; `Affine.Simplex.reindex_trans`; `LinearEquiv.trans.congr_simp`; `Std.Do.SPred.imp_trans`; `SimpleGraph.Reachable.trans`; `SimpleGraph.IsContained.trans`; `Matrix.isSimplyLaced_transpose` | — |
| `logic_contraposition` | none | — |
| `ineq_square_nonnegative` | `IsRealClosed.nonneg_iff_isSquare`; `IsSquare.sq`; `IsSquare.nonneg`; `IsSquare.of_nonneg`; `Int.isSquare_iff_nonneg_even_factorization` | — |
| `ineq_lt_of_lt_of_le` | `List.lt_of_le_of_lt`; `Array.lt_of_le_of_lt`; `Std.lt_of_le_of_lt`; `Std.lt_of_lt_of_le`; `lt_of_le_of_lt`; `lt_of_lt_of_le`; `Int.lt_of_le_of_lt`; `Int.lt_of_lt_of_le`; `Nat.lt_of_le_of_lt`; `Nat.lt_of_lt_of_le` | `lt_of_lt_of_le` |
| `ineq_nat_le_add` | `Nat.add_le_add`; `Fin.addNat_le_addNat_iff`; `Cardinal.add_nat_le_add_nat_iff`; `Fin.addNat_le_addNat_iff._simp_1`; `Fin.addNat_le_addNat_iff._gcongr_1`; `Cardinal.add_nat_le_add_nat_iff._simp_1`; `le_add_self`; `le_add_left`; `le_add_right`; `add_le_add` | `Nat.add_le_add` |
| `sets_union_comm` | `Set.union_comm`; `Set.iUnion_comm`; `Set.union_union_union_comm`; `Finset.union_comm`; `Multiset.union_comm`; `Finset.disjUnion_comm`; `Finset.insert_union_comm`; `Finset.union_union_union_comm`; `Finmap.union_comm_of_disjoint`; `AList.union_comm_of_disjoint` | — |
| `sets_diff_membership` | `Set.mem_diff`; `Set.mem_of_mem_diff`; `Set.mem_diff_of_mem`; `Set.notMem_diff_of_mem`; `Set.notMem_of_mem_diff`; `Set.mem_diff_singleton`; `Std.TreeSet.mem_diff_iff`; `Std.HashSet.mem_diff_iff`; `Filter.diff_mem`; `List.mem_diff_of_mem` | — |
| `sets_preimage_inter` | not invoked: no final theorem | — |
| `func_id_apply` | `Path.id_apply`; `PFun.id_apply`; `BotHom.id_apply`; `InfHom.id_apply`; `SupHom.id_apply`; `TopHom.id_apply`; `AddHom.id_apply`; `MulHom.id_apply`; `OneHom.id_apply`; `RelHom.id_apply` | — |
| `func_injective_comp` | `Function.Injective.comp`; `Function.Injective.of_comp`; `Function.injective_comp_left_iff`; `Function.injective_comp_right_iff_surjective`; `Function.injective_id`; `Function.Injective.nodup`; `Function.Injective.ne`; `Function.Injective.eq_1`; `Function.Injective.injOn`; `Function.Injective.iterate` | `Function.Injective.comp` |
| `func_left_inverse_injective` | `Function.injective_id`; `Function.Injective.comp`; `Function.Injective.of_comp`; `Function.Injective2.left`; `Function.Injective.nodup`; `Function.Injective.ne`; `Function.Injective.eq_1`; `Function.Injective.injOn`; `Function.Injective.iterate`; `Function.Injective.eq_iff` | — |

Manual applicability review found clearly irrelevant candidates in every nonempty top-k list. Examples include integer and bit-vector `add_zero` lemmas for a natural-number goal, `IsSquare.*` facts for a polynomial expansion, graph/category `trans` lemmas for plain implication, and homomorphism-specific `id_apply` lemmas for the polymorphic identity function. Retrieval relevance is therefore the main remaining quality problem; the successful exact-name usage does not mean the entire top-k context was clean.

## 9. Answers to the ablation questions

1. **Did retrieval improve verified rate?** Yes: 5/18 to 7/18, +11.1 pp, with five gains and three regressions.
2. **Did it reduce Lean/API hallucination?** Yes at proof stage: 31.0% to 16.2% of returned proof attempts. However, wrong/incompatible use of real lemmas rose sharply.
3. **Which categories benefited most?** Arithmetic, algebra, inequalities, and functions each gained one; logic and sets each lost one.
4. **Were there baseline regressions?** Yes: `algebra_square_sum`, `logic_and_comm`, and `sets_diff_membership`.
5. **Did the gain come from first proof or repair?** Aggregate first-pass success was unchanged at 3/18. The net +2 final gain is reflected entirely in repair gain increasing from +2 to +4.
6. **What was the latency/token cost?** End-to-end latency rose 17.3%. Clean-call residuals indicate roughly 50.84 s median retrieval overhead. Returned proof-attempt input tokens rose 177.7% per attempt and total tokens rose 10.9% per attempt. Full retrieval token totals are lower bounds because two provider failures returned no usage.

## 10. v1.0 decision and future work

This is **not yet sufficient as the final v1.0 method**. It is a credible opt-in improvement and validates the research direction, but the paired sample is small and stochastic, regressions are substantial, real-but-misapplied lemmas increased, irrelevant premises are common, and per-query Lean startup is expensive.

The next work should be narrowly focused: cache a local declaration index, add deterministic type/head-symbol compatibility filtering, and replicate the same frozen ablation to test whether the +2 net gain survives. Top-k sensitivity may be studied later because the fixed top-k 10 run showed a real signal; no top-k tuning was performed in this round.

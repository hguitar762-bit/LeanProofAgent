# Real-model Experiments

## Research question

Does compiler-guided feedback improve verifiable mathematical reasoning?

## Setup

The planned baseline uses all 36 curated autoformalization problems and the
real pipeline:

```text
natural language → LLM statement → Lean elaboration → statement repair
→ LLM proof → Lean verification → proof repair → semantic equivalence check
```

The runner records the UTC timestamp, exact Git commit, backend and model,
attempt limits, Lean toolchain and timeout, benchmark SHA-256 and problem IDs,
explicit model parameters, complete per-problem outcomes, latency, and
provider-reported token usage when available.

Status on 2026-09-21: **not run**. `OPENAI_API_KEY` was absent from the process
environment, so no real API smoke test or 36-problem baseline was executed. No
mock numbers are reported as experimental evidence.

### Reproduction commands

Set the key only in the current PowerShell process without writing it to a file:

```powershell
$env:OPENAI_API_KEY = Read-Host "OPENAI_API_KEY" -MaskInput
$env:OPENAI_MODEL = "gpt-5.5"
```

Run a five-problem real-API smoke test first:

```powershell
.venv\Scripts\python.exe examples\run_real_model_experiment.py `
  --name real_model_smoke_001 `
  --model $env:OPENAI_MODEL `
  --ids arith_add_zero algebra_mul_inv_cancel logic_implication_trans ineq_square_nonnegative sets_preimage_inter
```

Inspect `experiments/real_model_smoke_001/config.json`, `summary.md`,
`failures.md`, and the ignored `artifacts/` tree. Only after API, Lean,
artifacts, and metrics are confirmed should the full run start:

```powershell
.venv\Scripts\python.exe examples\run_real_model_experiment.py `
  --name real_model_baseline_001 `
  --model $env:OPENAI_MODEL
```

The defaults are three formalization attempts, three proof attempts, two
equivalence attempts per direction, and a 120-second Lean timeout. The current
OpenAI adapter sends only `model`, `instructions`, and `input`; temperature,
reasoning effort, and output limits therefore use provider defaults and are
recorded as such rather than guessed.

### Local Ollama alternative

Ollama can run the identical experiment pipeline without an OpenAI credential.
Start the local service and pull a caller-selected model:

```powershell
ollama serve
ollama pull <model>
$env:OLLAMA_MODEL = "<model>"
```

Run a one-problem smoke test before a full local baseline:

```powershell
.venv\Scripts\python.exe examples\run_real_model_experiment.py `
  --backend ollama `
  --model $env:OLLAMA_MODEL `
  --name local_smoke_001 `
  --ids arith_add_zero

.venv\Scripts\python.exe examples\run_real_model_experiment.py `
  --backend ollama `
  --model $env:OLLAMA_MODEL `
  --name local_baseline_001
```

The runner checks that Ollama is reachable and the model is installed before
creating the experiment. Its config records the `ollama-http` backend and model.
Ollama `prompt_eval_count` and `eval_count` values are preserved when returned;
missing usage remains unavailable. Ollama changes only model transport, not the
formalization, repair, proof, Lean verification, or equivalence standards.

## Metrics

- First-pass and final formalization success rates use all selected benchmark
  problems as the denominator.
- Formalization repair gain is the number of additional well-formed statements
  after compiler feedback and the corresponding percentage-point increase.
- First-pass and final proof success rates also use all selected problems as the
  denominator; a problem without a well-formed statement cannot pass proof.
- Proof repair gain is the number of additional Lean-verified proofs after
  compiler feedback and the corresponding percentage-point increase.
- End-to-end verified rate equals final proof success rate.
- Semantic equivalence, unknown, and `not_equivalent` rates preserve the
  checker's three-way result. Failed proof search remains `unknown`.
- Average statement/proof attempts, per-problem and aggregate latency, and
  provider-reported input/output/total tokens are recorded without imputation.

## Results

No real-model results are available because the required API credential was not
present. No percentage, repair gain, or model comparison can be reported yet.

## Failure analysis

No empirical failure distribution is available. Completed runs generate
`failures.md` grouped by recorded categories such as Lean elaboration failure,
proof verification failure, semantic equivalence unknown, provider failure, and
human-reviewed semantic categories. Automatic output never assigns semantic
correctness.

## Limitations

Without a completed real-API run, the instrumentation is tested but the research
question is unanswered. A single model/configuration and a 36-problem benchmark
will also provide limited statistical power. Lean provability and logical
equivalence remain auxiliary signals rather than natural-language semantic
ground truth.

## Next hypothesis

If compiler feedback is useful, most measurable gain should occur on Lean
elaboration and local proof-syntax/type failures, while missing assumptions,
wrong domains, and other semantic mismatches should remain unresolved or
`unknown`. This must be tested with the real baseline before drawing a
conclusion.

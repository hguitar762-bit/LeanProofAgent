# Reproducing the Local Ollama Experiments

This document gives the commands for the formal 18-problem benchmark and the
Mathlib retrieval ablation. Published results are summarized in
[REPORT.md](REPORT.md); this file is concerned with execution and controls.

## Environment

The formal runs used:

- Lean/Mathlib `v4.34.0` from `lean-toolchain` and `lake-manifest.json`;
- Ollama 0.34.4 with `qwen3:4b` and `qwen3:8b`;
- no explicit temperature, context-length, or `num_predict` override;
- three formalization attempts, three proof attempts, and two equivalence
  attempts per direction;
- a 120-second Lean timeout;
- benchmark directory SHA-256
  `7ac68ea1e8fbad111763bf1b0b508253d91aa7a50bfccbc2879157ed7dc7f3d7`.

The exact frozen problem list is versioned in
`experiments/qwen3_4b_vs_qwen3_8b_18_problem_manifest.json`.

## Setup and checks

```powershell
ollama pull qwen3:4b
ollama pull qwen3:8b
lake update
lake exe cache get
python -m pip install -e ".[dev]"
lake build
pytest
python examples/mock_autoformalization_demo.py
```

Create the exact 18-ID list from the manifest:

```powershell
$manifest = Get-Content `
  experiments/qwen3_4b_vs_qwen3_8b_18_problem_manifest.json | `
  ConvertFrom-Json
$ids = @($manifest.problems.id)
```

Use a short experiment root on Windows to stay below legacy path limits.

## qwen3:4b baseline

```powershell
python examples/run_real_model_experiment.py `
  --name reproduce-4b-baseline `
  --experiments-root e `
  --backend ollama `
  --model qwen3:4b `
  --ids $ids `
  --max-formalization-attempts 3 `
  --max-proof-attempts 3 `
  --max-equivalence-attempts 2 `
  --timeout 120
```

## qwen3:8b comparison

Run the same command with a new name and `--model qwen3:8b`. Do not add a
generation override if comparing with the published Ollama-default condition.

## Mathlib retrieval ablation

The published ablation fixed top-k at 10 before the run. It did not tune top-k
by outcome.

```powershell
python examples/run_real_model_experiment.py `
  --name reproduce-4b-retrieval `
  --experiments-root e `
  --backend ollama `
  --model qwen3:4b `
  --ids $ids `
  --max-formalization-attempts 3 `
  --max-proof-attempts 3 `
  --max-equivalence-attempts 2 `
  --timeout 120 `
  --premise-retrieval `
  --premise-top-k 10
```

Each problem that reaches proof generation writes `premises.json`. Retrieval is
disabled unless `--premise-retrieval` is present; tests assert that the disabled
path preserves the baseline proof prompt and artifact behavior.

## Saved outputs and metric rules

Every experiment directory contains `config.json`, `results.json`, `summary.md`,
`failures.md`, and a raw `artifacts/` tree. Generated run directories are local
and ignored by Git. Versioned reports and the frozen manifest live directly
under `experiments/`.

- Final verified success requires a real Lean exit code of zero.
- Repair gain counts new stage successes after the first attempt.
- Failed equivalence search remains `unknown`, never `not_equivalent`.
- Missing provider usage remains unavailable; aggregates containing such calls
  are lower bounds.
- Malformed output, API hallucination, wrong-lemma, and tactic-misuse rates are
  operational artifact-level signals and may overlap.

## Versioned reports

- `qwen3_4b_vs_qwen3_8b_5_problem.md`: initial controlled comparison.
- `ollama_inference_stability_3x3.md`: repeated hard-subset stability study.
- `ollama_num_predict_comparison.md`: hard-subset output-cap experiment.
- `ollama_num_predict_mixed_calibration.md`: mixed-difficulty calibration and
  easy-case regression that led to keeping Ollama defaults.
- `qwen3_4b_vs_qwen3_8b_18_problem_benchmark.md`: formal model comparison.
- `mathlib_retrieval_ablation_18.md`: baseline versus lexical Mathlib retrieval.

The reports retain negative and failed results; mock demos are never presented
as model-performance evidence.

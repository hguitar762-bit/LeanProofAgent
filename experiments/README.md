# Experiment artifacts

Each real-model run uses a unique directory such as
`real_model_smoke_001/` or `real_model_baseline_001/` containing:

- `config.json`: timestamp, exact Git commit, benchmark hash and IDs, backend,
  model, attempt limits, Lean timeout, and explicit model-parameter settings.
- `results.json`: complete aggregate and per-problem results.
- `summary.md`: compact metrics and repair gains.
- `failures.md`: categorized representative failures with Lean feedback.
- `artifacts/`: raw statement, proof, equivalence, and compiler attempts.

Raw `artifacts/` trees are ignored by Git. Review the four compact top-level
files for secrets and size before committing a completed experiment. The runner
never reads `.env` files and never writes `OPENAI_API_KEY`.

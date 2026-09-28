# Experiment artifacts

Each OpenAI or local Ollama real-model run uses a unique directory such as
`real_model_smoke_001/` or `real_model_baseline_001/` containing:

- `config.json`: timestamp, exact Git commit, benchmark hash and IDs, backend,
  model, attempt limits, Lean timeout, and explicit model-parameter settings.
- `results.json`: complete aggregate and per-problem results.
- `summary.md`: compact metrics and repair gains.
- `failures.md`: categorized representative failures with Lean feedback.
- `artifacts/`: raw statement, proof, equivalence, and compiler attempts.

Generated experiment directories, including their raw `artifacts/` trees, are
ignored by Git. Preserve them locally for audit, then promote only reviewed,
secret-free aggregate reports or frozen manifests directly into `experiments/`
for version control. The runner never reads `.env` files and never writes
`OPENAI_API_KEY` or other credentials.

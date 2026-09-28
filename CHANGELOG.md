# Changelog

All notable project milestones from the initial prototype to the first
reproducible research release are summarized here.

## [1.0.0] - 2026-09-28

### Added

- Deterministic local Mathlib premise retrieval with verified declaration names,
  type signatures, source modules, top-k control, and saved premise artifacts.
- Formal 18-problem qwen3:4b versus qwen3:8b benchmark and retrieval ablation.
- Research report, reproducibility guide, concise project homepage, and a single
  offline end-to-end repair demo.

### Changed

- Consolidated the project as a reproducible research system and documented the
  Lean kernel and natural-language semantic trust boundaries.
- Kept premise retrieval opt-in after the ablation showed both gains and
  regressions.

## [0.6.0] - 2026-09-21

- Added conservative Lean-verified bidirectional implication checking.
- Preserved failed equivalence proof search as `unknown` and kept human semantic
  review independent.

## [0.5.0] - 2026-09-21

- Added the local Ollama backend and reproducible real-model experiment runner.
- Added output-token controls and explicit reporting of truncation and missing
  provider usage.

## [0.4.0] - 2026-09-20

- Added natural-language autoformalization, Lean-guided statement repair, and
  guarded statement validation with `autoImplicit` disabled and a `Prop` check.

## [0.3.0] - 2026-09-20

- Added saved-evaluation comparison, coverage changes, and regression analysis.

## [0.2.0] - 2026-09-20

- Added theorem benchmark evaluation, aggregate metrics, and persisted JSON and
  Markdown artifacts.

## [0.1.0] - 2026-09-20

- Initial Lean-kernel-verified proof loop with bounded compiler-feedback repair,
  artifact persistence, CLI support, and offline real-Lean demo.

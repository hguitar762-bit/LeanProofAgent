# LeanProofAgent

LeanProofAgent is a small, executable framework for **kernel-checked mathematical
reasoning**. An LLM proposes a Lean 4 proof; Lean checks it against Mathlib. If
Lean rejects the proof, the agent sends the exact compiler feedback back to the
LLM and tries again, up to a fixed limit. Version 0.6 adds conservative,
Lean-verified bidirectional implication checking between generated and reference
statements while keeping human-reviewed semantic correctness separate.

```text
natural-language proposition
       │
       ▼
  LLM formalizer ──► theorem statement ──► Lean elaboration check
       ▲                                          │
       └──────────── exact Lean error ◄───────────┘
                                                  │ valid statement
                                                  ▼
theorem statement
       │
       ▼
  LLM backend ──► candidate proof ──► lake env lean
       ▲                                  │
       │                                  ├─ success ─► verified proof
       └──── previous proof + error ◄─────└─ failure
```

The Python process never declares a proof successful on its own. Success means
that the generated `.lean` file was accepted by a real `lake env lean` process
with exit code 0. Each attempted proof, command result, stdout, stderr, duration,
and the final summary are saved as run artifacts.

## Scope

Included:

- Lean 4.34.0 and the matching Mathlib 4.34.0 release, pinned in the repository.
- A model-neutral `LLMBackend` protocol.
- An OpenAI backend using the official Python SDK and Responses API.
- Compiler-guided retry with a configurable maximum attempt count.
- Rejection of `sorry`, `admit`, `axiom`, and theorem declarations that already
  contain a proof body.
- A CLI, theorem-only benchmarks, an offline mock repair demo, pytest coverage,
  and GitHub Actions CI.
- A failure-isolated evaluation runner with JSON results, Markdown summaries,
  latency/attempt metrics, and optional provider-reported token usage.
- Saved-evaluation comparison with aggregate deltas, benchmark coverage changes,
  and per-theorem regression analysis.
- Natural-language-to-Lean theorem generation with bounded, compiler-guided
  statement repair before the existing proof loop begins.
- A 36-problem, human-reviewed natural-language/reference-statement benchmark
  covering arithmetic, algebra, logic, inequalities, sets, and functions.
- Autoformalization evaluation with statement elaboration, repair, proof,
  conservative comparison, failure-category, JSON, Markdown, and independent
  semantic-review artifacts.
- A standalone semantic-equivalence checker that turns theorem declarations
  into closed propositions and checks reference → generated and generated →
  reference through the existing kernel-verified proof loop.
- Three small natural-language benchmarks covering arithmetic, logic, and
  algebra, plus an offline end-to-end autoformalization demo.
- Twenty theorem-only benchmarks across arithmetic, algebra, logic, lists,
  sets, and inequalities.

Deliberately not included: a web UI, database, RAG, multi-agent orchestration,
fine-tuning, reinforcement learning, parallel proof search, or
benchmark-specific proof lookup.

## Architecture

```text
src/lean_proof_agent/
├── agent.py            bounded generate → verify → repair loop
├── verifier.py         subprocess boundary for `lake env lean`
├── llm.py              backend protocol and output normalization
├── openai_backend.py   OpenAI Responses API adapter
├── offline_backend.py  generic offline tactic for plumbing checks only
├── prompts.py          initial and compiler-repair prompts
├── artifacts.py        per-attempt Lean and JSON records
├── models.py           typed domain objects and safety checks
├── benchmarks.py       theorem-only benchmark loader
├── evaluation.py       sequential runner, metrics, JSON, and Markdown
├── comparison.py       saved-run deltas and per-theorem regressions
├── formalization.py    text → theorem generation and Lean-guided repair
├── formalization_benchmarks.py  curated pair schema and loader
├── formalization_evaluation.py  statement/proof/semantic evaluation reports
├── semantic_equivalence.py  conservative bidirectional implication checker
├── text_benchmarks.py  natural-language benchmark loader
└── cli.py              `lean-proof` command

benchmarks/             statements and metadata, never solutions
benchmarks/formalization/  reviewed natural-language/reference pairs
text_benchmarks/        natural-language propositions, never formalizations
examples/               offline mock-LLM repair demo
tests/                  unit tests plus real-Lean integration tests
```

The small backend protocol is intentional: another provider or a local model
only needs to implement:

```python
class LLMBackend(Protocol):
    def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> str | GenerationResult: ...
```

Returning a plain string remains supported. `GenerationResult` adds optional
provider-reported token counts without coupling the proof loop to OpenAI.

## Prerequisites

- Python 3.11 or newer.
- Git.
- [Elan](https://github.com/leanprover/elan), the Lean toolchain manager.

Install Elan on Windows with WinGet:

```powershell
winget install --exact --id Lean.Elan
elan-init -y --default-toolchain none
```

On Linux/macOS, follow the Elan instructions linked above. Opening a fresh
terminal after installation ensures `~/.elan/bin` is on `PATH`.

## Install

Clone the repository, then from its root run:

```bash
# Installs the Lean version named by lean-toolchain and pins Mathlib in
# lake-manifest.json.
lake update

# Downloads Mathlib's precompiled cache instead of rebuilding it all locally.
lake exe cache get

# Install the Python package, OpenAI adapter, and test tools.
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[openai,dev]"
```

Check both halves of the installation:

```bash
lake build
pytest
```

## Configure OpenAI

Set the key in the process environment. The application does not accept an API
key argument and does not load `.env` files.

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-5.5"  # optional; --model overrides it
```

```bash
# Linux/macOS
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-5.5"  # optional
```

The adapter follows the official OpenAI Python quickstart: instantiate
`OpenAI()` without embedding a key, call `client.responses.create(...)`, and
read `response.output_text`. See the
[official OpenAI API quickstart](https://developers.openai.com/api/docs/quickstart).
Model access varies by account, so set `OPENAI_MODEL` or pass `--model` when the
default is unavailable.

## Use the CLI

List bundled theorem statements:

```bash
lean-proof list-benchmarks
```

Run a benchmark through OpenAI and allow three attempts:

```bash
lean-proof solve --benchmark add_zero --max-attempts 3
```

Run an inline theorem:

```bash
lean-proof solve \
  --name square_nonnegative \
  --theorem "theorem square_nonnegative (x : ℝ) : 0 ≤ x ^ 2" \
  --model gpt-5.5
```

Or provide a theorem-only JSON file:

```json
{
  "name": "my_theorem",
  "description": "Optional human-readable text.",
  "imports": ["Mathlib"],
  "theorem": "theorem my_theorem (n : ℕ) : n = n"
}
```

```bash
lean-proof solve --problem path/to/problem.json --artifacts-dir runs
```

The declaration must not include `:=` or a proof. That prevents a benchmark
file from smuggling in its own answer.

## Autoformalization

Formalize a natural-language proposition and then prove the generated theorem:

```bash
lean-proof solve-text "For every natural number n, n + 0 = n"
```

Useful controls mirror the existing proof command while keeping the two retry
budgets separate:

```bash
lean-proof solve-text \
  "For every natural number n, n + 0 = n" \
  --name natural_add_zero \
  --max-formalization-attempts 3 \
  --max-attempts 3 \
  --model gpt-5.5
```

Bundled natural-language prompts can be inspected and run by name:

```bash
lean-proof list-text-benchmarks
lean-proof solve-text --benchmark arithmetic_add_zero
```

The formalization model must return exactly one `theorem` declaration without
a proof body. Responses containing `:=`, `sorry`, `admit`, `axiom`, extra code
fences, or a `where` block are rejected before Lean runs. For structurally safe
responses, Lean elaborates an internal temporary `axiom` declaration with
`autoImplicit` disabled. A small Lean metaprogram also confirms that the
declaration's type is a proposition. Together these checks cover syntax,
referenced names, types, and theorem shape without pretending the proposition
has been proved. The temporary axiom is never passed to the proof stage or
counted as success. If elaboration fails, its exact feedback is returned to the
model for a bounded repair attempt.

Once a statement elaborates, the unchanged `ProofAgent` receives that theorem
and success still requires a generated proof accepted by `lake env lean` with
exit code 0.

**Semantic boundary:** Lean verifies that the final proof proves the generated
Lean theorem. It does not automatically establish that the generated theorem
faithfully captures every meaning, assumption, or ambiguity in the original
natural-language proposition. Autoformalization therefore needs human review
when semantic fidelity matters.

## Evaluation

Evaluate all bundled benchmarks with OpenAI:

```bash
lean-proof evaluate --benchmark benchmarks --max-attempts 3
```

`--benchmark` accepts either a theorem JSON file or a directory and can be
repeated. Omitting it evaluates the bundled suite. Results are sequential: each
theorem gets its own `ProofAgent` run, and a provider exception or failed proof
is recorded without aborting later theorems.

When no API key is available, validate the complete evaluation and real-Lean
pipeline with the offline backend:

```bash
lean-proof evaluate \
  --benchmark benchmarks/add_zero.json \
  --backend mock \
  --max-attempts 1
```

The mock backend always emits the same generic `simp` tactic. It is useful for
plumbing tests, is not an LLM performance measurement, and contains no
benchmark-specific solutions.

Each evaluation writes:

```text
evaluations/20260920T120000Z-evaluation-a1b2c3d4/
├── evaluation.json       machine-readable aggregate and per-theorem results
├── summary.md            concise metrics and status table
└── problems/             normal ProofAgent artifacts for every started theorem
```

### Metric definitions

- **Total problems:** number of loaded theorem declarations.
- **Verified problems:** problems whose final generated `.lean` file exited
  successfully under `lake env lean`.
- **Verified success rate:** `verified / total`; stored as a value from 0 to 1
  in JSON and rendered as a percentage.
- **Average/median attempts:** candidate proofs completed per problem. A provider
  failure before producing a candidate counts as zero attempts.
- **Average latency:** mean wall time per problem, including model generation,
  Lean verification, retries, and artifact writes.
- **Total latency:** sum of per-problem wall times; execution is sequential.
- **Token usage:** sums only counts explicitly returned by the provider. The
  OpenAI Responses API exposes optional input, output, and total token counts;
  missing usage stays `null`/`unavailable`, and the report states how many
  attempts supplied usage. See the
  [official Responses API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

Every theorem row records `verified`, `attempts`, `latency_seconds`, the final
proof when successful, the final compiler/provider failure when unsuccessful,
optional token usage, and the associated ProofAgent artifact directory.
The top-level result also records the backend, model, and maximum attempt limit
needed to interpret or compare a run.

## Autoformalization benchmark and semantic evaluation

Run the complete curated suite through statement generation, Lean elaboration,
and the unchanged proof agent:

```bash
lean-proof evaluate-formalization --benchmark benchmarks/formalization
```

The 36 benchmark entries are balanced across arithmetic, algebra, logic,
inequalities, sets, and functions. Every entry contains `id`,
`natural_language`, `reference_statement`, `imports`, `category`, `assumptions`,
and `ambiguity_notes`. Reference statements are reviewed targets, not answers
available to the generation prompt.

The evaluator reports these distinct quantities:

- **Well formed:** a generated statement passed safety checks and Lean syntax,
  name, type, and proposition elaboration.
- **Provable / proof verified:** the existing `ProofAgent` produced a proof that
  a real `lake env lean` invocation accepted.
- **Semantically correct:** only a human review of fidelity to the original
  natural language can set this to true or false.
- **Statement syntax/type success rate:** well-formed statements divided by all
  benchmark problems.
- **Repair success rate:** initially rejected statements that became well formed
  on a later bounded attempt, divided by problems where repair was attempted.
- **Average formalization attempts:** generated statement attempts per problem.
- **End-to-end proof verification rate:** problems with both an elaborated
  statement and a kernel-accepted generated proof, divided by all problems.

The v0.6 evaluator additionally closes each declaration's explicit binders and
asks the existing `ProofAgent` to prove both implications:

```text
reference proposition → generated proposition
generated proposition → reference proposition
```

Each candidate proof is accepted only when the pinned Lean kernel accepts its
complete source file. Different theorem and binder names are therefore not an
automatic mismatch. Both verified directions produce `equivalent`. An
exhausted or rejected proof search produces `unknown`, never `not_equivalent`.
The `not_equivalent` value is reserved for a future checker with an explicit,
machine-verifiable counterexample or other trusted evidence.

This result is an auxiliary signal, not semantic ground truth. **Provability is
not semantic correctness**, and **failure to prove equivalence is not proof of
inequivalence**. Human review remains authoritative and independent.

Every run writes `evaluation.json`, `summary.md`, per-problem generation/proof
artifacts, both equivalence-direction proof runs, and a separate
`semantic_reviews.json`. Edit only that review file,
using `correct`, `incorrect`, `ambiguous`, or `unreviewed`, then apply it to a
later run:

```bash
lean-proof evaluate-formalization \
  --benchmark benchmarks/formalization \
  --reviews previous-run/semantic_reviews.json
```

Incorrect or ambiguous reviews can use the controlled categories `missing
assumption`, `stronger statement`, `weaker statement`, `wrong quantifier`,
`wrong type/domain`, `wrong implication direction`, and `ambiguity`. Automated
execution can additionally report `Lean elaboration failure`, `proof
verification failure`, or `backend failure`. The benchmark source is never
modified by review writeback.

### Standalone equivalence checking

Provide two JSON files containing a `statement` field and optional `imports`:

```json
{
  "statement": "theorem reference (n : ℕ) : n + 0 = n",
  "imports": ["Mathlib"]
}
```

Then run:

```bash
lean-proof check-equivalence reference.json generated.json
```

For convenience, the loader also accepts existing `theorem`,
`reference_statement`, `generated_statement`, or `final_theorem` fields. Imports
from both files are merged without duplication. The output and saved
`summary.json` report:

```text
Semantic Equivalence
Forward (reference → generated): verified | failed | unknown
Backward (generated → reference): verified | failed | unknown
Result: equivalent | unknown
```

`failed` is reserved for an input, provider, or execution failure. Ordinary
proof attempts rejected by Lean are `unknown`. Each direction keeps its theorem,
proof attempts, exact Lean errors, final proof when verified, and run directory.

## Compare Evaluations

Compare any two saved evaluation results, for example runs made with different
models, prompts, maximum attempt limits, or code revisions:

```bash
lean-proof compare \
  eval_a/evaluation.json \
  eval_b/evaluation.json \
  --json
```

The command prints a terminal summary and writes
`comparisons/<timestamp>-comparison-<id>/comparison.md`. Passing `--json` also
writes `comparison.json`; omit it when only the human-readable report is
needed. Use `--output-dir <path>` to choose another report root.

The report includes overall success-rate, verified-count, average-attempt,
average-latency, and token-usage deltas (B minus A), followed by newly solved
theorems, regressions, still-failed theorems, and per-theorem attempt/latency
changes. Token deltas are reported only when both evaluations contain token
usage. Any other missing metric is shown as `unavailable` rather than inferred.

Theorem names are the comparison key. When suites differ, regression statuses
are computed only for the intersection; unmatched names are listed separately
as `only in A` or `only in B`. Overall metric deltas still describe the two
complete saved runs, so the coverage counts should be considered when reading
them.

Illustrative terminal output:

```text
LeanProofAgent Evaluation Comparison
Coverage: 18 common, 2 only in A, 1 only in B
Success rate delta: +5.0 pp
Verified problems delta: +1
Average attempts delta: -0.20
Average latency delta: -0.45s
Token usage delta: unavailable
Newly solved (2): logic_or_comm, set_union_comm
Regressions (1): list_reverse_reverse
Still failed (3): theorem_a, theorem_b, theorem_c
```

Illustrative summary format (not a claimed run):

```text
LeanProofAgent Evaluation
Problems: 20
Verified: 16
Success rate: 80.0%
Average attempts: 1.80
Median attempts: 1
Average latency: 4.20s
Total latency: 84.00s
```

```text
| Problem       | Category   | Status   | Attempts | Latency |
| add_zero      | arithmetic | verified |        1 |   3.80s |
| set_union_comm| sets       | failed   |        3 |   6.10s |
```

## Offline demos

The demo spends no API credits. Its mock backend deliberately emits an invalid
proof first, checks that the second prompt contains Lean's real error, and then
returns a repair. Both attempts still go through the real Lean compiler.

```bash
python examples/mock_repair_demo.py
python examples/mock_autoformalization_demo.py
python examples/mock_formalization_evaluation_demo.py
python examples/mock_semantic_equivalence_demo.py
```

The autoformalization demo exercises the complete offline sequence with a mock
model and real Lean: natural language → invalid statement → Lean feedback →
repaired statement → `ProofAgent` → verified proof. These are test fixtures,
not benchmark solvers. The formalization evaluation demo additionally writes and checks
the JSON, Markdown, and independent semantic-review workflow. Production CLI
runs use the LLM backend; no backend contains a lookup table of benchmark
answers, and reference statements are never placed in model prompts.

## Run artifacts

Every invocation gets a unique UTC-stamped directory under `runs/` (or the path
passed to `--artifacts-dir`):

```text
runs/20260920T120000Z-add_zero-a1b2c3d4/
├── problem.json
├── attempt_01.lean
├── attempt_01.json
├── attempt_02.lean
├── attempt_02.json
└── summary.json
```

An attempt JSON records the extracted proof, exact source filename, command,
exit code, stdout, stderr, timeout flag, generation/verification elapsed time,
and optional provider token usage. `summary.json` records success/failure, total
attempts, aggregate reported usage, and the final verified proof when one exists.
`runs/` is ignored by Git because it can contain model output and large logs.

Each `solve-text` invocation similarly writes a unique directory:

```text
autoformalizations/20260920T120000Z-natural_add_zero-a1b2c3d4/
├── input.json                    original natural language and retry limits
├── formalization_01.lean         temporary Lean elaboration source
├── formalization_01.json         raw output, normalized theorem, and Lean error
├── formalization_02.lean
├── formalization_02.json
├── proof/                        unchanged ProofAgent run artifacts
└── summary.json                  final theorem and verified proof
```

## Verification and safety boundary

- Verification is a subprocess call with an argument list, not shell string
  interpolation: `lake env lean <absolute-attempt-file>`.
- The project root controls the pinned Lean and Mathlib versions.
- Exit code 0 is the only success condition.
- Explicit holes and axiom injection (`sorry`, `admit`, `axiom`) are rejected
  before Lean is invoked and are still recorded as failed attempts.
- Formalization additionally rejects every proof body (`:=`) and uses an
  isolated temporary axiom only to ask Lean to elaborate the proposition.
- The LLM cannot modify repository source through this API; it only supplies the
  proof expression appended to a validated theorem declaration.

Lean verifies formal correctness relative to Lean's kernel and imported
libraries. It does not establish that a natural-language theorem was formalized
with the intended meaning, nor does it make generated code trustworthy for any
purpose outside this proof-checking boundary.

## Tests

```bash
pytest
```

Tests use mock LLM objects and never call a paid API. Integration tests invoke
real Lean to establish all of the following:

1. a valid proof is accepted;
2. an invalid proof is rejected with compiler feedback;
3. that feedback reaches the next model prompt;
4. a repaired proof succeeds; and
5. both attempts and the run summary are persisted.

Autoformalization tests additionally confirm that unsafe declarations never
reach Lean, invalid statements receive compiler-guided repair, final statements
flow through the existing `ProofAgent`, and the original text, each statement,
Lean feedback, proof attempts, and verified proof are persisted.

Semantic-evaluation tests validate the 36-pair schema and category balance,
unknown-on-unproved comparison behavior, human review isolation, aggregate
metrics and reports, and real-Lean elaboration of every reference statement.
Equivalence tests cover renamed binders, logical reordering, quantifier order,
stronger and weaker statements, missing assumptions, and domain changes. A
real-Lean integration test verifies both directions through separate compiler
invocations.

CI performs `lake update`, downloads the Mathlib cache, installs Python 3.11,
runs pytest, and executes the offline repair demo. Evaluation tests use mock
backends and never call a paid API; a Lean-marked integration test confirms that
evaluation success still comes from the real compiler.

## Known limitations

- The MVP handles one theorem declaration at a time and expects imports plus a
  declaration without a proof body; it is not a general Lean project editor.
- Natural-language formalization is model-generated and can be semantically
  wrong even when its statement elaborates and its proof is kernel-verified.
- The formalizer currently uses `Mathlib`, a single theorem declaration, and a
  simple full-error retry prompt; it does not ask clarifying questions about
  ambiguous source text.
- Conservative statement comparison recognizes only normalized exact matches.
  The Lean-based checker can recognize more cases, but bounded proof search is
  incomplete and therefore often returns `unknown`.
- Logical equivalence of closed propositions is coarser than natural-language
  semantic fidelity: two independently true mathematical propositions can be
  logically equivalent without expressing the same intended concept. Human
  review is still required.
- The checker currently has no trusted counterexample generator, so it does not
  emit `not_equivalent`.
- Generation is synchronous and uses a simple full-error retry prompt. There is
  no streaming, parallel search, or proof minimization.
- Lexical blocking covers explicit proof holes and axiom declarations, but the
  main trust boundary is still Lean's kernel and the exact imported environment.
- OpenAI model availability, latency, and cost depend on the caller's account.
- Artifact writes are local files; there is no retention policy or shared store.
- Comparisons match theorems by their saved names; renames appear as suite
  additions/removals rather than the same theorem.
- The offline mock is only a workflow check. Its success rate must not be
  compared with a model evaluation.

## Best next step

Develop kernel-checkable counterexample certificates and structure-aware binder
alignment so the system can distinguish genuine semantic mismatches from mere
proof-search incompleteness without weakening the `unknown` boundary.

## License

MIT

# LeanProofAgent

LeanProofAgent is a small, executable MVP for **kernel-checked mathematical
reasoning**. An LLM proposes a Lean 4 proof; Lean checks it against Mathlib. If
Lean rejects the proof, the agent sends the exact compiler feedback back to the
LLM and tries again, up to a fixed limit.

```text
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

## MVP scope

Included:

- Lean 4.34.0 and the matching Mathlib 4.34.0 release, pinned in the repository.
- A model-neutral `LLMBackend` protocol.
- An OpenAI backend using the official Python SDK and Responses API.
- Compiler-guided retry with a configurable maximum attempt count.
- Rejection of `sorry`, `admit`, `axiom`, and theorem declarations that already
  contain a proof body.
- A CLI, theorem-only benchmarks, an offline mock repair demo, pytest coverage,
  and GitHub Actions CI.

Deliberately not included: a web UI, database, RAG, multi-agent orchestration,
or benchmark-specific proof lookup.

## Architecture

```text
src/lean_proof_agent/
├── agent.py            bounded generate → verify → repair loop
├── verifier.py         subprocess boundary for `lake env lean`
├── llm.py              backend protocol and output normalization
├── openai_backend.py   OpenAI Responses API adapter
├── prompts.py          initial and compiler-repair prompts
├── artifacts.py        per-attempt Lean and JSON records
├── models.py           typed domain objects and safety checks
├── benchmarks.py       theorem-only benchmark loader
└── cli.py              `lean-proof` command

benchmarks/             statements and metadata, never solutions
examples/               offline mock-LLM repair demo
tests/                  unit tests plus real-Lean integration tests
```

The small backend protocol is intentional: another provider or a local model
only needs to implement:

```python
class LLMBackend(Protocol):
    def generate(self, *, system_prompt: str, user_prompt: str) -> str: ...
```

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

## Offline repair demo

The demo spends no API credits. Its mock backend deliberately emits an invalid
proof first, checks that the second prompt contains Lean's real error, and then
returns a repair. Both attempts still go through the real Lean compiler.

```bash
python examples/mock_repair_demo.py
```

This is a test fixture, not a benchmark solver. Production CLI runs use the LLM
backend and benchmark files contain no answers.

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
exit code, stdout, stderr, timeout flag, and elapsed time. `summary.json` records
success/failure, total attempts, and the final verified proof when one exists.
`runs/` is ignored by Git because it can contain model output and large logs.

## Verification and safety boundary

- Verification is a subprocess call with an argument list, not shell string
  interpolation: `lake env lean <absolute-attempt-file>`.
- The project root controls the pinned Lean and Mathlib versions.
- Exit code 0 is the only success condition.
- Explicit holes and axiom injection (`sorry`, `admit`, `axiom`) are rejected
  before Lean is invoked and are still recorded as failed attempts.
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

CI performs `lake update`, downloads the Mathlib cache, installs Python 3.11,
runs pytest, and executes the offline repair demo.

## Known limitations

- The MVP handles one theorem declaration at a time and expects imports plus a
  declaration without a proof body; it is not a general Lean project editor.
- Generation is synchronous and uses a simple full-error retry prompt. There is
  no token budgeting, streaming, parallel search, or proof minimization.
- Lexical blocking covers explicit proof holes and axiom declarations, but the
  main trust boundary is still Lean's kernel and the exact imported environment.
- OpenAI model availability, latency, and cost depend on the caller's account.
- Artifact writes are local files; there is no retention policy or shared store.

## Best next step

Add a small evaluation runner that executes every theorem-only benchmark across
configurable model/backend settings and reports verified success rate, attempts,
latency, and token usage. That would measure the agent without expanding the
trusted verification core or adding unrelated product surface.

## License

MIT

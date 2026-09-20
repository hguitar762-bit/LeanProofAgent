import Mathlib

/-!
LeanProofAgent keeps generated proofs in run artifacts. This tiny library target
exists so Lake can validate the pinned Lean/Mathlib project itself.
-/

namespace LeanProofAgent

theorem smokeTest (n : ℕ) : n + 0 = n := by
  simp

end LeanProofAgent

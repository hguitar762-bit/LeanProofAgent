from lean_proof_agent.models import LeanProblem
from lean_proof_agent.prompts import build_user_prompt


def test_repair_prompt_contains_proof_and_compiler_feedback() -> None:
    problem = LeanProblem("p", "theorem p : 1 = 1")
    prompt = build_user_prompt(
        problem,
        attempt_number=2,
        previous_proof="by exact 0",
        compiler_error="type mismatch",
    )
    assert "by exact 0" in prompt
    assert "type mismatch" in prompt
    assert "Attempt 2" in prompt

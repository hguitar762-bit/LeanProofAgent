from types import SimpleNamespace

import pytest

from lean_proof_agent.openai_backend import OpenAIBackend


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_text="by\n  rfl")


def test_openai_backend_uses_responses_api() -> None:
    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    backend = OpenAIBackend("test-model", client=client)
    output = backend.generate(system_prompt="system", user_prompt="user")
    assert output == "by\n  rfl"
    assert responses.kwargs == {
        "model": "test-model",
        "instructions": "system",
        "input": "user",
    }


def test_openai_backend_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIBackend("test-model")

from types import SimpleNamespace

import pytest

from lean_proof_agent.models import GenerationResult, TokenUsage
from lean_proof_agent.openai_backend import OpenAIBackend


class FakeResponses:
    def __init__(self, usage: object | None = None) -> None:
        self.kwargs = None
        self.usage = usage

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_text="by\n  rfl", usage=self.usage)


def test_openai_backend_uses_responses_api() -> None:
    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    backend = OpenAIBackend("test-model", client=client)
    output = backend.generate(system_prompt="system", user_prompt="user")
    assert output == GenerationResult("by\n  rfl")
    assert responses.kwargs == {
        "model": "test-model",
        "instructions": "system",
        "input": "user",
    }


def test_openai_backend_records_reported_token_usage() -> None:
    usage = SimpleNamespace(input_tokens=12, output_tokens=5, total_tokens=17)
    client = SimpleNamespace(responses=FakeResponses(usage))
    output = OpenAIBackend("test-model", client=client).generate(
        system_prompt="system", user_prompt="user"
    )
    assert output.token_usage == TokenUsage(12, 5, 17)


def test_openai_backend_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIBackend("test-model")

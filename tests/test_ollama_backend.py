from __future__ import annotations

from io import BytesIO
import json
from urllib.error import HTTPError, URLError

import pytest

from lean_proof_agent.backends import resolve_model
from lean_proof_agent.models import GenerationResult, TokenUsage
from lean_proof_agent.ollama_backend import OllamaBackend


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class RecordingOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, request, *, timeout: float):
        self.requests.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def test_ollama_generate_uses_nonstreaming_api_and_records_tokens() -> None:
    opener = RecordingOpener(
        [
            {
                "response": "by\n  rfl",
                "prompt_eval_count": 12,
                "eval_count": 5,
                "done_reason": "stop",
            }
        ]
    )
    backend = OllamaBackend(
        "qwen-test", base_url="localhost:11434/", opener=opener
    )
    output = backend.generate(system_prompt="system", user_prompt="user")

    assert output == GenerationResult("by\n  rfl", TokenUsage(12, 5, 17), "stop")
    request, timeout = opener.requests[0]
    assert request.full_url == "http://localhost:11434/api/generate"
    assert request.get_method() == "POST"
    assert timeout == 600.0
    assert json.loads(request.data) == {
        "model": "qwen-test",
        "system": "system",
        "prompt": "user",
        "stream": False,
    }


def test_ollama_num_predict_is_optional_and_records_length_finish() -> None:
    opener = RecordingOpener(
        [
            {
                "response": "by\n  exact",
                "prompt_eval_count": 3,
                "eval_count": 2048,
                "done_reason": "length",
            }
        ]
    )
    backend = OllamaBackend("qwen-test", num_predict=2048, opener=opener)

    output = backend.generate(system_prompt="system", user_prompt="user")

    assert output.finish_reason == "length"
    request, _ = opener.requests[0]
    assert json.loads(request.data)["options"] == {"num_predict": 2048}


def test_ollama_num_predict_must_be_positive() -> None:
    with pytest.raises(ValueError, match="num_predict"):
        OllamaBackend("qwen-test", num_predict=0)


def test_ollama_empty_length_response_reports_truncation_metadata() -> None:
    backend = OllamaBackend(
        "qwen-test",
        num_predict=2048,
        opener=RecordingOpener(
            [
                {
                    "response": "",
                    "prompt_eval_count": 10,
                    "eval_count": 2048,
                    "done_reason": "length",
                }
            ]
        ),
    )

    with pytest.raises(
        RuntimeError, match=r"done_reason=length, eval_count=2048"
    ):
        backend.generate(system_prompt="system", user_prompt="user")


def test_ollama_usage_stays_unavailable_when_counts_are_missing() -> None:
    backend = OllamaBackend(
        "local", opener=RecordingOpener([{"response": "by\n  simp"}])
    )
    assert backend.generate(system_prompt="s", user_prompt="u").token_usage is None


def test_ollama_preflight_accepts_latest_alias_and_rejects_missing_model() -> None:
    present = OllamaBackend(
        "qwen",
        opener=RecordingOpener([{"models": [{"name": "qwen:latest"}]}]),
    )
    present.check_available()

    missing = OllamaBackend(
        "missing",
        opener=RecordingOpener([{"models": [{"model": "qwen:latest"}]}]),
    )
    with pytest.raises(RuntimeError, match=r"ollama pull missing"):
        missing.check_available()


def test_ollama_connection_and_404_errors_are_clear() -> None:
    offline = OllamaBackend(
        "local", opener=RecordingOpener([URLError("connection refused")])
    )
    with pytest.raises(RuntimeError, match=r"ollama serve"):
        offline.generate(system_prompt="s", user_prompt="u")

    not_found = HTTPError(
        "http://localhost:11434/api/generate",
        404,
        "Not Found",
        {},
        BytesIO(b'{"error":"model not found"}'),
    )
    missing = OllamaBackend("absent", opener=RecordingOpener([not_found]))
    with pytest.raises(RuntimeError, match=r"ollama pull absent"):
        missing.generate(system_prompt="s", user_prompt="u")


def test_ollama_model_comes_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "local-model")
    assert resolve_model("ollama", None) == "local-model"
    monkeypatch.delenv("OLLAMA_MODEL")
    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
        resolve_model("ollama", None)

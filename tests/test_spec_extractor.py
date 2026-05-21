import json
from pathlib import Path

import pytest

from packages.ai_providers.base import CompletionRequest, CompletionResponse, LLMClient
from packages.spec_extractor import SpecExtractionError, extract_spec
from packages.spec_extractor.validation import parse_spec_response

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM(LLMClient):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        return CompletionResponse(content=self._responses.pop(0), raw={})

    def validate_key(self) -> bool:
        return True


def _todo_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def _fenced(spec: dict) -> str:
    return f"```json\n{json.dumps(spec)}\n```"


def test_parse_spec_response_handles_fenced_json():
    spec = _todo_spec()
    assert parse_spec_response(_fenced(spec)) == spec


def test_parse_spec_response_handles_bare_json():
    spec = _todo_spec()
    assert parse_spec_response(json.dumps(spec)) == spec


def test_parse_spec_response_rejects_schema_violations():
    with pytest.raises(Exception):
        parse_spec_response("{}")


def test_extract_spec_returns_spec_on_first_try():
    spec = _todo_spec()
    llm = FakeLLM([_fenced(spec)])
    assert extract_spec("doc text", llm) == spec
    assert len(llm.requests) == 1


def test_extract_spec_retries_on_invalid_then_succeeds():
    spec = _todo_spec()
    llm = FakeLLM(["not json", _fenced(spec)])
    assert extract_spec("doc text", llm) == spec
    assert len(llm.requests) == 2
    feedback = llm.requests[1].messages[-1]
    assert feedback.role == "user"
    assert "failed validation" in feedback.content


def test_extract_spec_raises_after_exhausting_retries():
    llm = FakeLLM(["not json"] * 3)
    with pytest.raises(SpecExtractionError):
        extract_spec("doc text", llm, retries=2)

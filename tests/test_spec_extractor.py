import json
from pathlib import Path

import pytest

from packages.ai_providers.base import CompletionRequest, CompletionResponse, LLMClient
from packages.spec_extractor import SpecExtractionError, extract_spec, refine_spec
from packages.spec_extractor.validation import parse_spec_response

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM(LLMClient):
    def __init__(self, responses: list[str], usage: tuple[int, int] = (10, 20)) -> None:
        self._responses = list(responses)
        self._usage = usage
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        return CompletionResponse(
            content=self._responses.pop(0),
            raw={},
            input_tokens=self._usage[0],
            output_tokens=self._usage[1],
        )

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


def test_extract_spec_returns_spec_and_usage_on_first_try():
    spec = _todo_spec()
    llm = FakeLLM([_fenced(spec)], usage=(40, 60))
    result = extract_spec("doc text", llm)
    assert result.spec == spec
    assert result.usage == {"input": 40, "output": 60, "total": 100}
    assert len(llm.requests) == 1


def test_extract_spec_retries_on_invalid_then_succeeds():
    spec = _todo_spec()
    llm = FakeLLM(["not json", _fenced(spec)], usage=(5, 5))
    result = extract_spec("doc text", llm)
    assert result.spec == spec
    assert result.usage["total"] == 20
    assert len(llm.requests) == 2
    feedback = llm.requests[1].messages[-1]
    assert feedback.role == "user"
    assert "failed validation" in feedback.content


def test_extract_spec_raises_after_exhausting_retries():
    llm = FakeLLM(["not json"] * 3)
    with pytest.raises(SpecExtractionError):
        extract_spec("doc text", llm, retries=2)


def test_extract_spec_respects_token_budget():
    spec = _todo_spec()
    llm = FakeLLM([_fenced(spec)], usage=(60, 50))
    with pytest.raises(SpecExtractionError) as exc:
        extract_spec("doc text", llm, max_tokens_budget=100)
    assert "budget" in str(exc.value).lower()
    assert "110" in str(exc.value)


def test_refine_spec_returns_modified_spec_and_includes_request_context():
    current = _todo_spec()
    modified = json.loads(json.dumps(current))
    modified["entities"][1]["fields"].append(
        {"name": "priority", "type": "string", "required": False}
    )
    llm = FakeLLM([_fenced(modified)], usage=(50, 30))

    result = refine_spec(current, "Add a priority field to Todo.", llm)

    assert result.spec == modified
    assert result.usage == {"input": 50, "output": 30, "total": 80}
    user_msg = llm.requests[0].messages[0].content
    assert "Add a priority field to Todo." in user_msg
    assert '"name": "Todo"' in user_msg
    assert "modify a structured Spec" in (llm.requests[0].system or "")


def test_refine_spec_respects_token_budget():
    current = _todo_spec()
    llm = FakeLLM([_fenced(current)], usage=(60, 60))
    with pytest.raises(SpecExtractionError):
        refine_spec(current, "no-op", llm, max_tokens_budget=50)


def test_refine_spec_retries_on_invalid_response():
    current = _todo_spec()
    modified = json.loads(json.dumps(current))
    modified["entities"][1]["fields"].append(
        {"name": "priority", "type": "string", "required": False}
    )
    llm = FakeLLM(["not json", _fenced(modified)], usage=(10, 5))
    result = refine_spec(current, "Add priority field to Todo.", llm)
    assert result.spec == modified
    assert len(llm.requests) == 2

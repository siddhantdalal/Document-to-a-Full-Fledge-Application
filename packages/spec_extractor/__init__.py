import json
from dataclasses import dataclass, field
from typing import Any

import jsonschema

from packages.ai_providers import CompletionRequest, LLMClient, Message
from packages.spec_extractor.prompts import system_prompt
from packages.spec_extractor.validation import parse_spec_response


class SpecExtractionError(Exception):
    pass


@dataclass
class ExtractionResult:
    spec: dict[str, Any]
    usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0, "total": 0})


def extract_spec(
    markdown: str,
    llm: LLMClient,
    retries: int = 2,
    max_tokens_budget: int | None = None,
) -> ExtractionResult:
    request = CompletionRequest(
        system=system_prompt(),
        messages=[Message(role="user", content=markdown)],
        temperature=0.0,
    )
    usage = {"input": 0, "output": 0, "total": 0}
    last_error: Exception | None = None
    for _ in range(retries + 1):
        response = llm.complete(request)
        usage["input"] += response.input_tokens
        usage["output"] += response.output_tokens
        usage["total"] = usage["input"] + usage["output"]
        if max_tokens_budget is not None and usage["total"] > max_tokens_budget:
            raise SpecExtractionError(
                f"Token budget {max_tokens_budget} exceeded ({usage['total']} used)."
            )
        try:
            spec = parse_spec_response(response.content)
            return ExtractionResult(spec=spec, usage=usage)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            last_error = exc
            request.messages.append(Message(role="assistant", content=response.content))
            request.messages.append(
                Message(
                    role="user",
                    content=(
                        f"Your previous output failed validation: {exc}. "
                        "Return a corrected JSON object only, inside a ```json fenced block."
                    ),
                )
            )
    raise SpecExtractionError(
        f"Spec extraction failed after {retries + 1} attempts: {last_error}"
    )


__all__ = ["ExtractionResult", "SpecExtractionError", "extract_spec"]

import json

import jsonschema

from packages.ai_providers import CompletionRequest, LLMClient, Message
from packages.spec_extractor.prompts import system_prompt
from packages.spec_extractor.validation import parse_spec_response


class SpecExtractionError(Exception):
    pass


def extract_spec(markdown: str, llm: LLMClient, retries: int = 2) -> dict:
    request = CompletionRequest(
        system=system_prompt(),
        messages=[Message(role="user", content=markdown)],
        temperature=0.0,
    )
    last_error: Exception | None = None
    for _ in range(retries + 1):
        response = llm.complete(request)
        try:
            return parse_spec_response(response.content)
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


__all__ = ["SpecExtractionError", "extract_spec"]

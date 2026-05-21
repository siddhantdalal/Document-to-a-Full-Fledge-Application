import json
import re
from typing import Any

import jsonschema

from packages.spec_extractor.prompts import get_schema

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def parse_spec_response(content: str) -> dict[str, Any]:
    match = _FENCE.search(content)
    raw = match.group(1) if match else content.strip()
    spec = json.loads(raw)
    jsonschema.validate(spec, get_schema())
    return spec

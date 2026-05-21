import json
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.json"


def get_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def system_prompt() -> str:
    schema = json.dumps(get_schema(), indent=2)
    return (
        "You extract a structured Spec from a requirements document.\n\n"
        "The Spec is the single source of truth for code generation. Extract exactly "
        "what the document says — no extra features, no missing ones. When the "
        "document is silent about something, omit it (subject to the defaults below) "
        "rather than invent it.\n\n"
        "Output a single JSON object that conforms to this schema:\n\n"
        f"```json\n{schema}\n```\n\n"
        "Defaults to apply when the document is silent:\n"
        "- stack: {\"frontend\": \"react-vite-ts\", \"backend\": \"fastapi\", \"db\": \"sqlite\"}\n"
        "- auth: {\"type\": \"none\"} (omit \"roles\" if none described)\n"
        "- app.version: \"0.1.0\"\n"
        "- integrations: []\n"
        "- non_functional.tests: \"smoke\"\n\n"
        "Respond with ONLY the JSON object inside a ```json fenced block. No prose."
    )


def refinement_system_prompt() -> str:
    schema = json.dumps(get_schema(), indent=2)
    return (
        "You modify a structured Spec based on a user's change request. "
        "Output the FULL updated Spec as JSON, with the user's change applied.\n\n"
        "Preserve everything not mentioned by the change request — do not invent "
        "additional changes, additional entities, additional endpoints, or "
        "additional screens beyond what the user asked for. If the request is "
        "ambiguous, prefer the smallest change that satisfies it.\n\n"
        "The Spec must conform to this schema:\n\n"
        f"```json\n{schema}\n```\n\n"
        "Respond with ONLY the updated JSON object inside a ```json fenced block. "
        "No prose."
    )


def refinement_user_message(current_spec: dict, change_request: str) -> str:
    return (
        f"Current Spec:\n\n```json\n{json.dumps(current_spec, indent=2)}\n```\n\n"
        f"Change request: {change_request}"
    )

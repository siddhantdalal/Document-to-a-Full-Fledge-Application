from dataclasses import dataclass


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def validate(project_dir: str) -> ValidationResult:
    raise NotImplementedError

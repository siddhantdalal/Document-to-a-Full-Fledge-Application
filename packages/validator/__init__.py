import py_compile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


def validate(project_dir: Path) -> ValidationResult:
    project_dir = Path(project_dir)
    errors: list[str] = []
    count = 0
    for py_file in (project_dir / "backend").rglob("*.py"):
        count += 1
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(
                f"{py_file.relative_to(project_dir)}: {str(exc).splitlines()[0]}"
            )
    return ValidationResult(
        ok=not errors,
        errors=errors,
        summary={"python_files": count, "python_errors": len(errors)},
    )


__all__ = ["ValidationResult", "validate"]

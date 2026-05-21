import json
from pathlib import Path

from packages.generator import generate
from packages.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_validate_passes_on_generated_project(tmp_path: Path):
    project = generate(_load_spec(), tmp_path / "out")
    result = validate(project)
    assert result.ok
    assert result.errors == []
    assert result.summary["python_files"] > 0
    assert result.summary["python_errors"] == 0


def test_validate_catches_syntax_error(tmp_path: Path):
    project = generate(_load_spec(), tmp_path / "out")
    bad = project / "backend" / "app" / "broken.py"
    bad.write_text("def broken(:\n")
    result = validate(project)
    assert result.ok is False
    assert any("broken.py" in err for err in result.errors)
    assert result.summary["python_errors"] >= 1


def test_validate_empty_project_succeeds(tmp_path: Path):
    project = tmp_path / "empty"
    (project / "backend").mkdir(parents=True)
    result = validate(project)
    assert result.ok
    assert result.summary["python_files"] == 0

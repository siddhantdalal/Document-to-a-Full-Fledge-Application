import json
import zipfile
from pathlib import Path

from packages.generator import generate
from packages.generator.template import package_zip, slugify

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_slugify_handles_spaces_and_punctuation():
    assert slugify("My Todo App!") == "my-todo-app"
    assert slugify("  ") == "app"


def test_generate_creates_template_files(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")

    assert (project / "README.md").exists()
    assert (project / "docker-compose.yml").exists()
    assert (project / "frontend" / "package.json").exists()
    assert (project / "frontend" / "src" / "App.tsx").exists()
    assert (project / "backend" / "app" / "main.py").exists()
    assert (project / "backend" / "app" / "auth.py").exists()
    assert (project / "spec.json").exists()


def test_generate_substitutes_placeholders(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")

    readme = (project / "README.md").read_text()
    assert spec["app"]["name"] in readme
    assert "{{APP_NAME}}" not in readme

    pkg = json.loads((project / "frontend" / "package.json").read_text())
    assert pkg["name"] == f"{slugify(spec['app']['name'])}-frontend"

    main_py = (project / "backend" / "app" / "main.py").read_text()
    assert spec["app"]["name"] in main_py
    assert "{{APP_NAME}}" not in main_py


def test_generate_writes_spec_json(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")

    written = json.loads((project / "spec.json").read_text())
    assert written == spec


def test_package_zip_contains_all_files(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    zip_path = package_zip(project, tmp_path / "out.zip")

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "README.md" in names
    assert "frontend/package.json" in names
    assert "backend/app/main.py" in names
    assert "spec.json" in names


def test_generate_overwrites_existing_output(tmp_path: Path):
    spec = _load_spec()
    out = tmp_path / "out"
    generate(spec, out)
    (out / "stale.txt").write_text("stale")
    generate(spec, out)
    assert not (out / "stale.txt").exists()
    assert (out / "README.md").exists()

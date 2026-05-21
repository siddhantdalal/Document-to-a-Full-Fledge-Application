import json
import py_compile
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


def test_generate_writes_spec_derived_files(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")

    assert (project / "backend" / "app" / "models" / "user.py").exists()
    assert (project / "backend" / "app" / "models" / "todo.py").exists()
    assert (project / "backend" / "app" / "routers" / "auth.py").exists()
    assert (project / "backend" / "app" / "routers" / "todos.py").exists()
    assert (project / "frontend" / "src" / "routes" / "Login.tsx").exists()
    assert (project / "frontend" / "src" / "routes" / "Signup.tsx").exists()
    assert (project / "frontend" / "src" / "routes" / "Todos.tsx").exists()
    assert (project / "frontend" / "src" / "lib" / "types.ts").exists()
    assert (project / "frontend" / "src" / "lib" / "todos.ts").exists()
    assert (project / "frontend" / "src" / "lib" / "auth.ts").exists()


def test_generated_backend_compiles(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    for py_file in (project / "backend").rglob("*.py"):
        py_compile.compile(str(py_file), doraise=True)


def test_generated_main_registers_routers(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    main_text = (project / "backend" / "app" / "main.py").read_text()
    assert "from app.routers import" in main_text
    assert "app.include_router(todos.router)" in main_text
    assert "app.include_router(auth.router)" in main_text
    assert "# GENERATED:IMPORTS" not in main_text
    assert "# GENERATED:ROUTERS" not in main_text


def test_generated_app_tsx_registers_routes(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    app_text = (project / "frontend" / "src" / "App.tsx").read_text()
    assert 'import { Route, Routes } from "react-router-dom";' in app_text
    assert '<Route path="/login" element={<Login />} />' in app_text
    assert '<Route path="/" element={<Todos />} />' in app_text
    assert "// GENERATED:IMPORTS" not in app_text
    assert "{/* GENERATED:ROUTES */}" not in app_text

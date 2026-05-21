import json
from pathlib import Path

from packages.generator import generate
from packages.reconciler import reconcile

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_reconcile_passes_on_generated_project(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    r = reconcile(spec, project)
    assert r.ok, f"missing: {r.missing}, extra: {r.extra}"
    assert r.coverage["entities"]["covered"] == len(spec["entities"])
    assert r.coverage["endpoints"]["covered"] == len(spec["endpoints"])
    assert r.coverage["screens"]["covered"] == len(spec["screens"])


def test_reconcile_detects_missing_model(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    (project / "backend" / "app" / "models" / "todo.py").unlink()
    r = reconcile(spec, project)
    assert r.ok is False
    assert any("entity Todo" in m for m in r.missing)


def test_reconcile_detects_missing_endpoint(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    todos_py = project / "backend" / "app" / "routers" / "todos.py"
    todos_py.write_text('from fastapi import APIRouter\nrouter = APIRouter(prefix="/todos", tags=["todos"])\n')
    r = reconcile(spec, project)
    assert r.ok is False
    assert any("endpoint GET /todos" in m for m in r.missing)
    assert any("endpoint POST /todos" in m for m in r.missing)


def test_reconcile_detects_missing_screen_route_in_app_tsx(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    app_tsx = project / "frontend" / "src" / "App.tsx"
    app_tsx.write_text(app_tsx.read_text().replace('path="/"', 'path="/missing"'))
    r = reconcile(spec, project)
    assert r.ok is False
    assert any("screen Todos" in m and "App.tsx" in m for m in r.missing)


def test_reconcile_detects_extra_artifact(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    (project / "backend" / "app" / "models" / "ghost.py").write_text(
        "from sqlmodel import SQLModel\n\nclass Ghost(SQLModel):\n    pass\n"
    )
    r = reconcile(spec, project)
    assert any("model ghost" in e for e in r.extra)
    assert r.ok is True


def test_reconcile_coverage_counts_partial(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    (project / "backend" / "app" / "models" / "todo.py").unlink()
    r = reconcile(spec, project)
    assert r.coverage["entities"]["covered"] == 1
    assert r.coverage["entities"]["total"] == 2

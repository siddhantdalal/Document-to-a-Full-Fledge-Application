import copy
import json
import py_compile
from pathlib import Path

from packages.generator import generate
from packages.generator.test_gen import (
    render_auth_tests,
    render_conftest,
    render_crud_smoke_test,
    should_generate_tests,
    write_backend_tests,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_should_generate_tests_for_smoke_level():
    spec = _load_spec()
    assert should_generate_tests(spec) is True


def test_should_skip_when_tests_level_is_none():
    spec = _load_spec()
    spec["non_functional"]["tests"] = "none"
    assert should_generate_tests(spec) is False


def test_should_skip_when_non_functional_block_missing():
    spec = _load_spec()
    del spec["non_functional"]
    assert should_generate_tests(spec) is False


def test_conftest_includes_auth_fixture_for_jwt(tmp_path: Path):
    spec = _load_spec()
    rendered = render_conftest(spec)
    assert "TestClient" in rendered
    assert "dependency_overrides" in rendered
    assert "def auth_token" in rendered
    out = tmp_path / "conftest.py"
    out.write_text(rendered)
    py_compile.compile(str(out), doraise=True)


def test_conftest_omits_auth_fixture_when_no_auth(tmp_path: Path):
    spec = _load_spec()
    spec["auth"] = {"type": "none"}
    rendered = render_conftest(spec)
    assert "def auth_token" not in rendered
    out = tmp_path / "conftest.py"
    out.write_text(rendered)
    py_compile.compile(str(out), doraise=True)


def test_render_auth_tests_compiles(tmp_path: Path):
    out = tmp_path / "test_auth.py"
    out.write_text(render_auth_tests())
    py_compile.compile(str(out), doraise=True)


def test_render_crud_smoke_test_for_todos(tmp_path: Path):
    spec = _load_spec()
    todo = next(e for e in spec["entities"] if e["name"] == "Todo")
    eps = [ep for ep in spec["endpoints"] if ep["path"].startswith("/todos")]
    rendered = render_crud_smoke_test("todos", todo, eps, has_auth=True)
    assert rendered is not None
    assert "def test_todos_crud(client, auth_headers):" in rendered
    assert 'client.post("/todos"' in rendered
    assert 'client.delete(f"/todos/{item_id}"' in rendered
    assert 'client.patch(f"/todos/{item_id}"' in rendered
    out = tmp_path / "test_todos.py"
    out.write_text(rendered)
    py_compile.compile(str(out), doraise=True)


def test_render_crud_returns_none_without_create_endpoint():
    spec = _load_spec()
    todo = next(e for e in spec["entities"] if e["name"] == "Todo")
    list_only = [ep for ep in spec["endpoints"] if ep["method"] == "GET" and ep["path"] == "/todos"]
    assert render_crud_smoke_test("todos", todo, list_only, has_auth=True) is None


def test_write_backend_tests_produces_files(tmp_path: Path):
    spec = _load_spec()
    project = tmp_path / "out"
    (project / "backend").mkdir(parents=True)

    written = write_backend_tests(spec, project)
    relative = {p.relative_to(project).as_posix() for p in written}

    assert "backend/tests/__init__.py" in relative
    assert "backend/tests/conftest.py" in relative
    assert "backend/tests/test_auth.py" in relative
    assert "backend/tests/test_todos.py" in relative


def test_write_backend_tests_no_op_when_tests_disabled(tmp_path: Path):
    spec = _load_spec()
    spec["non_functional"]["tests"] = "none"
    project = tmp_path / "out"
    (project / "backend").mkdir(parents=True)
    assert write_backend_tests(spec, project) == []
    assert not (project / "backend" / "tests").exists()


def test_generate_includes_tests_for_todo_fixture(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")

    assert (project / "backend" / "tests" / "conftest.py").exists()
    assert (project / "backend" / "tests" / "test_auth.py").exists()
    assert (project / "backend" / "tests" / "test_todos.py").exists()

    for py_file in (project / "backend" / "tests").glob("*.py"):
        py_compile.compile(str(py_file), doraise=True)


def test_generate_omits_tests_when_level_is_none(tmp_path: Path):
    spec = _load_spec()
    spec["non_functional"]["tests"] = "none"
    project = generate(spec, tmp_path / "out")
    assert not (project / "backend" / "tests").exists()

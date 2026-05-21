import json
import py_compile
from pathlib import Path

from packages.generator import generate

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_default_sqlite_compose_has_no_postgres(tmp_path: Path):
    spec = _load_spec()
    project = generate(spec, tmp_path / "out")
    compose = (project / "docker-compose.yml").read_text()
    assert "postgres" not in compose.lower()
    pyproject = (project / "backend" / "pyproject.toml").read_text()
    assert "psycopg" not in pyproject
    config = (project / "backend" / "app" / "config.py").read_text()
    assert "sqlite:///./app.db" in config


def test_postgres_choice_rewrites_compose(tmp_path: Path):
    spec = _load_spec()
    spec["stack"]["db"] = "postgres"
    project = generate(spec, tmp_path / "out")

    compose = (project / "docker-compose.yml").read_text()
    assert "postgres:16-alpine" in compose
    assert "POSTGRES_USER: app" in compose
    assert "postgresql+psycopg://app:app@db:5432/app" in compose
    assert "depends_on:" in compose
    assert "db_data:" in compose


def test_postgres_choice_adds_psycopg_dep(tmp_path: Path):
    spec = _load_spec()
    spec["stack"]["db"] = "postgres"
    project = generate(spec, tmp_path / "out")

    pyproject = (project / "backend" / "pyproject.toml").read_text()
    assert "psycopg[binary]" in pyproject
    dockerfile = (project / "backend" / "Dockerfile").read_text()
    assert "psycopg[binary]" in dockerfile


def test_postgres_choice_switches_default_database_url(tmp_path: Path):
    spec = _load_spec()
    spec["stack"]["db"] = "postgres"
    project = generate(spec, tmp_path / "out")
    config = (project / "backend" / "app" / "config.py").read_text()
    assert "postgresql+psycopg" in config
    assert "sqlite:///" not in config


def test_postgres_choice_keeps_backend_compiling(tmp_path: Path):
    spec = _load_spec()
    spec["stack"]["db"] = "postgres"
    project = generate(spec, tmp_path / "out")
    for py_file in (project / "backend").rglob("*.py"):
        py_compile.compile(str(py_file), doraise=True)

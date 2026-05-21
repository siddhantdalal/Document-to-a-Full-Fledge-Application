from pathlib import Path
from typing import Any

from packages.generator.backend import (
    _AUTH_PATHS,
    endpoint_kind,
    find_entity_for_group,
    group_endpoints,
)
from packages.generator.naming import snake

_TEST_LEVELS_WITH_OUTPUT = {"smoke", "full"}


def should_generate_tests(spec: dict[str, Any]) -> bool:
    level = (spec.get("non_functional") or {}).get("tests")
    return level in _TEST_LEVELS_WITH_OUTPUT


def _sample_value(field: dict[str, Any]) -> Any:
    type_ = field["type"]
    name = field["name"].lower()
    if type_ == "string":
        if "password" in name:
            return "pass1234"
        if "email" in name:
            return "test@example.com"
        return "sample"
    if type_ == "integer":
        return 0
    if type_ == "float":
        return 0.0
    if type_ == "boolean":
        return False
    if type_ == "datetime":
        return "2026-01-01T00:00:00"
    if type_ == "json":
        return {}
    return "sample"


def _sample_payload(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        snake(f["name"]): _sample_value(f)
        for f in entity["fields"]
        if f.get("required", True)
    }


def _sample_update(entity: dict[str, Any]) -> dict[str, Any]:
    for f in entity["fields"]:
        if f["type"] == "boolean":
            return {snake(f["name"]): True}
        if f["type"] == "string" and f["name"].lower() not in ("email", "password"):
            return {snake(f["name"]): "updated"}
    return {}


def render_conftest(spec: dict[str, Any]) -> str:
    has_auth = (spec.get("auth") or {}).get("type") == "jwt"
    base = """import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.models  # noqa: F401 - registers SQLModel tables
from app.db import get_session
from app.main import app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
"""
    if has_auth:
        base += """

@pytest.fixture
def auth_token(client):
    res = client.post(
        "/signup",
        data={"username": "fixture@example.com", "password": "pass1234"},
    )
    return res.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
"""
    return base


def render_auth_tests() -> str:
    return """def test_signup_returns_token(client):
    res = client.post(
        "/signup", data={"username": "new@example.com", "password": "pass1234"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_signup_duplicate_returns_409(client):
    client.post("/signup", data={"username": "dupe@example.com", "password": "pass1234"})
    res = client.post("/signup", data={"username": "dupe@example.com", "password": "pass1234"})
    assert res.status_code == 409


def test_login_with_correct_password(client):
    client.post("/signup", data={"username": "login@example.com", "password": "pass1234"})
    res = client.post(
        "/login", data={"username": "login@example.com", "password": "pass1234"}
    )
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_with_wrong_password(client):
    client.post("/signup", data={"username": "wrong@example.com", "password": "pass1234"})
    res = client.post(
        "/login", data={"username": "wrong@example.com", "password": "bad"}
    )
    assert res.status_code == 401
"""


def render_crud_smoke_test(
    group: str,
    entity: dict[str, Any],
    endpoints: list[dict[str, Any]],
    has_auth: bool,
) -> str | None:
    kinds = {endpoint_kind(ep, group): ep for ep in endpoints}
    if "create" not in kinds:
        return None

    auth_arg = ", auth_headers" if has_auth else ""
    auth_kw = ", headers=auth_headers" if has_auth else ""

    payload = _sample_payload(entity)
    payload_lines = ["    payload = {"]
    for k, v in payload.items():
        payload_lines.append(f"        {k!r}: {v!r},")
    payload_lines.append("    }")

    body = list(payload_lines)
    body.append(f'    res = client.post("/{group}", json=payload{auth_kw})')
    body.append("    assert res.status_code == 200, res.text")
    body.append("    created = res.json()")
    body.append('    item_id = created["id"]')

    if "get_one" in kinds:
        body.append(f'    res = client.get(f"/{group}/{{item_id}}"{auth_kw})')
        body.append("    assert res.status_code == 200")
        body.append('    assert res.json()["id"] == item_id')

    if "list" in kinds:
        body.append(f'    res = client.get("/{group}"{auth_kw})')
        body.append("    assert res.status_code == 200")
        body.append("    assert any(item[\"id\"] == item_id for item in res.json())")

    if "update" in kinds:
        update_payload = _sample_update(entity)
        if update_payload:
            body.append(
                f'    res = client.patch(f"/{group}/{{item_id}}", json={update_payload!r}{auth_kw})'
            )
            body.append("    assert res.status_code == 200")

    if "delete" in kinds:
        body.append(f'    res = client.delete(f"/{group}/{{item_id}}"{auth_kw})')
        body.append("    assert res.status_code == 204")

    func_sig = f"def test_{group}_crud(client{auth_arg}):"
    return func_sig + "\n" + "\n".join(body) + "\n"


def write_backend_tests(spec: dict[str, Any], project_dir: Path) -> list[Path]:
    if not should_generate_tests(spec):
        return []

    tests_dir = project_dir / "backend" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    (tests_dir / "__init__.py").write_text("")
    written.append(tests_dir / "__init__.py")

    (tests_dir / "conftest.py").write_text(render_conftest(spec))
    written.append(tests_dir / "conftest.py")

    has_auth = (spec.get("auth") or {}).get("type") == "jwt"
    auth_paths_present = any(ep["path"] in _AUTH_PATHS for ep in spec["endpoints"])
    if has_auth and auth_paths_present:
        (tests_dir / "test_auth.py").write_text(render_auth_tests())
        written.append(tests_dir / "test_auth.py")

    non_auth_endpoints = [ep for ep in spec["endpoints"] if ep["path"] not in _AUTH_PATHS]
    for group, eps in group_endpoints(non_auth_endpoints).items():
        entity = find_entity_for_group(group, spec)
        if not entity:
            continue
        rendered = render_crud_smoke_test(group, entity, eps, has_auth)
        if not rendered:
            continue
        (tests_dir / f"test_{group}.py").write_text(rendered)
        written.append(tests_dir / f"test_{group}.py")

    return written


__all__ = [
    "render_auth_tests",
    "render_conftest",
    "render_crud_smoke_test",
    "should_generate_tests",
    "write_backend_tests",
]

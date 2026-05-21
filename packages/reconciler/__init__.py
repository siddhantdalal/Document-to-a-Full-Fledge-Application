import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.generator.naming import pascal, snake

_PREFIX_RE = re.compile(r'APIRouter\([^)]*prefix=["\']([^"\']+)["\']')
_ROUTE_RE = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']')


@dataclass
class ReconciliationResult:
    ok: bool
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    coverage: dict[str, dict[str, int]] = field(default_factory=dict)


def _declared_routes(routers_dir: Path) -> set[tuple[str, str]]:
    declared: set[tuple[str, str]] = set()
    if not routers_dir.exists():
        return declared
    for f in routers_dir.glob("*.py"):
        if f.stem == "__init__":
            continue
        content = f.read_text()
        prefix_m = _PREFIX_RE.search(content)
        prefix = prefix_m.group(1) if prefix_m else ""
        for m in _ROUTE_RE.finditer(content):
            method = m.group(1).upper()
            rel = m.group(2)
            full = (prefix + rel) or "/"
            declared.add((method, full))
    return declared


def reconcile(spec: dict[str, Any], project_dir: Path) -> ReconciliationResult:
    project_dir = Path(project_dir)
    backend = project_dir / "backend"
    fe_src = project_dir / "frontend" / "src"
    missing: list[str] = []
    extra: list[str] = []

    expected_models = {snake(e["name"]) for e in spec["entities"]}
    models_dir = backend / "app" / "models"
    entity_covered = 0
    for entity in spec["entities"]:
        if (models_dir / f"{snake(entity['name'])}.py").exists():
            entity_covered += 1
        else:
            missing.append(f"entity {entity['name']}: model file not generated")
    if models_dir.exists():
        for model_file in models_dir.glob("*.py"):
            if model_file.stem == "__init__":
                continue
            if model_file.stem not in expected_models:
                extra.append(f"model {model_file.stem}: no matching entity in spec")

    declared = _declared_routes(backend / "app" / "routers")
    expected_endpoints = {(ep["method"].upper(), ep["path"]) for ep in spec["endpoints"]}
    endpoint_covered = len(expected_endpoints & declared)
    for method, path in sorted(expected_endpoints - declared):
        missing.append(f"endpoint {method} {path}: not declared in any router")
    for method, path in sorted(declared - expected_endpoints):
        extra.append(f"endpoint {method} {path}: not in spec")

    app_tsx = (fe_src / "App.tsx").read_text() if (fe_src / "App.tsx").exists() else ""
    expected_pages = {pascal(s["name"]) for s in spec["screens"]}
    routes_dir = fe_src / "routes"
    screen_covered = 0
    for screen in spec["screens"]:
        page = routes_dir / f"{pascal(screen['name'])}.tsx"
        registered = f'path="{screen["route"]}"' in app_tsx
        if page.exists() and registered:
            screen_covered += 1
        else:
            reasons: list[str] = []
            if not page.exists():
                reasons.append("page file missing")
            if not registered:
                reasons.append("route not in App.tsx")
            missing.append(f"screen {screen['name']}: {', '.join(reasons)}")
    if routes_dir.exists():
        for page in routes_dir.glob("*.tsx"):
            if page.stem not in expected_pages:
                extra.append(f"page {page.stem}: no matching screen in spec")

    coverage = {
        "entities": {"covered": entity_covered, "total": len(spec["entities"])},
        "endpoints": {"covered": endpoint_covered, "total": len(spec["endpoints"])},
        "screens": {"covered": screen_covered, "total": len(spec["screens"])},
    }
    return ReconciliationResult(
        ok=not missing,
        missing=missing,
        extra=extra,
        coverage=coverage,
    )


__all__ = ["ReconciliationResult", "reconcile"]

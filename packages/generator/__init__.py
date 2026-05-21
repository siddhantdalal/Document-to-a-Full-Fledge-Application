import json
import shutil
from pathlib import Path
from typing import Any

from packages.generator.backend import write_backend
from packages.generator.frontend import write_frontend
from packages.generator.template import (
    DEFAULT_TEMPLATE_ROOT,
    PlaceholderReplacements,
    copy_template,
    package_zip,
    slugify,
)
from packages.generator.test_gen import write_backend_tests

_POSTGRES_COMPOSE = """services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    ports:
      - "5432:5432"
    volumes:
      - db_data:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://app:app@db:5432/app
    volumes:
      - ./backend:/app
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      - backend

volumes:
  db_data:
"""


def _apply_postgres(project_dir: Path) -> None:
    (project_dir / "docker-compose.yml").write_text(_POSTGRES_COMPOSE)

    pyproject = project_dir / "backend" / "pyproject.toml"
    text = pyproject.read_text()
    text = text.replace(
        '"python-multipart>=0.0.9",\n]',
        '"python-multipart>=0.0.9",\n    "psycopg[binary]>=3.2",\n]',
    )
    pyproject.write_text(text)

    dockerfile = project_dir / "backend" / "Dockerfile"
    text = dockerfile.read_text()
    text = text.replace(
        '"python-multipart>=0.0.9"',
        '"python-multipart>=0.0.9" \\\n    "psycopg[binary]>=3.2"',
    )
    dockerfile.write_text(text)

    config = project_dir / "backend" / "app" / "config.py"
    text = config.read_text()
    text = text.replace(
        'database_url: str = "sqlite:///./app.db"',
        'database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"',
    )
    config.write_text(text)


def _apply_db_choice(spec: dict[str, Any], project_dir: Path) -> None:
    db = (spec.get("stack") or {}).get("db", "sqlite")
    if db == "postgres":
        _apply_postgres(project_dir)


def generate(
    spec: dict,
    output_dir: Path,
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
) -> Path:
    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)

    name = spec["app"]["name"]
    replacements: PlaceholderReplacements = {
        "{{APP_NAME}}": name,
        "{{APP_SUMMARY}}": spec["app"].get("summary", ""),
        "{{APP_SLUG}}": slugify(name),
    }

    copy_template(template_root / "react-fastapi", output_dir, replacements)
    write_backend(spec, output_dir)
    write_frontend(spec, output_dir)
    write_backend_tests(spec, output_dir)
    _apply_db_choice(spec, output_dir)
    (output_dir / "spec.json").write_text(json.dumps(spec, indent=2))
    return output_dir


__all__ = ["generate", "package_zip"]

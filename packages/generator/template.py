import re
import shutil
import zipfile
from pathlib import Path

PlaceholderReplacements = dict[str, str]

DEFAULT_TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "templates"

_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip"}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "app"


def copy_template(
    source: Path,
    destination: Path,
    replacements: PlaceholderReplacements,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for src in source.rglob("*"):
        rel = src.relative_to(source)
        target = destination / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in _BINARY_SUFFIXES:
            shutil.copyfile(src, target)
            continue
        content = src.read_text(encoding="utf-8")
        for needle, value in replacements.items():
            content = content.replace(needle, value)
        target.write_text(content, encoding="utf-8")


def package_zip(project_dir: Path, zip_path: Path) -> Path:
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(project_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(project_dir))
    return zip_path

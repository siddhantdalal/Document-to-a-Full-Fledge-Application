import json
import shutil
from pathlib import Path

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
    (output_dir / "spec.json").write_text(json.dumps(spec, indent=2))
    return output_dir


__all__ = ["generate", "package_zip"]

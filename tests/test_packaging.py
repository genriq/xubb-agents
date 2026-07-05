"""Packaging drift-locks (public-release audit, 2026-07-04).

A built wheel once shipped WITHOUT library/schemas/*.json: the old package-data
glob ('"*" = ["*.json"]') is non-recursive and schemas/ is not a package, so a
pip-installed xubb-agents silently degraded every v2 output format to
DynamicAgent's emergency fallback schema (a log warning was the only symptom).

These tests can't build a wheel (that's the release script's job), but they
lock the two config facts the fix depends on, so a refactor that reintroduces
the bug fails CI instead of shipping quietly.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
SCHEMAS_DIR = REPO_ROOT / "library" / "schemas"

# The schemas DynamicAgent actually loads at runtime (library/dynamic.py).
REQUIRED_SCHEMAS = [
    "default.json",
    "default_v2.json",
    "v2_raw.json",
    "ui_control.json",
    "widget_control.json",
]


class TestSchemaPackaging:
    def test_schema_files_exist_on_disk(self):
        for name in REQUIRED_SCHEMAS:
            assert (SCHEMAS_DIR / name).is_file(), f"library/schemas/{name} missing"

    def test_pyproject_ships_the_schemas(self):
        """package-data must include the explicit schemas glob for the library
        package — the bare '"*" = [...*.json...]' glob does NOT reach into
        schemas/ (non-recursive, not a package) and is not sufficient."""
        assert re.search(
            r'"xubb_agents\.library"\s*=\s*\[[^\]]*"schemas/\*\.json"', PYPROJECT
        ), 'pyproject.toml must declare "xubb_agents.library" = ["schemas/*.json"] package-data'

    def test_version_is_consistent(self):
        """pyproject version and __init__.__version__ must agree (release identity)."""
        pyproject_version = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT, re.M).group(1)
        init_text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        init_version = re.search(r'__version__\s*=\s*"([^"]+)"', init_text).group(1)
        assert pyproject_version == init_version, (
            f"pyproject.toml says {pyproject_version} but __init__.py says {init_version}"
        )

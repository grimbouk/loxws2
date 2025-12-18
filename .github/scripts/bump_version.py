"""Bump project version and align HA manifest requirements."""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]

PYPROJECT = ROOT / "pyproject.toml"
MANIFEST = ROOT / "custom_components" / "loxone" / "manifest.json"


def _load_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["version"]


def _increment(version: str) -> str:
    parts = version.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"Unsupported version format: {version}")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def _write_pyproject(new_version: str) -> None:
    content = PYPROJECT.read_text()
    updated = re.sub(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{new_version}"', content)
    PYPROJECT.write_text(updated)


def _write_manifest(new_version: str) -> None:
    manifest = json.loads(MANIFEST.read_text())
    manifest["version"] = new_version
    manifest["requirements"] = [f"loxone-api=={new_version}"]
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    current = _load_version()
    new_version = _increment(current)
    _write_pyproject(new_version)
    _write_manifest(new_version)
    print(f"Bumped version: {current} -> {new_version}")
    output = Path(__file__).with_suffix(".output")
    output.write_text(f"version={new_version}\n")


if __name__ == "__main__":
    main()

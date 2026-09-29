"""Build the source distribution used to install the fig-brush plugin.

The plugin ZIP is deliberately separate from the Python wheel. This module
uses an explicit allowlist so a local run cannot accidentally package private
research data, generated Origin output, caches, or test fixtures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


PLUGIN_NAME = "fig-brush"

# Files that make up the plugin manifest and its public documentation. A
# missing optional file is simply skipped while a release is assembled.
ROOT_FILES = {
    ".mcp.json", "pyproject.toml", "README.md", "requirements.txt",
    "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "CITATION.cff",
    "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
    "MANIFEST.in",
}
PACKAGE_DIRS = {"fig_brush", "mcp_server", "origin_bridge"}
DATA_DIRS = {"plot_specs", "templates"}
DOC_DIRS = {"docs"}
SCRIPT_DIRS = {"scripts"}
SKILL_DIRS = {"skills"}

# Runtime and local evaluation material must never be copied to a release.
EXCLUDED_PARTS = {
    ".git", ".github", ".pytest_cache", ".pytest-tmp", ".venv", "venv",
    "env", "__pycache__", "outputs", "output", "artifacts", "dist", "build",
    "benchmarks", "benchmark", "private", "tests", "node_modules",
}
FORBIDDEN_EXTENSIONS = {
    ".opju", ".opj", ".otp", ".xls", ".xlsx", ".tsv", ".pdf", ".jpg",
    ".jpeg", ".gif", ".webp", ".svg",
}


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    return path.relative_to(root).parts


def is_allowed(path: Path, root: Path) -> bool:
    """Return whether *path* is safe to place in the plugin ZIP.

    The only raster image admitted is the synthetic example at the exact
    path ``examples/synthetic/reference.png``. Synthetic example data may use
    CSV/JSON/Markdown, but CSV files anywhere else are excluded.
    """
    if not path.is_file() or path.is_symlink():
        return False
    parts = _relative_parts(path, root)
    if not parts or any(part.lower() in EXCLUDED_PARTS for part in parts):
        return False
    relative = "/".join(parts)
    suffix = path.suffix.lower()
    if relative == "examples/synthetic/reference.png":
        return True
    if suffix in FORBIDDEN_EXTENSIONS or suffix in {".png", ".bmp", ".tif", ".tiff"}:
        return False
    if relative in ROOT_FILES or relative == ".codex-plugin/plugin.json":
        return True
    top = parts[0].lower()
    if top in PACKAGE_DIRS:
        return suffix == ".py"
    if top in DATA_DIRS:
        return suffix in {".py", ".json"}
    if top in DOC_DIRS:
        return suffix == ".md"
    if top in SCRIPT_DIRS:
        return suffix in {".py", ".ps1", ".md"}
    if top in SKILL_DIRS:
        return path.name.lower() == "skill.md"
    if top == "examples" and len(parts) >= 2 and parts[1].lower() == "synthetic":
        # This is the explicitly scoped synthetic example area. The image
        # exception above remains the only image exception.
        return suffix in {".csv", ".json", ".md", ".py", ".txt"}
    return False


def iter_allowed_files(root: Path):
    """Yield allowlisted files in deterministic order."""
    for path in sorted(root.rglob("*")):
        if is_allowed(path, root):
            yield path


def build_package(root: Path, dist: Path | None = None) -> tuple[Path, Path]:
    """Create ``dist/fig-brush-<version>.zip`` and its SHA-256 sidecar."""
    root = root.resolve()
    manifest_path = root / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    name = str(manifest.get("name", ""))
    version = str(manifest.get("version", ""))
    if name != PLUGIN_NAME:
        raise ValueError(f"Expected plugin name {PLUGIN_NAME!r}, got {name!r}")
    if not version:
        raise ValueError("plugin.json has no version")
    output_dir = (dist or (root / "dist")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{name}-{version}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    for existing in (archive, checksum):
        if existing.exists():
            existing.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in iter_allowed_files(root):
            relative = path.relative_to(root).as_posix()
            # Every member is rooted beneath the plugin name; no machine path
            # is ever written into the archive.
            bundle.write(path, f"{name}/{relative}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, checksum


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="plugin source root (default: repository root)")
    parser.add_argument("--dist", type=Path, help="output directory (default: <root>/dist)")
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    archive, checksum = build_package(root, args.dist)
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

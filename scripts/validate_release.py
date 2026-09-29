"""Validate public release metadata and scan for accidental private content.

This validator intentionally does not require a root-level ``plugin.json``.
The Codex plugin manifest lives at ``.codex-plugin/plugin.json``; a root
manifest may be added later without changing this release contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_NAME = "fig-brush"
EXPECTED_VERSION = "0.3.1"
EXPECTED_AUTHOR = "Petey Yu"

RUNTIME_EXCLUDED_DIRS = {
    ".git", ".pytest_cache", ".pytest-tmp", ".venv", "venv", "env",
    "__pycache__", "dist", "build", "outputs", "output", "artifacts",
    "benchmarks", "benchmark", "tests", "node_modules",
}
TEXT_SUFFIXES = {
    ".c", ".cfg", ".cff", ".cmd", ".css", ".csv", ".gitignore", ".ini",
    ".json", ".md", ".ps1", ".py", ".pyi", ".rst", ".toml", ".txt", ".yml",
    ".yaml", ".xml",
}
FORBIDDEN_ASSET_EXTENSIONS = {
    ".csv", ".tsv", ".xls", ".xlsx", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".bmp", ".tif", ".tiff", ".svg", ".pdf", ".opj", ".opju",
    ".otp",
}

# Construct the old product name in pieces so this validator does not flag
# its own source while scanning for stale references.
_OLD_NAME = "origin" + "-research" + "-plot"
_OLD_NAME_UNDERSCORE = "origin" + "_research" + "_plot"

# Build path fragments separately so the validator's own detector patterns do
# not look like a leaked path when this file is included in the source scan.
_DRIVE_ROOT = r"[a-z]:[\\/]" + r"(?:u" + "sers" + r"|documents and settings)[\\/]"
_HOME_ROOT = "/" + "home" + r"/[^/\s]+/"
_USERS_ROOT = "/" + "users" + r"/[^/\s]+/"
_ABSOLUTE_PATH_RE = re.compile(r"(?i)(?:" + _DRIVE_ROOT + "|" + _HOME_ROOT + "|" + _USERS_ROOT + ")")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_TOKEN_RE = re.compile(
    r"(?i)(?:ghp_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|xox[baprs]-[a-z0-9-]{12,}|sk-[a-z0-9]{20,}|AKIA[0-9A-Z]{16})"
)
_ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|secret[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{12,}"
)


def _toml_load(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:  # Python 3.10 uses the dev tomli extra.
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def iter_release_files(root: Path):
    """Yield text-like files while excluding runtime/generated directories."""
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part.lower() in RUNTIME_EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.lower() in {"license", "notice"}:
            yield path


def scan_release_tree(root: Path) -> list[str]:
    """Return findings for paths/secrets/stale names in public source files."""
    findings: list[str] = []
    # Scan all non-runtime paths once so binary/private assets are reported
    # even though they are not decoded as text below.
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative_path = path.relative_to(root)
        if any(part.lower() in RUNTIME_EXCLUDED_DIRS for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        suffix = path.suffix.lower()
        synthetic = relative.startswith("examples/synthetic/")
        if suffix in FORBIDDEN_ASSET_EXTENSIONS:
            allowed_synthetic = synthetic and (
                suffix == ".csv" or relative == "examples/synthetic/reference.png"
            )
            if not allowed_synthetic:
                findings.append(f"{relative}: forbidden release asset")
                continue
        if suffix not in TEXT_SUFFIXES and path.name.lower() not in {"license", "notice"}:
            continue
        text = _read_text(path)
        if not text:
            continue
        if _ABSOLUTE_PATH_RE.search(text):
            findings.append(f"{relative}: personal absolute path")
        if _PRIVATE_KEY_RE.search(text) or _TOKEN_RE.search(text) or _ASSIGNMENT_SECRET_RE.search(text):
            findings.append(f"{relative}: possible secret/token")
        if _OLD_NAME.lower() in text.lower() or _OLD_NAME_UNDERSCORE.lower() in text.lower():
            findings.append(f"{relative}: stale project name")
    return findings


def _require(errors: list[str], path: Path, label: str) -> str:
    if not path.is_file():
        errors.append(f"missing required {label}: {path.name}")
        return ""
    return _read_text(path)


def validate_metadata(root: Path) -> list[str]:
    """Validate plugin, MCP, Python, citation, and skill metadata."""
    errors: list[str] = []
    manifest_path = root / ".codex-plugin" / "plugin.json"
    manifest_text = _require(errors, manifest_path, ".codex-plugin/plugin.json")
    manifest: dict[str, Any] = {}
    if manifest_text:
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid plugin manifest JSON: {exc}")
    if manifest:
        if manifest.get("name") != EXPECTED_NAME:
            errors.append(f"plugin name must be {EXPECTED_NAME!r}")
        if str(manifest.get("version")) != EXPECTED_VERSION:
            errors.append(f"plugin version must be {EXPECTED_VERSION}")
        if manifest.get("license") != "Apache-2.0":
            errors.append("plugin license must be Apache-2.0")
        author = manifest.get("author", {})
        interface = manifest.get("interface", {})
        if author.get("name") != EXPECTED_AUTHOR:
            errors.append(f"plugin author must be {EXPECTED_AUTHOR!r}")
        if interface.get("developerName") != EXPECTED_AUTHOR:
            errors.append(f"plugin developerName must be {EXPECTED_AUTHOR!r}")

    mcp_text = _require(errors, root / ".mcp.json", ".mcp.json")
    if mcp_text:
        try:
            mcp = json.loads(mcp_text)
            server = mcp["mcpServers"][EXPECTED_NAME]
            command = str(server.get("command", "")).lower()
            args = [str(item).lower() for item in server.get("args", [])]
            if "powershell" not in command:
                errors.append(".mcp.json must launch scripts/run_mcp.ps1 through PowerShell")
            if not any("run_mcp.ps1" in item for item in args):
                errors.append(".mcp.json args must include scripts/run_mcp.ps1")
            if not (root / "scripts" / "run_mcp.ps1").is_file():
                errors.append("scripts/run_mcp.ps1 is missing")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            errors.append(f"invalid .mcp.json fig-brush server: {exc}")

    pyproject_path = root / "pyproject.toml"
    pyproject_text = _require(errors, pyproject_path, "pyproject.toml")
    if pyproject_text:
        try:
            project = _toml_load(pyproject_path).get("project", {})
            if project.get("name") != EXPECTED_NAME:
                errors.append(f"pyproject project.name must be {EXPECTED_NAME!r}")
            if str(project.get("version")) != EXPECTED_VERSION:
                errors.append(f"pyproject project.version must be {EXPECTED_VERSION}")
            authors = project.get("authors", [])
            if not any(str(author.get("name", "")) == EXPECTED_AUTHOR for author in authors):
                errors.append(f"pyproject authors must include {EXPECTED_AUTHOR!r}")
            license_value = project.get("license", "")
            if isinstance(license_value, dict):
                license_value = license_value.get("text", license_value.get("file", ""))
            if "Apache-2.0" not in str(license_value):
                errors.append("pyproject license must be Apache-2.0")
        except Exception as exc:  # tomllib errors differ between Python versions.
            errors.append(f"invalid pyproject.toml: {exc}")

    citation_text = _require(errors, root / "CITATION.cff", "CITATION.cff")
    if citation_text:
        if not re.search(r"(?m)^[ \t]*title:\s*.*fig-brush", citation_text, re.I):
            errors.append("CITATION.cff title must mention fig-brush")
        if not re.search(r"(?m)^[ \t]*version:\s*['\"]?0\.3\.1", citation_text):
            errors.append("CITATION.cff version must be 0.3.1")
        has_full_name = EXPECTED_AUTHOR.lower() in citation_text.lower()
        has_split_name = bool(
            re.search(r"(?m)^[ \t]*(?:-\s*)?family-names:\s*Yu\s*$", citation_text)
            and re.search(r"(?m)^[ \t]*(?:-\s*)?given-names:\s*Petey\s*$", citation_text)
        )
        if not (has_full_name or has_split_name):
            errors.append(f"CITATION.cff must credit {EXPECTED_AUTHOR}")

    skill_path = root / "skills" / "fig-brush" / "SKILL.md"
    skill_text = _require(errors, skill_path, "skills/fig-brush/SKILL.md")
    if skill_text:
        if not re.search(r"(?m)^name:\s*fig-brush\s*$", skill_text):
            errors.append("SKILL.md front matter name must be fig-brush")
        if EXPECTED_VERSION not in skill_text:
            errors.append("SKILL.md must mention version 0.3.1")

    _require(errors, root / "LICENSE", "LICENSE")
    _require(errors, root / "README.md", "README.md")
    return errors


def validate_release(root: Path) -> list[str]:
    root = root.resolve()
    errors = validate_metadata(root)
    errors.extend(scan_release_tree(root))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="release tree (default: repository root)")
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    errors = validate_release(root)
    ignored = ", ".join(sorted(RUNTIME_EXCLUDED_DIRS))
    print(f"Release scan excludes runtime/generated directories: {ignored}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Release metadata and source scan passed for {EXPECTED_NAME} {EXPECTED_VERSION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

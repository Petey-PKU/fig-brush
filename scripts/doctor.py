"""Check whether a local fig-brush installation is ready to run.

The doctor deliberately performs import and metadata checks only.  It does not
call ``originpro.new()``, ``originpro.open()``, ``originpro.exit()``, or any
other API that starts Origin or changes a project.

Exit codes
----------
``0`` means the screenshot-template path is ready.  Origin is an optional
local capability, so an unavailable Origin installation is reported as a
warning and still returns ``0``.  ``1`` means a required check failed (Python,
the plugin root, or a packaged dependency).  ``2`` is reserved for command
line usage errors.  Pass ``--require-origin`` when a calling script needs a
native Origin render and should treat the optional capability as required.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


# Make ``python scripts/doctor.py`` work from an extracted plugin directory.
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


# The import names differ for Pillow and the distribution metadata.
DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("Pillow", "PIL"),
    ("scipy", "scipy"),
    ("jsonschema", "jsonschema"),
    ("mcp", "mcp"),
)


@dataclass(frozen=True)
class CheckResult:
    """One human-readable and JSON-serializable diagnostic result."""

    name: str
    status: str
    detail: str
    required: bool = True

    @property
    def passed(self) -> bool:
        return self.status == "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "required": self.required,
        }


@dataclass(frozen=True)
class DoctorReport:
    """The complete result of :func:`run_doctor`."""

    plugin_root: Path
    checks: tuple[CheckResult, ...]
    screenshot_ready: bool
    origin_ready: bool
    exit_code: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin_root": str(self.plugin_root),
            "screenshot_ready": self.screenshot_ready,
            "origin_ready": self.origin_ready,
            "exit_code": self.exit_code,
            "checks": [check.as_dict() for check in self.checks],
        }


def _version_for(module: ModuleType, distribution: str) -> str | None:
    """Return a best-effort version without making it a required check."""

    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = getattr(module, "__version__", None)
        return str(version) if version else None


def _check_plugin_root(root: Path) -> CheckResult:
    if not root.exists() or not root.is_dir():
        return CheckResult(
            "plugin root",
            "error",
            f"directory does not exist: {root}",
        )

    manifest_path = root / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return CheckResult(
            "plugin root",
            "error",
            f"missing .codex-plugin/plugin.json under {root}",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return CheckResult("plugin root", "error", f"cannot read plugin manifest: {exc}")
    if not isinstance(manifest, dict) or not manifest.get("name"):
        return CheckResult("plugin root", "error", "plugin manifest has no name")
    version = manifest.get("version")
    if not version:
        return CheckResult("plugin root", "error", "plugin manifest has no version")
    return CheckResult(
        "plugin root",
        "ok",
        f"{manifest['name']} {version} ({root})",
    )


def _check_python() -> CheckResult:
    current = sys.version_info
    version = platform.python_version()
    if current < (3, 10):
        return CheckResult("Python", "error", f"{version}; Python 3.10 or newer is required")
    return CheckResult("Python", "ok", f"{version} (requires >= 3.10)")


def _check_dependency(distribution: str, module_name: str) -> CheckResult:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # ImportError and native DLL load errors are both useful here.
        reason = str(exc).strip() or exc.__class__.__name__
        return CheckResult(
            f"dependency: {distribution}",
            "error",
            f"import {module_name!r} failed: {reason}",
        )
    version = _version_for(module, distribution)
    suffix = f" {version}" if version else ""
    return CheckResult(f"dependency: {distribution}", "ok", f"imported {module_name!r}{suffix}")


def _check_origin(
    *,
    system_name: Callable[[], str] | None = None,
    importer: Callable[[str], ModuleType] | None = None,
) -> tuple[CheckResult, CheckResult, CheckResult, bool]:
    """Check the Origin platform, package import, and safe API entry points.

    ``originpro`` is imported only to inspect metadata and callable attributes.
    No Origin project is created, opened, saved, or closed by this function.
    """

    system_name = system_name or platform.system
    importer = importer or importlib.import_module
    system = system_name()
    if system.lower() != "windows":
        platform_result = CheckResult(
            "Origin platform",
            "warning",
            f"{system}; native Origin automation requires Windows",
            required=False,
        )
        package_result = CheckResult(
            "originpro import",
            "skipped",
            "skipped because the current platform is not Windows",
            required=False,
        )
        api_result = CheckResult(
            "Origin API entry points",
            "skipped",
            "skipped because the current platform is not Windows",
            required=False,
        )
        return platform_result, package_result, api_result, False

    platform_result = CheckResult("Origin platform", "ok", "Windows")
    try:
        module = importer("originpro")
    except Exception as exc:  # Includes missing package and DLL/license load errors.
        reason = str(exc).strip() or exc.__class__.__name__
        package_result = CheckResult(
            "originpro import",
            "warning",
            f"unavailable: {reason}",
            required=False,
        )
        api_result = CheckResult(
            "Origin API entry points",
            "skipped",
            "skipped because originpro could not be imported",
            required=False,
        )
        return platform_result, package_result, api_result, False

    version = _version_for(module, "originpro")
    detail = "imported"
    if version:
        detail += f" ({version})"
    package_result = CheckResult("originpro import", "ok", detail, required=False)
    required_entries = ("new", "open")
    missing = [name for name in required_entries if not callable(getattr(module, name, None))]
    if missing:
        api_result = CheckResult(
            "Origin API entry points",
            "warning",
            "originpro imported, but missing callable(s): " + ", ".join(missing),
            required=False,
        )
        return platform_result, package_result, api_result, False
    api_result = CheckResult(
        "Origin API entry points",
        "ok",
        "new() and open() are present; no project was started",
        required=False,
    )
    return platform_result, package_result, api_result, True


def run_doctor(
    plugin_root: str | Path | None = None,
    *,
    require_origin: bool = False,
    system_name: Callable[[], str] | None = None,
    importer: Callable[[str], ModuleType] | None = None,
) -> DoctorReport:
    """Run diagnostics and return a structured report.

    The injectable platform/importer arguments make the optional Origin branch
    testable without launching the commercial application.
    """

    system_name = system_name or platform.system
    importer = importer or importlib.import_module
    root = Path(plugin_root).expanduser().resolve() if plugin_root else PLUGIN_ROOT
    checks: list[CheckResult] = [_check_plugin_root(root), _check_python()]
    checks.extend(_check_dependency(distribution, module) for distribution, module in DEPENDENCIES)
    origin_platform, origin_package, origin_api, origin_ready = _check_origin(
        system_name=system_name,
        importer=importer,
    )
    checks.extend((origin_platform, origin_package, origin_api))

    required_failed = any(check.required and check.status == "error" for check in checks)
    screenshot_ready = not required_failed
    if require_origin and not origin_ready:
        required_failed = True
    exit_code = 1 if required_failed else 0
    return DoctorReport(
        plugin_root=root,
        checks=tuple(checks),
        screenshot_ready=screenshot_ready,
        origin_ready=origin_ready,
        exit_code=exit_code,
    )


def _print_text(report: DoctorReport) -> None:
    print("fig-brush doctor")
    for check in report.checks:
        label = check.status.upper()
        print(f"[{label}] {check.name}: {check.detail}")
    print(f"Screenshot preparation: {'ready' if report.screenshot_ready else 'unavailable'}")
    print(f"Native Origin rendering: {'ready' if report.origin_ready else 'unavailable'}")
    print(f"Exit code: {report.exit_code}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        help="plugin root containing .codex-plugin/plugin.json (default: parent of scripts/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON report instead of human-readable text",
    )
    parser.add_argument(
        "--require-origin",
        action="store_true",
        help="return exit code 1 unless native Origin automation is ready",
    )
    args = parser.parse_args(argv)
    report = run_doctor(args.plugin_root, require_origin=args.require_origin)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())


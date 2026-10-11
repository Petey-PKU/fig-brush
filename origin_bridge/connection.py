from __future__ import annotations

import importlib
import platform
from dataclasses import dataclass
from types import ModuleType
from typing import Any


class OriginBridgeError(RuntimeError):
    """Base error for failures in the local Origin bridge."""


class OriginUnavailableError(OriginBridgeError):
    """Raised when Origin or its originpro package cannot be used."""


class OriginStartupError(OriginBridgeError):
    """Raised when Origin Automation is installed but cannot finish startup."""


@dataclass
class OriginStatus:
    available: bool
    platform: str
    package_version: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "platform": self.platform,
            "package_version": self.package_version,
            "reason": self.reason,
        }


def _import_originpro() -> ModuleType:
    if platform.system().lower() != "windows":
        raise OriginUnavailableError(
            "Origin Automation requires Windows. The current platform is "
            f"{platform.system()}."
        )
    try:
        return importlib.import_module("originpro")
    except ImportError as exc:
        raise OriginUnavailableError(
            "The originpro package is unavailable. Install Origin 2021 or newer "
            "and install OriginLab's originpro package in this Python environment."
        ) from exc


def _startup_error(operation: str, exc: Exception) -> OriginStartupError:
    """Turn common UFF/COM startup failures into an actionable message."""
    detail = str(exc).strip() or exc.__class__.__name__
    lowered = detail.lower()
    startup_markers = (
        "invalid command",
        "lt_execute",
        "exception in originext",
        "access is denied",
        "winerror 5",
        "user files folder",
        "uff",
    )
    if any(marker in lowered for marker in startup_markers):
        hint = (
            "Origin Automation connected but did not finish startup. Complete the "
            "User Files Folder dialog once in the normal Origin desktop, then rerun "
            "fig-brush. The UFF is Origin configuration and is separate from the "
            "project output folder. Do not launch Origin64.exe with -d during normal "
            "generation because -d intentionally forces a new UFF. If this runs in a "
            "restricted sandbox, allow Origin COM/registry access or run the native "
            "render locally."
        )
    else:
        hint = (
            "Check that Origin is installed and licensed, that originpro matches the "
            "Origin version, and that the desktop process can access its user files "
            "folder."
        )
    return OriginStartupError(f"{operation} failed: {detail}. {hint}")


def origin_status() -> dict[str, Any]:
    try:
        module = _import_originpro()
    except OriginUnavailableError as exc:
        return OriginStatus(
            available=False,
            platform=platform.system(),
            reason=str(exc),
        ).as_dict()
    version = getattr(module, "__version__", None)
    return OriginStatus(
        available=True,
        platform=platform.system(),
        package_version=str(version) if version else None,
    ).as_dict()


class OriginSession:
    """Small lifecycle wrapper around the originpro project namespace."""

    def __init__(self, show: bool = False):
        self.show = show
        self.op: ModuleType | None = None

    def __enter__(self) -> ModuleType:
        self.op = _import_originpro()
        set_show = getattr(self.op, "set_show", None)
        try:
            if callable(set_show):
                set_show(self.show)
        except Exception as exc:
            raise _startup_error("Origin startup", exc) from exc
        new_project = getattr(self.op, "new", None)
        if not callable(new_project):
            raise OriginBridgeError("originpro does not expose project.new().")
        try:
            new_project()
        except Exception as exc:
            raise _startup_error("Origin project creation", exc) from exc
        return self.op

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.op is None:
            return
        # originpro has exposed exit() across supported versions, but do not turn a
        # successful render into an error if an older installation omits it.
        exit_origin = getattr(self.op, "exit", None)
        if callable(exit_origin):
            try:
                exit_origin()
            except Exception:
                # Cleanup must not mask the render or the original exception.
                pass


def open_origin_project(path: str, show: bool = False, asksave: bool = False) -> ModuleType:
    """Attach to Origin and open a project.

    ``asksave`` is kept explicit because automation that opens a reference
    project should be able to preserve a user's unsaved work.  Existing
    batch/render callers retain the historical no-prompt default; interactive
    bridges such as the native format clipboard pass ``asksave=True``.
    """
    op = _import_originpro()
    set_show = getattr(op, "set_show", None)
    try:
        if callable(set_show):
            set_show(show)
    except Exception as exc:
        raise _startup_error("Origin startup", exc) from exc
    open_project = getattr(op, "open", None)
    if not callable(open_project):
        raise OriginBridgeError("originpro does not expose project.open().")
    try:
        opened = open_project(path, readonly=False, asksave=asksave)
    except Exception as exc:
        raise _startup_error(f"Opening Origin project {path}", exc) from exc
    if not opened:
        raise OriginBridgeError(f"Origin could not open project: {path}")
    return op

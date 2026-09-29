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
        if callable(set_show):
            set_show(self.show)
        new_project = getattr(self.op, "new", None)
        if not callable(new_project):
            raise OriginBridgeError("originpro does not expose project.new().")
        new_project()
        return self.op

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.op is None:
            return
        # originpro has exposed exit() across supported versions, but do not turn a
        # successful render into an error if an older installation omits it.
        exit_origin = getattr(self.op, "exit", None)
        if callable(exit_origin):
            exit_origin()


def open_origin_project(path: str, show: bool = False) -> ModuleType:
    op = _import_originpro()
    set_show = getattr(op, "set_show", None)
    if callable(set_show):
        set_show(show)
    open_project = getattr(op, "open", None)
    if not callable(open_project):
        raise OriginBridgeError("originpro does not expose project.open().")
    if not open_project(path, readonly=False, asksave=False):
        raise OriginBridgeError(f"Origin could not open project: {path}")
    return op

"""Stage an Origin-native graph format in Origin's format clipboard.

Origin already has a native Copy Format/Paste Format workflow.  The
``FILE.OGS`` sections used by Origin's context menu compile and run the same
copy operation as the GUI, so this bridge can prepare the clipboard without
serializing the style into a second, Python-owned representation.

The function in this module intentionally leaves the Origin session open and
does not save or exit the source project.  A caller can then let the user
activate their target graph and choose Origin's normal right-click Paste
Format command.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .connection import OriginBridgeError, open_origin_project


FORMAT_CLIPBOARD_SCOPES: dict[str, str] = {
    "all": "FmtsCopyAll",
    "all_styles": "FmtsCopyAllStyles",
    "colors": "FmtsCopyColors",
    "fonts": "FmtsCopyFonts",
    "scales": "FmtsCopyScales",
    "dimensions": "FmtsCopyDimensions",
    "text": "FmtsCopyText",
    "background": "FmtsCopyBackground",
    "plot": "FmtsCopyPlot",
    "colormap": "FmtsCopyColormap",
}

_SCOPE_ALIASES = {
    "all styles": "all_styles",
    "style": "all_styles",
    "styles": "all_styles",
    "color": "colors",
    "font": "fonts",
    "scale": "scales",
    "dimension": "dimensions",
    "plots": "plot",
    "colour": "colors",
    "colourmap": "colormap",
}


def normalize_format_scope(scope: str) -> tuple[str, str]:
    """Return a canonical scope and its Origin ``FILE.OGS`` section."""
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError(
            "scope must be one of: " + ", ".join(FORMAT_CLIPBOARD_SCOPES)
        )
    canonical = scope.strip().lower().replace("-", "_")
    canonical = _SCOPE_ALIASES.get(canonical, canonical)
    section = FORMAT_CLIPBOARD_SCOPES.get(canonical)
    if section is None:
        raise ValueError(
            f"unsupported format clipboard scope {scope!r}; choose one of: "
            + ", ".join(FORMAT_CLIPBOARD_SCOPES)
        )
    return canonical, section


def _origin_graph(op: Any, graph_name: str | None) -> Any:
    finder = getattr(op, "find_graph", None)
    if not callable(finder):
        raise OriginBridgeError("originpro does not expose find_graph().")
    graph = finder(graph_name or "")
    if graph is None:
        target = f"{graph_name!r}" if graph_name else "the active window"
        raise OriginBridgeError(f"{target} is not an Origin graph.")
    activate = getattr(graph, "activate", None)
    if callable(activate):
        try:
            activate()
        except (AttributeError, RuntimeError, OSError) as exc:
            raise OriginBridgeError("Origin could not activate the reference graph.") from exc
    return graph


def stage_format_clipboard(
    reference_project_path: str,
    graph_name: str | None = None,
    scope: str = "all",
    show_origin: bool = True,
) -> dict[str, Any]:
    """Copy a reference graph's native format into Origin's format clipboard.

    ``reference_project_path`` must point to an existing ``.opju`` or ``.opj``
    project.  The source project is opened in the connected Origin session,
    its selected graph is activated, and ``FILE.OGS``'s ``FmtsCopy*`` section
    is executed.  The Origin process remains attached so the user can switch
    to their own graph and use the built-in Paste Format context menu.
    """
    source = Path(reference_project_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"reference Origin project does not exist: {source}")
    if source.suffix.lower() not in {".opju", ".opj"}:
        raise ValueError("reference_project_path must be an .opju or .opj file")
    canonical_scope, section = normalize_format_scope(scope)

    # Ask Origin before replacing a currently open project so a user's
    # unsaved target graph cannot be discarded as a side effect of staging.
    op = open_origin_project(str(source), show=show_origin, asksave=True)
    graph = _origin_graph(op, graph_name)

    # Omitting the FILE.OGS filename is deliberate.  Origin resolves the
    # built-in FILE.OGS in its installation folder, matching its own menu
    # commands.  FmtsCopy* calls PrepareCopyFormats and then Origin C's
    # CopyFormat* implementation, which writes Origin's internal format
    # clipboard (not the Windows text/image clipboard).
    execute = getattr(op, "lt_exec", None)
    if not callable(execute):
        raise OriginBridgeError("originpro does not expose lt_exec().")
    script = f"run.section(,{section});"
    try:
        result = execute(script)
    except (AttributeError, RuntimeError, OSError, TypeError, ValueError) as exc:
        raise OriginBridgeError(
            f"Origin could not stage the {canonical_scope} format clipboard."
        ) from exc
    if result is False:
        raise OriginBridgeError(
            f"Origin rejected the {canonical_scope} format clipboard command."
        )

    graph_label = str(getattr(graph, "name", graph_name or ""))
    warnings = [
        "The reference project remains open in Origin and was not saved.",
        "Origin's format clipboard is session-local; keep Origin open until the target graph is pasted.",
    ]
    if canonical_scope in {"plot", "text", "colormap"}:
        warnings.append(
            "This scope follows Origin's current selection; select the matching plot or graph object in the reference graph before staging."
        )
    return {
        "status": "staged",
        "mode": "origin_format_clipboard",
        "reference_project": str(source),
        "graph": graph_label,
        "scope": canonical_scope,
        "origin_section": section,
        "clipboard": "origin_format",
        "saved": False,
        "origin_closed": False,
        "instructions": [
            "Switch to the target graph in Origin.",
            "Right-click the target graph or plot and choose Paste Format.",
            "Use Paste Format To or Paste Format (Advanced) when only selected properties are wanted.",
        ],
        "warnings": warnings,
    }


__all__ = [
    "FORMAT_CLIPBOARD_SCOPES",
    "normalize_format_scope",
    "stage_format_clipboard",
]

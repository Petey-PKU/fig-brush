"""Apply a format-brush parameter bundle to an existing Origin project.

The screenshot reader intentionally emits a small, data-free JSON file.  This
module is the bridge between that file and a user's already editable graph:
the input project is opened, page/layer/axis appearance is updated, and a new
``*_formatted.opju`` copy is written.  Plot values, axis limits, labels, and
series colours are left alone because a screenshot cannot safely infer those
from pixels alone.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .connection import OriginBridgeError, _import_originpro, open_origin_project
from .styles import apply_layer_style, apply_page_style


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _side_options(value: Any) -> bool | dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, bool):
        return value
    return bool(value)


def format_parameters_to_style(parameters: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Translate ``format_parameters.json`` into the existing style API.

    The returned style is deliberately conservative: it contains only page,
    layer, axis, and typography fields.  Missing or non-numeric measurements
    are skipped and reported as warnings instead of becoming Origin defaults.
    """
    if not isinstance(parameters, dict):
        raise ValueError("format parameters must be a JSON object")
    if parameters.get("kind") not in {None, "origin_format_parameters"}:
        raise ValueError("unsupported format parameter kind")

    warnings: list[str] = []
    canvas = parameters.get("canvas") or {}
    frame = parameters.get("plot_frame") or {}
    axes = parameters.get("axes") or {}
    typography = parameters.get("typography") or {}
    style: dict[str, Any] = {}

    ratio = _number(canvas.get("page_aspect_ratio", canvas.get("aspect_ratio")))
    if ratio is not None and float(ratio) > 0:
        style["page_aspect_ratio"] = float(ratio)
    width = _number(canvas.get("width_px"))
    if width is not None and float(width) > 0:
        style["page_width_px"] = int(round(float(width)))

    margins = frame.get("margins_percent") or {}
    if isinstance(margins, dict):
        values = {key: _number(margins.get(key)) for key in ("left", "top", "right", "bottom")}
        if all(value is not None for value in values.values()):
            style["plot_frame"] = {key: float(value) for key, value in values.items()}
        elif margins:
            warnings.append("incomplete plot_frame.margins_percent was skipped")
    sides = frame.get("sides")
    if isinstance(sides, dict):
        # Hiding an existing axis is a destructive visual change. The reader
        # emits ``frame_side_detected`` evidence, so only trust an all-false
        # result when geometry confidence is reasonably high. A low-confidence
        # screenshot still gets page/margin/axis typography applied.
        confidence = parameters.get("confidence") if isinstance(parameters.get("confidence"), dict) else {}
        try:
            geometry_confidence = float(confidence.get("geometry", 1) or 0)
        except (TypeError, ValueError):
            geometry_confidence = 0.0
        visible_side = any(bool(value.get("show", value.get("visible", False))) if isinstance(value, dict) else bool(value) for value in sides.values())
        if visible_side or geometry_confidence >= 0.75:
            style["frame_sides"] = {key: _side_options(value) for key, value in sides.items() if key in {"top", "right", "bottom", "left"}}
        elif sides:
            warnings.append("low-confidence frame side detection was skipped to avoid hiding existing axes")

    for axis_name in ("x", "y"):
        source = axes.get(axis_name) or {}
        if not isinstance(source, dict):
            continue
        target: dict[str, Any] = {}
        for key in ("scale", "tick_direction", "show_labels"):
            if source.get(key) is not None:
                target[key] = source[key]
        aliases = {
            "major_tick_count": "major_tick_count",
            "minor_tick_count": "minor_tick_count",
            "major_tick_length_pt_96dpi": "major_tick_length",
            "minor_tick_length_pt_96dpi": "minor_tick_length",
            "frame_line_width_pt_96dpi": "axis_line_width",
        }
        for source_key, target_key in aliases.items():
            value = _number(source.get(source_key))
            if value is not None:
                target[target_key] = value
        if target:
            style.setdefault("axes", {})[axis_name] = target

    base_font = _number(typography.get("base_font_pt"))
    if base_font is not None and float(base_font) > 0:
        style["tick_label_font_pt"] = float(base_font)
        style["axis_title_font_pt"] = float(base_font)
    if typography.get("font_family"):
        # Origin's font property differs by object/version. Keep this as a
        # warning until a native, version-stable setter is available.
        warnings.append("font_family is reported for manual review; Origin font family was not changed")

    review = parameters.get("review") if isinstance(parameters.get("review"), dict) else {}
    if review.get("required"):
        warnings.append("reference analysis marked some measurements for visual review")
    warnings.append("series colours, labels, and axis limits were preserved from the input project")
    return style, warnings


def load_format_parameters(path_or_parameters: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Load and minimally validate a format parameter JSON file."""
    if isinstance(path_or_parameters, dict):
        return path_or_parameters
    path = Path(path_or_parameters).expanduser().resolve()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read format parameters: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid format parameters JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("format parameters JSON must contain an object")
    return value


def apply_format_to_project(
    project_path: str,
    format_parameters: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    *,
    graph_name: str | None = None,
    show_origin: bool = False,
    export_preview: bool = True,
) -> dict[str, Any]:
    """Apply a format bundle and save a new editable OPJU copy.

    ``output_path`` defaults to ``<input-stem>_formatted.opju``.  Refusing an
    in-place save is intentional: users can always compare or discard the
    generated copy without risking their original project.
    """
    source = Path(project_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Origin project does not exist: {source}")
    params = load_format_parameters(format_parameters)
    style, warnings = format_parameters_to_style(params)
    destination = (
        Path(output_path).expanduser().resolve()
        if output_path
        else source.with_name(f"{source.stem}_formatted.opju")
    )
    if destination == source:
        raise ValueError("output_path must differ from the input project")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Remove a previous generated copy so a failed Save cannot accidentally
    # make an old OPJU look like a successful result.
    try:
        destination.unlink(missing_ok=True)
    except OSError as exc:
        raise ValueError(f"cannot replace output project: {destination}") from exc

    op = open_origin_project(str(source), show=show_origin)
    selected: list[Any] = []
    applied_pages: list[dict[str, Any]] = []
    try:
        graph_list = getattr(op, "graph_list", None)
        if not callable(graph_list):
            raise OriginBridgeError("originpro does not expose graph_list().")
        pages = list(graph_list("p"))
        if graph_name:
            selected = [page for page in pages if str(getattr(page, "name", "")) == str(graph_name)]
            if not selected:
                raise ValueError(f"graph page not found: {graph_name}")
        else:
            selected = pages
        if not selected:
            raise ValueError("Origin project contains no graph pages")

        layer_style_spec = {"style": style, "axes": style.pop("axes", {})}
        for page in selected:
            applied: list[str] = []
            applied.extend(apply_page_style(page, style))
            try:
                layer = page[0]
            except (AttributeError, IndexError, KeyError, TypeError):
                layer = None
            if layer is None:
                warnings.append(f"graph page {getattr(page, 'name', '<unnamed>')} has no accessible layer")
            else:
                applied.extend(apply_layer_style(layer, layer_style_spec))
            applied_pages.append({"name": str(getattr(page, "name", "")), "applied": applied})

        save = getattr(op, "save", None)
        if not callable(save):
            raise OriginBridgeError("originpro does not expose project.save().")
        saved = bool(save(str(destination)))
        after = (destination.stat().st_size, destination.stat().st_mtime_ns) if destination.exists() else None
        if not saved and after is None:
            raise OriginBridgeError(f"Origin failed to save formatted project: {destination}")

        preview_path: Path | None = None
        if export_preview and selected:
            preview_path = destination.with_name(f"{destination.stem}_preview.png")
            save_fig = getattr(selected[0], "save_fig", None)
            if callable(save_fig):
                try:
                    if not save_fig(str(preview_path), type="png", replace=True, width=int(style.get("page_width_px", 1600))):
                        preview_path = None
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    preview_path = None
            if preview_path is None:
                warnings.append("preview export was unavailable; the OPJU was still saved")
        result: dict[str, Any] = {
            "status": "applied",
            "project": str(source),
            "output_project": str(destination),
            "format_parameters": str(Path(format_parameters).expanduser().resolve()) if isinstance(format_parameters, (str, Path)) else None,
            "pages": applied_pages,
            "warnings": warnings,
        }
        if preview_path is not None and preview_path.is_file():
            result["preview"] = str(preview_path)
        return result
    finally:
        close = getattr(op, "exit", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def apply_format_to_active_graph(
    format_parameters: str | Path | dict[str, Any],
    *,
    graph_name: str | None = None,
    layer_index: int | None = None,
    show_origin: bool = True,
    export_preview_path: str | Path | None = None,
) -> dict[str, Any]:
    """Apply a format bundle to the graph already active in Origin.

    This is the native-app entry point for a future Origin context-menu command.
    It deliberately attaches to the existing Origin process and never opens,
    saves, or exits a project.  The active graph and active layer stay editable
    in the user's current session; saving remains an explicit Origin action.

    ``layer_index`` is zero based.  When omitted, the graph's current
    ``page.active`` layer is selected, which matches Origin's active layer in
    the UI.  ``graph_name`` is optional and is mainly useful for automation;
    the default is the graph that currently has focus.
    """
    params = load_format_parameters(format_parameters)
    style, warnings = format_parameters_to_style(params)
    op = _import_originpro()
    set_show = getattr(op, "set_show", None)
    if callable(set_show):
        try:
            set_show(show_origin)
        except Exception:
            # Showing an existing Origin window is a convenience only.  A
            # connected session can still apply the style when this setter is
            # absent or unsupported by an older originpro build.
            pass

    finder = getattr(op, "find_graph", None)
    if not callable(finder):
        raise OriginBridgeError("originpro does not expose find_graph().")
    graph = finder(graph_name or "")
    if graph is None:
        target = f"{graph_name!r}" if graph_name else "the active window"
        raise OriginBridgeError(f"{target} is not an active Origin graph.")

    # Origin's page.active property is one based.  Keep the conversion here
    # instead of assuming layer 1 so multi-layer panels receive the format at
    # the same layer the user right-clicked.
    if layer_index is None:
        try:
            layer_index = int(graph.get_int("active")) - 1
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            layer_index = 0
    try:
        layer_count = len(graph)
    except (TypeError, AttributeError):
        layer_count = 0
    if layer_index < 0 or (layer_count and layer_index >= layer_count):
        raise ValueError(f"active graph layer index is out of range: {layer_index}")
    try:
        layer = graph[layer_index]
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise OriginBridgeError(f"cannot access graph layer {layer_index + 1}") from exc

    applied = apply_page_style(graph, style)
    layer_style_spec = {"style": style, "axes": style.get("axes", {})}
    applied.extend(apply_layer_style(layer, layer_style_spec))

    result: dict[str, Any] = {
        "status": "applied",
        "mode": "active_graph",
        "graph": str(getattr(graph, "name", graph_name or "")),
        "layer_index": int(layer_index),
        "format_parameters": str(Path(format_parameters).expanduser().resolve()) if isinstance(format_parameters, (str, Path)) else None,
        "applied": applied,
        "warnings": warnings,
        "saved": False,
        "save_note": "The active Origin project was not saved; use Origin's Save command when ready.",
    }
    if export_preview_path is not None:
        save_fig = getattr(graph, "save_fig", None)
        if not callable(save_fig):
            result["warnings"].append("preview export is unavailable for this Origin build")
        else:
            preview_path = Path(export_preview_path).expanduser().resolve()
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                generated = save_fig(str(preview_path), type="png", replace=True)
                if generated and preview_path.is_file():
                    result["preview"] = str(preview_path)
                else:
                    result["warnings"].append("preview export did not produce a file")
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                result["warnings"].append("preview export failed; format was applied")
    return result


__all__ = [
    "apply_format_to_active_graph",
    "apply_format_to_project",
    "format_parameters_to_style",
    "load_format_parameters",
]

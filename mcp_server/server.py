from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp_server.annotations import resolve_annotations
from mcp_server.data_inspector import inspect_dataset
from mcp_server.inference import infer_plot_spec
from mcp_server.layout import resolve_layout
from mcp_server.paths import InputValidationError, json_safe, write_json
from mcp_server.reference import inspect_reference
from mcp_server.replacement import refresh_reference_spec
from mcp_server.verification import create_data_manifest, validate_plot_spec, verify_origin_project
from mcp_server.template import compare_reference, prepare_template, validate_template, verify_template
from mcp_server.format_brush import analyze_format
from origin_bridge.connection import OriginBridgeError, OriginStartupError, OriginUnavailableError, origin_status
from origin_bridge.exporter import export_preview, render_project, render_reference_template
from origin_bridge.format_clipboard import stage_format_clipboard as stage_origin_format_clipboard
from origin_bridge.style_apply import apply_format_to_active_graph, apply_format_to_project
from origin_bridge.workbook import choose_table


def _as_dict(payload: dict[str, Any] | str | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"Expected JSON object, got invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InputValidationError("Expected a JSON object.")
    return value


def inspect_reference_tool(image_path: str, user_notes: str = "") -> dict[str, Any]:
    try:
        return inspect_reference(image_path, user_notes)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def inspect_dataset_tool(data_path: str) -> dict[str, Any]:
    try:
        return inspect_dataset(data_path)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def infer_plot_spec_tool(
    reference: dict[str, Any] | str | None,
    inventory: dict[str, Any] | str,
    user_notes: str = "",
) -> dict[str, Any]:
    try:
        return infer_plot_spec(_as_dict(reference), _as_dict(inventory) or {}, user_notes)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def render_origin_project_tool(
    data_path: str,
    plot_spec: dict[str, Any] | str,
    output_dir: str,
    table_name: str | None = None,
    show_origin: bool = False,
) -> dict[str, Any]:
    try:
        spec = _as_dict(plot_spec) or {}
        errors = validate_plot_spec(spec)
        if errors:
            return {"status": "error", "error": "PlotSpec validation failed.", "details": errors}
        spec = resolve_layout(spec)
        # Resolve semantic peak callouts against the actual data before saving
        # plot_spec.json, so the audit artifact records the coordinates that
        # were rendered rather than screenshot coordinates from the reference.
        frame = choose_table(data_path, table_name)
        spec = resolve_annotations(spec, frame)
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "plot_spec.json", spec)
        manifest = create_data_manifest(data_path, spec, output)
        result = render_project(data_path, spec, output, table_name, show_origin)
        result["plot_spec"] = str(output / "plot_spec.json")
        result["data_manifest"] = str(output / "data_manifest.json")
        return json_safe(result)
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except OriginStartupError as exc:
        return {"status": "error", "error_type": "origin_startup", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


def verify_origin_project_tool(
    project_path: str,
    plot_spec: dict[str, Any] | str,
    data_path: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    try:
        spec = _as_dict(plot_spec) or {}
        return verify_origin_project(project_path, spec, data_path, output_dir)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def export_origin_preview_tool(
    project_path: str,
    output_dir: str,
    formats: list[str] | None = None,
) -> dict[str, Any]:
    try:
        return export_preview(project_path, output_dir, formats)
    except (OriginUnavailableError, OriginStartupError, OriginBridgeError, OSError) as exc:
        error_type = "origin_startup" if isinstance(exc, OriginStartupError) else None
        payload = {"status": "error", "error": str(exc)}
        if error_type:
            payload["error_type"] = error_type
        return payload


def origin_status_tool() -> dict[str, Any]:
    return origin_status()


def prepare_reference_template_tool(
    image_path: str,
    template_spec: dict[str, Any] | str,
    output_dir: str,
    show_origin: bool = False,
    render_origin: bool = False,
) -> dict[str, Any]:
    """Prepare a visual format brush and optionally render native Origin files.

    ``template_spec`` is the structured visual reading supplied by the calling
    model after inspecting the image; it contains no user/private dataset. The
    native render returns a reusable ``style_template.otpu`` first and keeps
    the synthetic ``result.opju`` only as a companion preview. Native render
    is opt-in (`render_origin=True`) so screenshot analysis does not repeatedly
    open Origin or trigger its User Files Folder dialog.
    """
    try:
        spec = _as_dict(template_spec) or {}
        prepared = prepare_template(image_path, spec, output_dir)
        if not render_origin:
            prepared["status"] = "prepared"
            prepared["render_deferred"] = True
            return json_safe(prepared)
        result = render_reference_template(prepared["spec"], output_dir, show_origin)
        if result.get("style_template_status") == "unavailable":
            result["status"] = "partial"
        prepared.update(result)
        return json_safe(prepared)
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except OriginStartupError as exc:
        return {"status": "error", "error_type": "origin_startup", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


def refresh_reference_template_tool(
    template_spec_path: str,
    input_dir: str,
    output_dir: str,
    show_origin: bool = False,
) -> dict[str, Any]:
    """Rebuild the styled Origin project from local replacement tables."""
    try:
        spec_path = Path(template_spec_path).expanduser().resolve()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        refreshed = refresh_reference_spec(spec, input_dir)
        result = render_reference_template(refreshed, output_dir, show_origin)
        if result.get("style_template_status") == "unavailable":
            result["status"] = "partial"
        result["template_spec"] = str(spec_path)
        result["input_dir"] = str(Path(input_dir).expanduser().resolve())
        result["replacement_applied"] = refreshed.get("replacement_applied", {})
        return json_safe(result)
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except OriginStartupError as exc:
        return {"status": "error", "error_type": "origin_startup", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}


def format_brush(
    image_path: str,
    output_dir: str | None = None,
    user_notes: str = "",
    template_spec: dict[str, Any] | str | None = None,
    render_origin: bool = False,
    show_origin: bool = False,
) -> dict[str, Any]:
    """Run the compact reference-image-to-format-parameters workflow.

    The default result is ``format_parameters.json``, the auditable
    ``reference_analysis.json``, and a short ``APPLY_FORMAT.md`` checklist;
    users should open the checklist first. If ``output_dir`` is omitted, a sibling
    ``<image-name>_format_brush`` folder is used. Supplying a completed
    TemplateSpec enables the existing optional native Origin export; no
    research data is required for either path.
    """
    try:
        if not output_dir:
            image = Path(image_path).expanduser().resolve()
            output_dir = str(image.with_name(f"{image.stem}_format_brush"))
        result = analyze_format(image_path, output_dir, user_notes)
        if template_spec is None:
            return result
        spec = _as_dict(template_spec) or {}
        prepared = prepare_reference_template_tool(
            image_path,
            spec,
            output_dir,
            show_origin=show_origin,
            render_origin=render_origin,
        )
        if prepared.get("status") == "error":
            result.update({"template": prepared})
            return result
        result["template"] = prepared
        result["template_spec"] = prepared.get("template_spec")
        result["style_manifest"] = prepared.get("style_manifest")
        if render_origin:
            result["native_origin"] = True
        return result
    except (InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


# Python callers from the first compact workflow draft can keep using the
# explicit ``*_tool`` name, while MCP exposes the shorter user-facing names.
format_brush_tool = format_brush


def apply_format(
    project_path: str,
    format_parameters_path: str,
    output_path: str | None = None,
    graph_name: str | None = None,
    show_origin: bool = False,
) -> dict[str, Any]:
    """Apply ``format_parameters.json`` to an existing OPJU safely.

    The result is a new ``*_formatted.opju`` copy unless ``output_path`` is
    supplied.  User data, labels, limits, and series colours are preserved;
    only measured page/layer/axis appearance is changed.
    """
    try:
        return apply_format_to_project(
            project_path,
            format_parameters_path,
            output_path,
            graph_name=graph_name,
            show_origin=show_origin,
        )
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except OriginStartupError as exc:
        return {"status": "error", "error_type": "origin_startup", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


apply_format_tool = apply_format


def apply_active_format(
    format_parameters_path: str,
    graph_name: str | None = None,
    layer_index: int | None = None,
    show_origin: bool = True,
    preview_path: str | None = None,
) -> dict[str, Any]:
    """Paste a format bundle onto the graph currently active in Origin.

    This connects to the existing Origin process, changes visual properties,
    and leaves project saving to the user. It never opens or replaces an OPJU.
    """
    try:
        return json_safe(
            apply_format_to_active_graph(
                format_parameters_path,
                graph_name=graph_name,
                layer_index=layer_index,
                show_origin=show_origin,
                export_preview_path=preview_path,
            )
        )
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except OriginStartupError as exc:
        return {"status": "error", "error_type": "origin_startup", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


apply_active_format_tool = apply_active_format


def stage_format_clipboard(
    reference_project_path: str,
    graph_name: str | None = None,
    scope: str = "all",
    show_origin: bool = True,
) -> dict[str, Any]:
    """Prepare Origin's native format clipboard from a reference OPJU/OPJ.

    The Origin process stays open so the user can switch to their project and
    use the built-in right-click Paste Format command. No project is saved or
    replaced by this operation.
    """
    try:
        return json_safe(
            stage_origin_format_clipboard(
                reference_project_path,
                graph_name=graph_name,
                scope=scope,
                show_origin=show_origin,
            )
        )
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except OriginStartupError as exc:
        return {"status": "error", "error_type": "origin_startup", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


stage_format_clipboard_tool = stage_format_clipboard


def compare_reference_tool(reference_path: str, preview_path: str, output_dir: str) -> dict[str, Any]:
    try:
        return compare_reference(reference_path, preview_path, output_dir)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def verify_reference_template_tool(output_dir: str) -> dict[str, Any]:
    try:
        return verify_template(output_dir)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised when optional MCP dependency is absent
    FastMCP = None  # type: ignore[assignment,misc]


if FastMCP is not None:
    mcp = FastMCP("fig-brush")
    mcp.tool()(format_brush)
    mcp.tool()(apply_format)
    mcp.tool()(apply_active_format)
    mcp.tool()(stage_format_clipboard)
    mcp.tool()(inspect_reference_tool)
    mcp.tool()(origin_status_tool)
    mcp.tool()(prepare_reference_template_tool)
    mcp.tool()(compare_reference_tool)
    mcp.tool()(verify_reference_template_tool)
    # Keep the older data-driven/replacement API available to local callers
    # without making it part of the default format-brush surface.  Existing
    # integrations can opt in explicitly when they need those tools.
    if os.getenv("FIG_BRUSH_ENABLE_LEGACY_TOOLS", "").strip().lower() in {"1", "true", "yes"}:
        mcp.tool()(inspect_dataset_tool)
        mcp.tool()(infer_plot_spec_tool)
        mcp.tool()(render_origin_project_tool)
        mcp.tool()(verify_origin_project_tool)
        mcp.tool()(export_origin_preview_tool)
        mcp.tool()(refresh_reference_template_tool)
else:
    mcp = None


def main() -> int:
    if mcp is None:
        print(
            "The MCP dependency is not installed. Run: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

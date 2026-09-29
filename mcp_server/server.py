from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp_server.annotations import resolve_annotations
from mcp_server.data_inspector import inspect_dataset
from mcp_server.inference import infer_plot_spec
from mcp_server.layout import resolve_layout
from mcp_server.paths import InputValidationError, json_safe, write_json
from mcp_server.reference import inspect_reference
from mcp_server.verification import create_data_manifest, validate_plot_spec, verify_origin_project
from mcp_server.template import compare_reference, prepare_template, validate_template, verify_template
from origin_bridge.connection import OriginBridgeError, OriginUnavailableError, origin_status
from origin_bridge.exporter import export_preview, render_project, render_reference_template
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
    except (OriginUnavailableError, OriginBridgeError, OSError) as exc:
        return {"status": "error", "error": str(exc)}


def origin_status_tool() -> dict[str, Any]:
    return origin_status()


def prepare_reference_template_tool(
    image_path: str,
    template_spec: dict[str, Any] | str,
    output_dir: str,
    show_origin: bool = False,
    render_origin: bool = True,
) -> dict[str, Any]:
    """Prepare an editable template and optionally render it in Origin.

    ``template_spec`` is the structured visual reading supplied by the calling
    model after inspecting the image; it contains no user/private dataset.
    Set ``render_origin=False`` during fast analysis iterations to write the
    spec and replacement manifest without starting Origin; render once after
    the visual contract is settled.
    """
    try:
        spec = _as_dict(template_spec) or {}
        prepared = prepare_template(image_path, spec, output_dir)
        if not render_origin:
            prepared["status"] = "prepared"
            prepared["render_deferred"] = True
            return json_safe(prepared)
        result = render_reference_template(prepared["spec"], output_dir, show_origin)
        prepared.update(result)
        return json_safe(prepared)
    except OriginUnavailableError as exc:
        return {"status": "error", "error_type": "origin_unavailable", "error": str(exc)}
    except (OriginBridgeError, InputValidationError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}


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
    mcp.tool()(inspect_reference_tool)
    mcp.tool()(inspect_dataset_tool)
    mcp.tool()(infer_plot_spec_tool)
    mcp.tool()(render_origin_project_tool)
    mcp.tool()(verify_origin_project_tool)
    mcp.tool()(export_origin_preview_tool)
    mcp.tool()(origin_status_tool)
    mcp.tool()(prepare_reference_template_tool)
    mcp.tool()(compare_reference_tool)
    mcp.tool()(verify_reference_template_tool)
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

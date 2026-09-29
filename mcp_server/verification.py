from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data_inspector import inspect_dataset
from .paths import InputValidationError, json_safe, sha256_file, write_json
from .reference import inspect_reference
from origin_bridge.connection import OriginBridgeError, OriginUnavailableError, open_origin_project


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "plot_specs" / "schema.json"


def validate_plot_spec(plot_spec: dict[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema is not installed; structural validation was skipped."]
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    return [error.message for error in Draft202012Validator(schema).iter_errors(plot_spec)]


def _annotation_geometry_check(plot_spec: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    annotations = plot_spec.get("annotations", {}) or {}
    labels = annotations.get("text_labels", annotations.get("labels", [])) if isinstance(annotations, dict) else []
    lines = annotations.get("lines", []) if isinstance(annotations, dict) else []
    markers = [item for item in lines if isinstance(item, dict) and item.get("role") == "peak_marker"]
    if not markers:
        return True, {"markers": 0}
    label = next((item for item in labels if isinstance(item, dict) and item.get("role") == "peak_value"), None)
    errors: list[str] = []
    for marker in markers:
        try:
            if abs(float(marker["y1"]) - float(marker["y2"])) > 1e-9:
                errors.append("peak marker line is not horizontal")
            if not float(marker["x2"]) > float(marker["x1"]):
                errors.append("peak marker line has no positive span")
            if label is not None:
                if str(label.get("align", "")).lower() not in {"center", "middle"}:
                    errors.append("peak value label is not centered")
                if abs(float(label["x"]) - float(marker["anchor_x"])) > 1e-6:
                    errors.append("peak value label is not aligned to marker anchor")
        except (KeyError, TypeError, ValueError):
            errors.append("peak marker contains invalid coordinates")
    return not errors, {"markers": len(markers), "errors": errors}


def create_data_manifest(data_path: str, plot_spec: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    inventory = inspect_dataset(data_path)
    manifest = {
        "manifest_version": "1.0",
        "source": {
            "file": inventory["file"],
            "sha256": inventory["sha256"],
            "suffix": inventory["suffix"],
        },
        "tables": inventory["tables"],
        "mapping": plot_spec.get("data_mapping", {}),
        "statistics": plot_spec.get("statistics", {}),
        "interpretation": plot_spec.get("interpretation", {}),
        "warnings": inventory.get("warnings", []),
    }
    write_json(Path(output_dir) / "data_manifest.json", manifest)
    return manifest


def verify_origin_project(
    project_path: str,
    plot_spec: dict[str, Any],
    data_path: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(project_path).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    schema_errors = validate_plot_spec(plot_spec)
    checks.append({"name": "plot_spec_schema", "passed": not schema_errors, "details": schema_errors})
    annotation_ok, annotation_details = _annotation_geometry_check(plot_spec)
    checks.append({"name": "plot_spec_annotation_geometry", "passed": annotation_ok, "details": annotation_details})
    checks.append({"name": "project_exists", "passed": path.is_file(), "details": str(path)})
    if path.is_file():
        checks.append({"name": "project_extension", "passed": path.suffix.lower() == ".opju", "details": path.suffix})
        checks.append({"name": "project_sha256", "passed": True, "details": sha256_file(path)})

    if data_path:
        try:
            inventory = inspect_dataset(data_path)
            mapping = plot_spec.get("data_mapping", {}) or {}
            table_name = mapping.get("table")
            table_names = [table["name"] for table in inventory["tables"]]
            checks.append(
                {
                    "name": "source_table_available",
                    "passed": not table_name or table_name in table_names,
                    "details": {"requested": table_name, "available": table_names},
                }
            )
        except (InputValidationError, OSError) as exc:
            checks.append({"name": "source_data_readable", "passed": False, "details": str(exc)})

    style = plot_spec.get("style", {}) or {}
    expected_ratio = style.get("page_aspect_ratio")
    if output_dir and expected_ratio:
        preview_dir = Path(output_dir).expanduser().resolve()
        preview = next((preview_dir / f"preview.{ext}" for ext in ("png", "jpg", "jpeg") if (preview_dir / f"preview.{ext}").is_file()), None)
        if preview:
            try:
                from PIL import Image

                with Image.open(preview) as image:
                    actual_ratio = image.width / max(1, image.height)
                relative_error = abs(actual_ratio - float(expected_ratio)) / float(expected_ratio)
                checks.append(
                    {
                        "name": "preview_aspect_ratio",
                        "passed": relative_error <= 0.12,
                        "details": {"expected": expected_ratio, "actual": round(actual_ratio, 4), "relative_error": round(relative_error, 4)},
                    }
                )
                expected_frame = style.get("plot_frame") or {}
                expected_sides = style.get("frame_sides") or {}
                if isinstance(expected_frame, dict) and all(
                    key in expected_frame for key in ("left", "top", "right", "bottom")
                ):
                    geometry = inspect_reference(preview)["image"]["geometry_hints"]
                    actual_frame = geometry.get("plot_frame", {})
                    margin_errors = {
                        key: round(abs(float(actual_frame.get(key, 0)) - float(expected_frame[key])), 3)
                        for key in ("left", "top", "right", "bottom")
                    }
                    sides_match = all(
                        geometry.get("frame_sides", {}).get(key) == bool(value)
                        for key, value in expected_sides.items()
                    ) if expected_sides else True
                    checks.append(
                        {
                            "name": "preview_frame_geometry",
                            "passed": max(margin_errors.values(), default=0) <= 4.0 and sides_match,
                            "details": {
                                "expected": {key: expected_frame[key] for key in ("left", "top", "right", "bottom")},
                                "actual": {key: actual_frame.get(key) for key in ("left", "top", "right", "bottom")},
                                "margin_errors": margin_errors,
                                "expected_sides": expected_sides,
                                "actual_sides": geometry.get("frame_sides", {}),
                            },
                        }
                    )
            except (ImportError, OSError, TypeError, ValueError) as exc:
                checks.append({"name": "preview_aspect_ratio", "passed": False, "details": str(exc)})

    if not path.is_file():
        checks.append({"name": "origin_open", "passed": False, "details": "Project file is missing."})
    else:
        try:
            op = open_origin_project(str(path), show=False)
            pages = getattr(op, "pages", None)
            graph_pages = list(pages("g")) if callable(pages) else []
            graph_count = len(graph_pages) if callable(pages) else None
            checks.append(
                {
                    "name": "origin_open",
                    "passed": True,
                    "details": {"graph_count": graph_count},
                }
            )
            if graph_pages:
                graph = graph_pages[0]
                layer = graph[0] if hasattr(graph, "__getitem__") else None
                expected_font = style.get("tick_label_font_pt", style.get("base_font_pt"))
                if layer is not None and expected_font is not None:
                    actual_fonts = []
                    for axis_name in ("x", "y"):
                        try:
                            actual_fonts.append(float(layer.get_float(f"{axis_name}.label.pt")))
                        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                            pass
                    checks.append(
                        {
                            "name": "origin_tick_label_font",
                            "passed": len(actual_fonts) == 2 and all(abs(font - float(expected_font)) <= 0.25 for font in actual_fonts),
                            "details": {"expected_pt": expected_font, "actual_pt": actual_fonts},
                        }
                    )
                expected_minor = {
                    "x": ((plot_spec.get("axes", {}) or {}).get("x", {}) or {}).get("minor_tick_count"),
                    "y": ((plot_spec.get("axes", {}) or {}).get("y", {}) or {}).get("minor_tick_count"),
                }
                if layer is not None and any(value is not None for value in expected_minor.values()):
                    actual_minor: dict[str, float | None] = {}
                    for axis_name in ("x", "y"):
                        try:
                            actual_minor[axis_name] = float(layer.get_float(f"{axis_name}.minorTicks"))
                        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                            actual_minor[axis_name] = None
                    passed_minor = all(
                        expected_minor[name] is None
                        or actual_minor.get(name) is not None
                        and abs(float(actual_minor[name]) - float(expected_minor[name])) <= 0.25
                        for name in ("x", "y")
                    )
                    checks.append(
                        {
                            "name": "origin_minor_tick_count",
                            "passed": passed_minor,
                            "details": {"expected": expected_minor, "actual": actual_minor},
                        }
                    )
                expected_width_mm = style.get("page_width_mm")
                expected_height_mm = style.get("page_height_mm")
                if expected_width_mm and expected_height_mm:
                    try:
                        resx = float(graph.get_float("resx"))
                        resy = float(graph.get_float("resy"))
                        actual_width_mm = float(graph.get_float("width")) / resx * 25.4
                        actual_height_mm = float(graph.get_float("height")) / resy * 25.4
                        checks.append(
                            {
                                "name": "origin_page_size",
                                "passed": abs(actual_width_mm - float(expected_width_mm)) / float(expected_width_mm) <= 0.02
                                and abs(actual_height_mm - float(expected_height_mm)) / float(expected_height_mm) <= 0.02,
                                "details": {
                                    "expected_mm": {"width": expected_width_mm, "height": expected_height_mm},
                                    "actual_mm": {"width": round(actual_width_mm, 4), "height": round(actual_height_mm, 4)},
                                    "unit": graph.get_float("unit"),
                                },
                            }
                        )
                    except (AttributeError, TypeError, ValueError, ZeroDivisionError, RuntimeError, OSError) as exc:
                        checks.append({"name": "origin_page_size", "passed": False, "details": str(exc)})
                expected_zoom = style.get("open_zoom_percent")
                if layer is not None and expected_zoom is not None:
                    try:
                        actual_zoom = float(graph.get_float("zoom"))
                        checks.append(
                            {
                                "name": "origin_open_zoom",
                                "passed": abs(actual_zoom - float(expected_zoom)) <= 1.0,
                                "details": {"expected_percent": expected_zoom, "actual_percent": actual_zoom},
                            }
                        )
                    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
                        checks.append({"name": "origin_open_zoom", "passed": False, "details": str(exc)})
            exit_origin = getattr(op, "exit", None)
            if callable(exit_origin):
                exit_origin()
        except OriginUnavailableError as exc:
            checks.append({"name": "origin_open", "passed": False, "details": str(exc), "skipped": True})
        except OriginBridgeError as exc:
            checks.append({"name": "origin_open", "passed": False, "details": str(exc)})

    passed = all(check["passed"] for check in checks) and not any(
        check.get("skipped") for check in checks
    )
    report = {
        "verification_version": "1.0",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "project": str(path),
        "graph_family": plot_spec.get("graph_family"),
        "checks": checks,
    }
    if output_dir:
        write_json(Path(output_dir) / "verification_report.json", report)
    return json_safe(report)

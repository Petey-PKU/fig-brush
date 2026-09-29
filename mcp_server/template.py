"""Screenshot-only template preparation. No private dataset is accepted here."""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import re
from typing import Any

import numpy as np
from PIL import Image

from .curve_fitting import fit_marker_curve
from .paths import InputValidationError, resolve_input, sha256_file, write_json


PROVENANCE = "Visual placeholder reconstructed from the reference image; not original research data."
# Pie families are kept explicit so a reader can distinguish a flat 2-D
# composition chart from a perspective/3-D rendering.  They still share the
# same editable categorical X + numeric Y data contract.
KINDS = {
    "line", "scatter", "line_symbol", "column", "pie", "doughnut",
    "pie3d", "doughnut3d", "heatmap",
}

# A screenshot does not contain the paper's private measurements.  By default
# we therefore optimize for a fast, readable visual placeholder: preserve the
# number and rough position of visible observations, but do not spend time
# carrying many insignificant decimal places through Origin.  Callers that
# need the historical, full-precision behaviour can set
# ``placeholder_policy.mode`` to ``exact`` in the TemplateSpec.
_DEFAULT_PLACEHOLDER_POLICY = {
    "mode": "approximate_visual",
    "numeric_significant_digits": 3,
    "fit_dense_points": 120,
    "preserve_axis_bounds": True,
    "preserve_marker_count": True,
}
_PLACEHOLDER_POLICY_KEYS = set(_DEFAULT_PLACEHOLDER_POLICY)
_PLACEHOLDER_MODES = {"approximate_visual", "exact"}


def _normalise_placeholder_policy(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a validated placeholder policy without mutating ``spec``.

    The policy is deliberately part of the public TemplateSpec.  This makes
    the speed/fidelity trade-off visible in ``data_manifest.json`` and keeps an
    exact/pixel-oriented caller backwards compatible.
    """
    raw = spec.get("placeholder_policy")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise InputValidationError("placeholder_policy must be an object.")
    unknown = set(raw) - _PLACEHOLDER_POLICY_KEYS
    if unknown:
        raise InputValidationError(f"placeholder_policy has unsupported fields: {sorted(unknown)}")
    policy = dict(_DEFAULT_PLACEHOLDER_POLICY)
    policy.update(raw)
    mode = str(policy.get("mode", "")).strip().lower().replace("-", "_")
    # A few natural spellings are accepted so model-authored specs remain
    # easy to write while manifests use one stable value.
    if mode in {"approximate", "visual", "visual_placeholder", "approximate_visual_placeholder"}:
        mode = "approximate_visual"
    elif mode in {"full_precision", "pixel", "pixel_fidelity", "exact_values"}:
        mode = "exact"
    if mode not in _PLACEHOLDER_MODES:
        raise InputValidationError(
            "placeholder_policy.mode must be 'approximate_visual' or 'exact'."
        )
    policy["mode"] = mode
    digits = policy.get("numeric_significant_digits")
    if isinstance(digits, bool) or not isinstance(digits, int) or not 1 <= digits <= 12:
        raise InputValidationError("placeholder_policy.numeric_significant_digits must be an integer from 1 to 12.")
    dense_points = policy.get("fit_dense_points")
    if isinstance(dense_points, bool) or not isinstance(dense_points, int) or dense_points < 20:
        raise InputValidationError("placeholder_policy.fit_dense_points must be an integer >= 20.")
    for key in ("preserve_axis_bounds", "preserve_marker_count"):
        if not isinstance(policy.get(key), bool):
            raise InputValidationError(f"placeholder_policy.{key} must be boolean.")
    return policy


def _round_significant(value: float, digits: int) -> float:
    """Round one finite number to significant digits, preserving zero."""
    value = float(value)
    if value == 0.0 or not math.isfinite(value):
        return value
    exponent = math.floor(math.log10(abs(value)))
    decimals = int(digits - 1 - exponent)
    rounded = round(value, decimals)
    # Avoid serialising a negative zero, which is confusing in a replacement
    # worksheet and has no visual meaning.
    return 0.0 if rounded == 0 else float(rounded)


def _round_numeric_data(spec: dict[str, Any], policy: dict[str, Any]) -> None:
    """Apply approximate placeholder precision to data arrays in-place.

    Axis limits are intentionally excluded.  They are visual geometry and
    must remain exactly as read from the reference.  Categorical labels and
    colour integers are also left untouched.  The operation never drops a
    row, so marker count remains a stable replacement contract.
    """
    if policy["mode"] == "exact":
        return
    digits = int(policy["numeric_significant_digits"])
    numeric_fields = {"x", "y", "y_error", "x_error", "lower", "upper"}
    for panel in spec.get("panels", []):
        matrix = panel.get("matrix")
        if isinstance(matrix, dict) and isinstance(matrix.get("values"), list):
            matrix["values"] = [
                [_round_significant(float(value), digits) for value in row]
                for row in matrix["values"]
            ]
        for series in panel.get("series", []):
            for block_name in ("data", "marker_data", "line_data"):
                block = series.get(block_name)
                if not isinstance(block, dict):
                    continue
                # Marker placeholders are intentionally compact in fast mode,
                # but dense fitted curves and confidence-band boundaries are
                # visual geometry.  Keeping a few extra digits prevents the
                # Origin line/fill from becoming visibly stair-stepped.
                block_digits = max(digits, 6) if block_name == "line_data" else digits
                for field in numeric_fields:
                    values = block.get(field)
                    if isinstance(values, list):
                        # Pie/doughnut X values are category labels (for
                        # example ``["B cells", "T cells"]``), not numeric
                        # coordinates.  Preserve those strings while still
                        # compacting numeric X/Y/error arrays for Cartesian
                        # series.
                        if any(isinstance(value, str) for value in values):
                            continue
                        block[field] = [_round_significant(float(value), block_digits) for value in values]


def _wide_columns_for_series(series: dict[str, Any]) -> dict[str, str]:
    """Stable, human-readable headers for a panel-wide Origin worksheet."""
    prefix = str(series["id"])
    source = dict(series.get("data", {}) or {})
    source.update(series.get("marker_data", {}) or {})
    columns = {"x": f"{prefix}_X", "y": f"{prefix}_Y"}
    for key, suffix in (("y_error", "YErr"), ("x_error", "XErr"), ("color_rgb", "ColorRGB")):
        if key in source:
            columns[key] = f"{prefix}_{suffix}"
    if series.get("line_data"):
        columns["fit_x"] = f"{prefix}_FitX"
        columns["fit_y"] = f"{prefix}_FitY"
        if "lower" in series["line_data"]:
            columns["fit_lower"] = f"{prefix}_FitLower"
        if "upper" in series["line_data"]:
            columns["fit_upper"] = f"{prefix}_FitUpper"
    return columns


def _validate_series_data(data: Any, sid: str, categorical_x: bool = False) -> tuple[list[Any], list[float]]:
    if not isinstance(data, dict):
        raise InputValidationError(f"{sid}.data must be an object.")
    if categorical_x:
        x_raw = data.get("x")
        if not isinstance(x_raw, list) or not x_raw:
            raise InputValidationError(f"{sid}.x must be a nonempty category list for pie data.")
        if all(isinstance(v, str) and v.strip() for v in x_raw):
            x = [str(v) for v in x_raw]
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in x_raw):
            x = [float(v) for v in x_raw]
        else:
            raise InputValidationError(f"{sid}.x must contain either strings or finite numbers for pie data.")
    else:
        x = _numbers(data.get("x"), sid + ".x")
    y = _numbers(data.get("y"), sid + ".y")
    if len(x) != len(y):
        raise InputValidationError(f"{sid}: X and Y lengths must agree.")
    return x, y


def pixel_to_value(pixel: float, start: float, end: float, axis: dict) -> float:
    """Calibrate in the displayed coordinate system (including reversed/log axes)."""
    if start == end:
        raise InputValidationError("Axis calibration needs two distinct pixel coordinates.")
    t = (pixel - start) / (end - start)
    lo, hi = float(axis["min"]), float(axis["max"])
    if axis.get("scale", "linear") == "log10":
        if min(lo, hi) <= 0:
            raise InputValidationError("Logarithmic limits must be positive.")
        return float(10 ** (math.log10(lo) + t * math.log10(hi / lo)))
    return lo + t * (hi - lo)


def value_to_pixel(value: float, start: float, end: float, axis: dict) -> float:
    lo, hi = float(axis["min"]), float(axis["max"])
    if axis.get("scale", "linear") == "log10":
        t = math.log10(value / lo) / math.log10(hi / lo)
    else:
        t = (value - lo) / (hi - lo)
    return start + t * (end - start)


def _numbers(values: Any, field: str) -> list[float]:
    if not isinstance(values, list) or not values:
        raise InputValidationError(f"{field} must be a nonempty numeric list.")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
        raise InputValidationError(f"{field} must contain finite numbers only.")
    return [float(v) for v in values]


_FIT_REQUEST_KEYS = {"model", "points", "options", "x_range", "x_domain", "dense_points", "source_label", "confidence_level"}
_FIT_OPTION_KEYS = {"x_range", "x_domain", "dense_points", "source_label", "confidence_level"}


def _validate_fit_request(request: Any, sid: str) -> None:
    """Validate the opt-in marker-to-fit contract without running scipy."""
    if not isinstance(request, dict):
        raise InputValidationError(f"{sid}.fit_request must be an object.")
    unknown = set(request) - _FIT_REQUEST_KEYS
    if unknown:
        raise InputValidationError(f"{sid}.fit_request has unsupported fields: {sorted(unknown)}")
    if not isinstance(request.get("model"), str) or not request["model"].strip():
        raise InputValidationError(f"{sid}.fit_request.model must be a nonempty string.")
    points = request.get("points", "marker_data")
    if points not in {"marker_data", "data"}:
        raise InputValidationError(f"{sid}.fit_request.points must be 'marker_data' or 'data'.")
    options = request.get("options", {})
    if not isinstance(options, dict):
        raise InputValidationError(f"{sid}.fit_request.options must be an object.")
    unknown_options = set(options) - _FIT_OPTION_KEYS
    if unknown_options:
        raise InputValidationError(f"{sid}.fit_request.options has unsupported fields: {sorted(unknown_options)}")
    merged = dict(options)
    for key in ("x_range", "x_domain", "dense_points", "source_label"):
        if key in request:
            merged[key] = request[key]
    if "x_range" in merged and "x_domain" in merged:
        raise InputValidationError(f"{sid}.fit_request should specify only one of x_range or x_domain.")
    range_value = merged.get("x_range", merged.get("x_domain"))
    if range_value is not None:
        if not isinstance(range_value, list) or len(range_value) != 2:
            raise InputValidationError(f"{sid}.fit_request x_range must be [min, max].")
        try:
            values = [float(value) for value in range_value]
        except (TypeError, ValueError):
            raise InputValidationError(f"{sid}.fit_request x_range must contain finite numbers.")
        if any(not math.isfinite(value) for value in values) or values[1] <= values[0]:
            raise InputValidationError(
                f"{sid}.fit_request x_range must be finite and increasing; "
                "positivity is checked by the selected fit model."
            )
    if "dense_points" in merged:
        points_value = merged["dense_points"]
        if isinstance(points_value, bool) or not isinstance(points_value, int) or points_value < 20:
            raise InputValidationError(f"{sid}.fit_request dense_points must be an integer >= 20.")
    if "source_label" in merged and not isinstance(merged["source_label"], str):
        raise InputValidationError(f"{sid}.fit_request source_label must be a string.")
    if "confidence_level" in merged:
        level = merged["confidence_level"]
        if isinstance(level, bool) or not isinstance(level, (float, int)) or not 0.5 < float(level) < 1.0:
            raise InputValidationError(f"{sid}.fit_request confidence_level must be between 0.5 and 1.0.")


def _fit_request_options(request: dict[str, Any]) -> dict[str, Any]:
    options = dict(request.get("options", {}))
    for key in ("x_range", "x_domain", "dense_points", "source_label", "confidence_level"):
        if key in request:
            options[key] = request[key]
    # x_range is the public, image-oriented spelling; curve_fitting receives
    # the neutral x_domain argument.
    if "x_range" in options:
        options["x_domain"] = options.pop("x_range")
    return options


def _apply_requested_fits(spec: dict[str, Any]) -> None:
    """Derive explicit marker fits in-place; never infer fit intent implicitly."""
    policy = _normalise_placeholder_policy(spec)
    default_dense_points = 400 if policy["mode"] == "exact" else int(policy["fit_dense_points"])
    for panel in spec.get("panels", []):
        for series in panel.get("series", []):
            request = series.get("fit_request")
            if request is None:
                continue
            sid = str(series.get("id", "Series"))
            source_key = request.get("points", "marker_data")
            source = series.get(source_key)
            if source is None:
                raise InputValidationError(
                    f"{sid}.fit_request.points={source_key!r} requires that field on the series."
                )
            x, y = _validate_series_data(source, sid + "." + source_key)
            options = _fit_request_options(request)
            x_domain = options.pop("x_domain", None)
            dense_points = options.pop("dense_points", default_dense_points)
            source_label = options.pop("source_label", f"{sid} marker observations")
            confidence_level = options.pop("confidence_level", 0.95)
            if options:
                # This is defensive: _validate_fit_request catches it before
                # this function runs, and keeps future edits from being silent.
                raise InputValidationError(f"{sid}.fit_request has unsupported options: {sorted(options)}")
            try:
                fit = fit_marker_curve(
                    x, y, model=str(request["model"]),
                    x_domain=tuple(x_domain) if x_domain is not None else None,
                    dense_points=int(dense_points), source_label=source_label,
                    confidence_level=float(confidence_level),
                )
            except (TypeError, ValueError) as exc:
                raise InputValidationError(f"{sid}.fit_request could not be applied: {exc}") from exc
            series["line_data"] = fit["line_data"]
            series["fit_metadata"] = fit["fit_metadata"]
            # Preserve a normalized, audit-friendly request beside the derived
            # columns so a replacement workflow can reproduce the same fit.
            normalized = {"model": str(request["model"]), "points": source_key}
            if x_domain is not None:
                normalized["x_range"] = [float(x_domain[0]), float(x_domain[1])]
            if "dense_points" in request or "dense_points" in request.get("options", {}) or dense_points != 400:
                normalized["dense_points"] = int(dense_points)
            if source_label != f"{sid} marker observations":
                normalized["source_label"] = source_label
            if "confidence_level" in request or "confidence_level" in request.get("options", {}) or float(confidence_level) != 0.95:
                normalized["confidence_level"] = float(confidence_level)
            series["fit_request"] = normalized


def validate_template(spec: dict) -> None:
    if spec.get("schema_version") != "2.0" or spec.get("mode") != "reference_template":
        raise InputValidationError("Expected schema_version=2.0, mode=reference_template.")
    canvas = spec.get("canvas", {})
    for key in ("width_px", "height_px", "font_reference_px", "font_anchor_pt"):
        if not isinstance(canvas.get(key), (float, int)) or not math.isfinite(canvas[key]) or canvas[key] <= 0:
            raise InputValidationError(f"canvas.{key} must be positive.")
    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels:
        raise InputValidationError("At least one panel is required.")
    _normalise_placeholder_policy(spec)
    ids: set[str] = set()
    for panel in panels:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", panel.get("id", "")) or panel["id"] in ids:
            raise InputValidationError("Panel IDs must be unique Origin-compatible identifiers.")
        ids.add(panel["id"])
        frame = _numbers(panel.get("frame_px"), "frame_px")
        if len(frame) != 4 or not (0 <= frame[0] < frame[2] <= canvas["width_px"] and 0 <= frame[1] < frame[3] <= canvas["height_px"]):
            raise InputValidationError("frame_px must be [left, top, right, bottom] within the canvas.")
        for name in ("x", "y"):
            axis = panel.get("axes", {}).get(name, {})
            limits = _numbers([axis.get("min"), axis.get("max")], f"{name} limits")
            if limits[0] == limits[1] or axis.get("scale", "linear") not in ("linear", "log10"):
                raise InputValidationError("Axis limits must differ and scale must be linear or log10.")
            if axis.get("scale") == "log10" and min(limits) <= 0:
                raise InputValidationError("Logarithmic limits must be positive.")
        if panel.get("graph_family") == "heatmap":
            matrix = panel.get("matrix", {})
            values = matrix.get("values") if isinstance(matrix, dict) else None
            if not isinstance(values, list) or not values or not all(isinstance(row, list) and row for row in values):
                raise InputValidationError("A heatmap requires a nonempty rectangular matrix.")
            width = len(values[0])
            if any(len(row) != width for row in values):
                raise InputValidationError("Heatmap matrix rows must have equal length.")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                   for row in values for value in row):
                raise InputValidationError("Heatmap matrix values must be finite numbers.")
            x_labels = matrix.get("x_labels", [])
            y_labels = matrix.get("y_labels", [])
            if x_labels and (not isinstance(x_labels, list) or len(x_labels) != width):
                raise InputValidationError("Heatmap x_labels must match the matrix width.")
            if y_labels and (not isinstance(y_labels, list) or len(y_labels) != len(values)):
                raise InputValidationError("Heatmap y_labels must match the matrix height.")
        if not panel.get("series") and panel.get("graph_family") != "heatmap":
            raise InputValidationError("A panel must contain native data series.")
        for series in panel.get("series", []):
            sid = series.get("id", "")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", sid) or sid in ids:
                raise InputValidationError("Series IDs must be unique Origin-compatible identifiers.")
            ids.add(sid)
            if series.get("kind") not in KINDS:
                raise InputValidationError(f"Unsupported native series kind: {series.get('kind')}")
            if series.get("kind") == "heatmap":
                continue
            if "fit_request" in series:
                _validate_fit_request(series["fit_request"], sid)
            data = series.get("data", {})
            categorical = series.get("kind") in {"pie", "doughnut", "pie3d", "doughnut3d"}
            x, y = _validate_series_data(data, sid, categorical_x=categorical)
            for data_key in ("line_data", "marker_data"):
                if data_key in series:
                    _validate_series_data(series[data_key], sid + "." + data_key, categorical_x=categorical)
            for axis_name, values in (("x", x), ("y", y)):
                if panel["axes"][axis_name].get("scale") == "log10" and min(values) <= 0:
                    raise InputValidationError(f"{sid}: log-axis data must be positive.")
            for data_key in ("line_data", "marker_data"):
                if data_key in series:
                    sx, sy = _validate_series_data(
                        series[data_key], sid + "." + data_key, categorical_x=categorical
                    )
                    for axis_name, values in (("x", sx), ("y", sy)):
                        if panel["axes"][axis_name].get("scale") == "log10" and min(values) <= 0:
                            raise InputValidationError(f"{sid}.{data_key}: log-axis data must be positive.")
                    if data_key == "line_data":
                        line_block = series[data_key]
                        has_lower = "lower" in line_block
                        has_upper = "upper" in line_block
                        if has_lower != has_upper:
                            raise InputValidationError(f"{sid}.line_data confidence band requires both lower and upper.")
                        if has_lower:
                            lower = _numbers(line_block["lower"], sid + ".line_data.lower")
                            upper = _numbers(line_block["upper"], sid + ".line_data.upper")
                            if len(lower) != len(sx) or len(upper) != len(sx):
                                raise InputValidationError(f"{sid}.line_data confidence band arrays must match X/Y length.")
                            if any(lo > hi for lo, hi in zip(lower, upper)):
                                raise InputValidationError(f"{sid}.line_data confidence band lower values must not exceed upper values.")
            for error in ("y_error", "x_error"):
                if error in data:
                    errors = _numbers(data[error], sid + "." + error)
                    if len(errors) != len(x) or min(errors) < 0:
                        raise InputValidationError(f"{sid}: error magnitudes must be nonnegative and match X/Y length.")


def prepare_template(image_path: str, template_spec: dict, output_dir: str) -> dict:
    """Resolve an agent's visual reading into transparent, replaceable placeholder data."""
    reference = resolve_input(image_path, {".png", ".jpg", ".jpeg"})
    spec = deepcopy(template_spec)
    validate_template(spec)
    policy = _normalise_placeholder_policy(spec)
    spec["placeholder_policy"] = policy
    _round_numeric_data(spec, policy)
    _apply_requested_fits(spec)
    # Fit output is generated after marker rounding.  Apply the same compact
    # serialization to the derived trace so the worksheet remains light and
    # fast to write while retaining its full row count.
    _round_numeric_data(spec, policy)
    # Validate derived line_data and its axis compatibility after fitting.
    validate_template(spec)
    with Image.open(reference) as im:
        actual = list(im.size)
    if actual != [spec["canvas"]["width_px"], spec["canvas"]["height_px"]]:
        raise InputValidationError("Canvas dimensions must match the inspected reference image.")
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    spec["reference"] = {"path": str(reference), "sha256": sha256_file(reference)}
    spec["data_policy"] = {
        "source": "reference_image_only", "private_data_requested": False,
        "provenance": PROVENANCE, "original_data_recovered": False,
        "placeholder_mode": policy["mode"],
        "numeric_significant_digits": policy["numeric_significant_digits"],
        "fit_dense_points_default": policy["fit_dense_points"],
        "preserves_axis_bounds": policy["preserve_axis_bounds"],
        "preserves_marker_count": policy["preserve_marker_count"],
        "speed_intent": "Visual style is the priority; placeholder values are intentionally approximate."
        if policy["mode"] == "approximate_visual" else
        "Exact numeric placeholders requested by the caller; values still are not original research data.",
    }
    # All XY replacement worksheets for one reference image share this book.
    # Keeping the name in the spec makes the user-facing replacement map and
    # the Origin builder agree even when a caller supplies a custom label.
    spec.setdefault("data_book_name", "Reference Data")
    factor = spec["canvas"]["font_anchor_pt"] / spec["canvas"]["font_reference_px"]
    spec["layout_resolution"] = {
        "points_per_reference_pixel": factor,
        "width_mm": spec["canvas"]["width_px"] * factor * 25.4 / 72,
        "height_mm": spec["canvas"]["height_px"] * factor * 25.4 / 72,
        "physical_size_is_inferred": True,
        "formula": "point_scale = font_anchor_pt / reference_font_em_px; page_mm = reference_px * point_scale * 25.4 / 72",
    }
    mapping = []
    for panel in spec["panels"]:
        if panel.get("graph_family") == "heatmap":
            matrix = panel.get("matrix", {})
            mapping.append({
                "panel": panel["id"], "series_id": panel["id"] + "Matrix",
                "visible_name": matrix.get("name", "Heatmap matrix"),
                "role": "editable heatmap matrix", "color": matrix.get("colormap", "Thermometer.pal"),
                "worksheet": panel["id"] + " Matrix", "columns": {"Z": "matrix values"},
                "rows": len(matrix.get("values", [])), "columns_count": len(matrix.get("values", [[]])[0]) if matrix.get("values") else 0,
                # Matrix worksheets use Origin's native matrix layer, but they
                # still belong to the same replacement workbook as XY data.
                # A suffix here made the manifest imply a second book even
                # when the builder could keep all sheets together.
                "book": spec["data_book_name"],
                "provenance": PROVENANCE,
            })
        panel_series = panel.get("series", [])
        # Put every multi-series panel, and every marker-plus-fit panel, on a
        # single worksheet with repeated X/Y pairs.  This leaves the user a
        # compact, readable replacement surface while keeping fitted traces
        # visibly separate from the marker observations.
        panel_wide = bool(panel_series) and (
            len(panel_series) > 1
            or any(series.get("line_data") or series.get("marker_data") for series in panel_series)
        )
        if panel_wide:
            panel["data_layout"] = "panel_wide"
            panel.setdefault("data_worksheet", f"{panel['id']}_Data")
            # Reuse a single X column when every series has the same
            # observations.  This is common for time-course panels and keeps
            # the researcher's replacement surface to one X plus many Y
            # columns.  Categorical columns retain the same treatment.
            x_sources = [
                (series.get("marker_data") or series.get("data", {})).get("x", [])
                for series in panel_series
            ]
            same_x = bool(x_sources and x_sources[0]) and all(values == x_sources[0] for values in x_sources[1:])
            if any(series.get("kind") == "column" for series in panel_series) or same_x:
                panel["shared_x_header"] = f"{panel['id']}_X"
        for series in panel_series:
            series.setdefault("provenance", PROVENANCE)
            if panel_wide:
                wide = _wide_columns_for_series(series)
                # Merge legacy caller-authored headers while ensuring newly
                # derived FitLower/FitUpper columns are not lost.
                wide.update(series.get("wide_columns", {}) or {})
                series["wide_columns"] = wide
                if panel.get("shared_x_header"):
                    wide["x"] = panel["shared_x_header"]
                series["data_worksheet"] = panel["data_worksheet"]
                series["worksheet"] = panel["data_worksheet"]
                series["marker_worksheet"] = panel["data_worksheet"]
                if "line_data" in series:
                    series["line_worksheet"] = panel["data_worksheet"]
                columns = {role: wide[key] for role, key in (
                    ("X", "x"), ("Y", "y"), ("YErr", "y_error"), ("XErr", "x_error"),
                    ("ColorRGB", "color_rgb"), ("FitX", "fit_x"), ("FitY", "fit_y"),
                    ("FitLower", "fit_lower"), ("FitUpper", "fit_upper"),
                ) if key in wide}
                marker_source = series.get("marker_data") or series.get("data", {})
                item = {"panel": panel["id"], "series_id": series["id"], "visible_name": series.get("name", series["id"]),
                        "role": series.get("role", series["kind"]), "color": series.get("style", {}).get("color", "#000000"),
                        "color_list": series.get("style", {}).get("colors", []),
                        "style": deepcopy(series.get("style", {})),
                        "worksheet": panel["data_worksheet"], "data_layout": "panel_wide", "columns": columns,
                        "rows": len(marker_source.get("x", [])), "book": spec["data_book_name"],
                        "provenance": series["provenance"]}
                if series.get("fit_request") is not None:
                    item["fit_request"] = deepcopy(series["fit_request"])
                if series.get("fit_metadata") is not None:
                    item["fit_metadata"] = deepcopy(series["fit_metadata"])
                if "line_data" in series:
                    item["line_rows"] = len(series["line_data"]["x"])
                    item["line_worksheet"] = panel["data_worksheet"]
                    if "lower" in series["line_data"]:
                        item["confidence_band"] = deepcopy(
                            (series.get("fit_metadata", {}) or {}).get(
                                "confidence_band", {"available": True, "kind": "confidence"}
                            )
                        )
                if "marker_data" in series:
                    item["marker_rows"] = len(series["marker_data"]["x"])
                    item["marker_worksheet"] = panel["data_worksheet"]
                mapping.append(item)
            else:
                columns = ["x", "y"] + [key for key in ("y_error", "x_error", "color_rgb") if key in series["data"]]
                if "line_data" in series:
                    series["line_worksheet"] = series.get("line_worksheet", series["id"] + "_line")
                if "marker_data" in series:
                    series["marker_worksheet"] = series.get("marker_worksheet", series["id"] + "_markers")
                # The plotted replacement sheet is the marker worksheet when a
                # reference contains sparse observations plus a dense line;
                # otherwise the series id is the worksheet name.
                series["worksheet"] = series.get("marker_worksheet", series["id"])
                mapping.append({"panel": panel["id"], "series_id": series["id"], "visible_name": series.get("name", series["id"]),
                                "role": series.get("role", series["kind"]), "color": series.get("style", {}).get("color", "#000000"),
                                "color_list": series.get("style", {}).get("colors", []),
                                "style": deepcopy(series.get("style", {})),
                                "worksheet": series["worksheet"], "columns": {chr(65+i): key for i, key in enumerate(columns)},
                                "rows": len(series["data"]["x"]), "book": spec["data_book_name"],
                                "provenance": series["provenance"],
                                **({"derived_columns": {"FitX": "A", "FitY": "B", **({"FitLower": "C"} if "lower" in series.get("line_data", {}) else {}), **({"FitUpper": "D" if "lower" in series.get("line_data", {}) else "C"} if "upper" in series.get("line_data", {}) else {})}} if "line_data" in series else {}),
                                **({"fit_request": deepcopy(series["fit_request"])} if series.get("fit_request") is not None else {}),
                                **({"fit_metadata": deepcopy(series["fit_metadata"])} if series.get("fit_metadata") is not None else {})})
                if "line_data" in series:
                    mapping[-1]["line_worksheet"] = series["line_worksheet"]
                    mapping[-1]["line_rows"] = len(series["line_data"]["x"])
                    if "lower" in series["line_data"]:
                        mapping[-1]["confidence_band"] = deepcopy(
                            (series.get("fit_metadata", {}) or {}).get(
                                "confidence_band", {"available": True, "kind": "confidence"}
                            )
                        )
                if "marker_data" in series:
                    mapping[-1]["marker_worksheet"] = series["marker_worksheet"]
                    mapping[-1]["marker_rows"] = len(series["marker_data"]["x"])
    interpretation = deepcopy(spec.get("interpretation", {}))
    context = deepcopy(spec.get("scientific_context", {}))
    if not context and isinstance(interpretation, dict):
        context = deepcopy(interpretation.get("scientific_context", {}))
    manifest = {"schema_version": "2.0", "data_policy": spec["data_policy"],
                "placeholder_policy": deepcopy(spec["placeholder_policy"]), "data_book": spec["data_book_name"],
                "scientific_context": context, "interpretation": interpretation,
                "layout_resolution": deepcopy(spec.get("layout_resolution", {})), "series": mapping,
                "replacement": "Paste your locally processed values into the matching columns in the same Reference Data book. Multi-series panels use one worksheet with parallel X/Y columns; FitX/FitY and FitLower/FitUpper are candidate derived traces to regenerate after replacement. Keep X/Y/error roles; clear obsolete rows if the replacement is shorter. Axis limits are fixed to the reference until you rescale them.",
                "annotations": "Reference statistics and fitted curves are visual placeholders. Replace these using your own results; the plugin does not infer their scientific meaning."}
    write_json(output / "template_spec.json", spec)
    write_json(output / "data_manifest.json", manifest)
    (output / "替换数据说明.md").write_text(_replacement_guide(manifest), encoding="utf-8")
    return {"status": "prepared", "spec": spec, "manifest": manifest,
            "template_spec": str(output / "template_spec.json"), "data_manifest": str(output / "data_manifest.json")}


def _replacement_guide(manifest: dict) -> str:
    books = {str(item.get("book", manifest.get("data_book", "Reference Data"))) for item in manifest.get("series", [])}
    if len(books) > 1:
        location = "、".join(sorted(books))
        opening = f"本图包含多个 Origin 页面类型，请分别打开 `{location}`；按下表找到对应工作表，将自己处理的 X、Y、误差或矩阵列粘贴进去。"
    else:
        opening = f"在 Origin 的 `{manifest.get('data_book', 'Reference Data')}` book 中找到下表对应工作表，将自己处理的 X、Y、误差列粘贴进去。"
    policy = manifest.get("placeholder_policy", {})
    mode = policy.get("mode", "approximate_visual")
    if mode == "approximate_visual":
        policy_note = (f"当前采用快速视觉占位策略：数值最多保留 {policy.get('numeric_significant_digits', 3)} 位有效数字，"
                       f"拟合轨迹默认使用 {policy.get('fit_dense_points', 120)} 个点；坐标范围和可见 marker 数量保持不变。")
    else:
        policy_note = "当前采用 exact 占位策略，保留调用方提供的数值精度；这些数值仍不是原始实验数据。"
    lines = ["# Origin 风格模板：替换数据", "", "只需截图即可创建本模板。所有数值均为用于复现外观的示例，不是原始实验数据。", policy_note, "",
             opening + "同一 panel 的多组 X/Y 已并列放在同一页，环形图还可替换 ColorRGB 列中的 Origin RGB 整数。行数减少时清空末尾旧值。曲线直接关联工作表，无需重新设定样式。FitLower/FitUpper 是拟合均值的候选置信带上下界，替换数据后应按自己的模型和统计方法重新计算。", "",
             "| 图中对象 | 颜色 | Book | 工作表 | 列对应 | 点数 |", "|---|---|---|---|---|---|"]
    for item in manifest["series"]:
        name = item["visible_name"].replace("|", "\\|")
        lines.append(f"| {name} ({item['role']}) | {item['color']} | {item.get('book', manifest.get('data_book', 'Reference Data'))} | {item['worksheet']} | " + ", ".join(f"{c}: {v}" for c,v in item["columns"].items()) + f" | {item['rows']} |")
    lines += ["", "坐标范围保持参考图设置，数据超出范围时请手动重设范围。FitX/FitY（若本图定义了拟合或显示轨迹）来自占位点；FitLower/FitUpper（若存在）是用于视觉复现的候选置信带，并非论文原始统计结果；替换自己的 X/Y 后请按实际模型重新拟合或覆盖派生列。",
              "", "误差棒只复制可见长度，不能据此认定为 SD、SEM 或 CI。图中的 P 值、显著性、IC50 等属于参考文字，请按自己的统计结果修改。私人数据由你本地处理和保管。", ""]
    return "\n".join(lines)


def compare_reference(reference: str, preview: str, output_dir: str) -> dict:
    """Report foreground-aware image distances; white margins cannot dominate the score."""
    from scipy.ndimage import distance_transform_edt
    with Image.open(reference) as im:
        a = np.asarray(im.convert("RGB"), dtype=float)
    with Image.open(preview) as im:
        original_size = im.size
        b = np.asarray(im.convert("RGB").resize((a.shape[1], a.shape[0]), Image.Resampling.LANCZOS), dtype=float)
    fg_a, fg_b = np.min(a, axis=2) < 230, np.min(b, axis=2) < 230
    union = fg_a | fg_b
    da, db = distance_transform_edt(~fg_a), distance_transform_edt(~fg_b)
    distances = np.concatenate([db[fg_a], da[fg_b]])
    result = {"reference_size": [a.shape[1], a.shape[0]], "preview_size": list(original_size),
              "foreground_mean_rgb_error": float(np.abs(a-b)[union].mean()/255) if union.any() else 0,
              "foreground_distance_mean_px": float(distances.mean()) if distances.size else 0,
              "foreground_distance_p95_px": float(np.percentile(distances, 95)) if distances.size else 0,
              "pixels_within_2px_fraction": float((distances <= 2).mean()) if distances.size else 1,
              "pixel_identical": bool(np.array_equal(a,b)),
              "interpretation": "Diagnostic image distances, not proof of matching semantics, font identity, editable structure, or original data."}
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.uint8(a*.5+b*.5)).save(output / "comparison_overlay.png")
    Image.fromarray(np.uint8(np.clip(np.abs(a-b)*2,0,255))).save(output / "comparison_difference.png")
    write_json(output / "visual_comparison.json", result)
    return result


def verify_template(output_dir: str) -> dict:
    """Verify template artifacts and native Origin accessibility without inventing fidelity."""
    from origin_bridge.connection import OriginBridgeError, OriginUnavailableError, open_origin_project
    output = Path(output_dir).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    spec_path, manifest_path, project_path = output / "template_spec.json", output / "data_manifest.json", output / "result.opju"
    for name, path in (("template_spec", spec_path), ("data_manifest", manifest_path), ("origin_project", project_path)):
        checks.append({"name": name + "_exists", "passed": path.is_file(), "path": str(path)})
    previews = [output / "preview.png", output / "preview.svg"]
    checks.append({"name": "preview_exists", "passed": any(p.is_file() for p in previews), "paths": [str(p) for p in previews]})
    if spec_path.is_file() and manifest_path.is_file():
        try:
            spec = __import__("json").loads(spec_path.read_text(encoding="utf-8"))
            manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
            validate_template(spec)
            checks.append({"name": "template_spec_valid", "passed": True})
            checks.append({"name": "placeholder_policy", "passed": manifest.get("data_policy", {}).get("original_data_recovered") is False,
                           "details": manifest.get("data_policy")})
            expected_mapping = sum(len(p.get("series", [])) + (1 if p.get("graph_family") == "heatmap" else 0)
                                   for p in spec.get("panels", []))
            checks.append({"name": "series_mapping_complete", "passed": len(manifest.get("series", [])) == expected_mapping})
        except Exception as exc:
            checks.append({"name": "template_spec_valid", "passed": False, "details": str(exc)})
    if project_path.is_file():
        try:
            op = open_origin_project(str(project_path), show=False)
            pages = list(op.graph_list("p")) if callable(getattr(op, "graph_list", None)) else []
            checks.append({"name": "origin_opju_opens", "passed": bool(pages), "graph_pages": len(pages)})
            close = getattr(op, "exit", None)
            if callable(close):
                close()
        except (OriginUnavailableError, OriginBridgeError) as exc:
            checks.append({"name": "origin_opju_opens", "passed": False, "details": str(exc), "skipped": True})
    passed = all(check.get("passed", False) for check in checks)
    limitations = ["Placeholder values are not original research data.", "Artifact checks do not prove perfect visual or semantic identity."]
    if spec_path.is_file():
        try:
            families = {p.get("graph_family") for p in __import__("json").loads(spec_path.read_text(encoding="utf-8")).get("panels", [])}
            if families & {"pie", "doughnut", "pie3d", "doughnut3d", "heatmap"}:
                limitations.append("This bridge smoke test keeps ring/heatmap values editable as native replacement series; exact specialized Origin geometry may require a local Origin template or a follow-up renderer.")
        except Exception:
            pass
    report = {"verification_version": "2.0", "status": "passed" if passed else "failed", "passed": passed,
              "mode": "reference_template", "output_dir": str(output), "checks": checks, "limitations": limitations}
    write_json(output / "verification_report.json", report)
    return report

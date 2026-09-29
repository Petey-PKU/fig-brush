"""Resolve data-linked annotations before handing a PlotSpec to Origin.

Reference images describe a visual relationship (a peak, a short horizontal
marker, and a centered value label), while Origin needs concrete data
coordinates.  This module keeps that relationship semantic until the supplied
data are available, then resolves it against the current axis limits.
"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

import pandas as pd


_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_PEAK_LINE_ROLES = {"peak_marker", "peak_callout", "horizontal_marker"}
_PEAK_LABEL_ROLES = {"peak_value", "peak_label"}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _axis_range(spec: dict[str, Any], frame: pd.DataFrame, axis: str) -> tuple[float, float] | None:
    axis_spec = (spec.get("axes", {}) or {}).get(axis, {}) or {}
    lower = _finite(axis_spec.get("min", axis_spec.get("from")))
    upper = _finite(axis_spec.get("max", axis_spec.get("to")))
    if lower is not None and upper is not None and upper > lower:
        return lower, upper
    mapping = spec.get("data_mapping", {}) or {}
    if axis == "x":
        names = [mapping.get("x")]
    else:
        names = [mapping.get("y")]
        names.extend(mapping.get("numeric_columns", []) or [])
    for name in names:
        if name is None or name not in frame.columns:
            continue
        values = pd.to_numeric(frame[name], errors="coerce").dropna()
        if not values.empty:
            lo, hi = float(values.min()), float(values.max())
            if hi > lo:
                return lo, hi
    return None


def _numeric_value(text: Any) -> float | None:
    if text is None:
        return None
    match = _NUMBER.search(str(text).replace(",", ""))
    return _finite(match.group(0)) if match else None


def _data_peak(spec: dict[str, Any], frame: pd.DataFrame, preferred_x: float | None) -> tuple[float, float] | None:
    mapping = spec.get("data_mapping", {}) or {}
    x_name = mapping.get("x")
    if x_name not in frame.columns:
        return None
    x_values = pd.to_numeric(frame[x_name], errors="coerce")
    y_names = [mapping.get("y")]
    y_names.extend(mapping.get("numeric_columns", []) or [])
    y_names = [name for name in y_names if name in frame.columns]
    if not y_names:
        return None
    candidates: list[tuple[float, float, float]] = []
    for name in y_names:
        y_values = pd.to_numeric(frame[name], errors="coerce")
        valid = x_values.notna() & y_values.notna()
        for x, y in zip(x_values[valid].tolist(), y_values[valid].tolist()):
            candidates.append((float(x), float(y), abs(float(x) - preferred_x) if preferred_x is not None else 0.0))
    if not candidates:
        return None
    if preferred_x is not None:
        # A numeric value label normally identifies a peak by its X coordinate,
        # but the sampled trace may put the tallest point dozens of samples
        # away from the reported centroid. Search a data-relative neighbourhood
        # instead of attaching the callout to one arbitrary raster/sample row.
        distance = min(item[2] for item in candidates)
        x_values = [item[0] for item in candidates]
        x_span = max(x_values) - min(x_values) if x_values else 0.0
        window = max(x_span * 0.003, distance * 3, 1e-9)
        neighbourhood = [item for item in candidates if item[2] <= window]
        return max(neighbourhood, key=lambda item: item[1])[:2]
    return max(candidates, key=lambda item: item[1])[:2]


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _resolve_marker(
    spec: dict[str, Any],
    frame: pd.DataFrame,
    label: dict[str, Any] | None,
    line: dict[str, Any] | None,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    xmin, xmax = x_range
    ymin, ymax = y_range
    x_span = xmax - xmin
    y_span = ymax - ymin
    label_value = _numeric_value((label or {}).get("text"))
    requested_x = _finite((label or {}).get("anchor_x", (label or {}).get("x")))
    if requested_x is None:
        requested_x = label_value
    peak = _data_peak(spec, frame, requested_x)
    anchor_x = peak[0] if peak else requested_x
    if anchor_x is None and line:
        x1, x2 = _finite(line.get("x1")), _finite(line.get("x2"))
        if x1 is not None and x2 is not None:
            anchor_x = (x1 + x2) / 2
    if anchor_x is None:
        anchor_x = xmin + x_span / 2
    anchor_x = _clamp(anchor_x, xmin, xmax)
    peak_y = peak[1] if peak else None
    if peak_y is None:
        peak_y = _finite((label or {}).get("anchor_y"))
    if peak_y is None:
        peak_y = ymin + 0.8 * y_span
    peak_y = _clamp(peak_y, ymin, ymax)

    resolved_line: dict[str, Any] | None = deepcopy(line) if line else None
    if resolved_line is not None:
        old_x1, old_x2 = _finite(resolved_line.get("x1")), _finite(resolved_line.get("x2"))
        old_span = abs(old_x2 - old_x1) if old_x1 is not None and old_x2 is not None else 0.0
        span_fraction = _finite(resolved_line.get("span_x_fraction"))
        if span_fraction is None:
            span_fraction = old_span / x_span if old_span > 0 else 0.10
        span_fraction = _clamp(span_fraction, 0.04, 0.24)
        marker_y = _finite(resolved_line.get("anchor_y"))
        if marker_y is None:
            offset = _finite(resolved_line.get("offset_y_fraction"))
            offset = 0.04 if offset is None else _clamp(offset, -0.05, 0.20)
            marker_y = peak_y + offset * y_span
        # Leave breathing room for the label above the line and keep both
        # objects inside the layer. This is data-relative, so it follows a new
        # dataset instead of replaying a screenshot's absolute Y coordinate.
        marker_y = _clamp(marker_y, ymin + 0.04 * y_span, ymax - 0.10 * y_span)
        resolved_line.update(
            {
                "role": "peak_marker",
                "coordinate_system": "data",
                "anchor_x": round(anchor_x, 9),
                "anchor_y": round(marker_y, 9),
                "x1": round(anchor_x - span_fraction * x_span / 2, 9),
                "x2": round(anchor_x + span_fraction * x_span / 2, 9),
                "y1": round(marker_y, 9),
                "y2": round(marker_y, 9),
                "span_x_fraction": round(span_fraction, 9),
            }
        )

    resolved_label: dict[str, Any] | None = deepcopy(label) if label else None
    if resolved_label is not None:
        line_y = resolved_line.get("anchor_y") if resolved_line else None
        line_y = _finite(line_y)
        if line_y is None:
            line_y = _clamp(peak_y + 0.04 * y_span, ymin, ymax - 0.10 * y_span)
        offset = _finite(resolved_label.get("offset_y_fraction"))
        offset = 0.035 if offset is None else _clamp(offset, 0.01, 0.12)
        label_y = _clamp(line_y + offset * y_span, ymin + 0.02 * y_span, ymax - 0.025 * y_span)
        resolved_label.update(
            {
                "role": "peak_value",
                "coordinate_system": "data",
                "align": "center",
                "anchor_x": round(anchor_x, 9),
                "x": round(anchor_x, 9),
                "y": round(label_y, 9),
                "anchor_y": round(peak_y, 9),
            }
        )
    return resolved_label, resolved_line


def resolve_annotations(plot_spec: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    """Return a copy with peak markers tied to the supplied data coordinates."""
    spec = deepcopy(plot_spec)
    annotations = spec.setdefault("annotations", {}) or {}
    if not isinstance(annotations, dict):
        return spec
    labels = annotations.get("text_labels", annotations.get("labels", []))
    if not labels and annotations.get("peak_label") is not None:
        labels = [
            {
                "text": annotations.get("peak_label"),
                "x": annotations.get("peak_x"),
                "y": annotations.get("peak_y"),
                "font_size_pt": annotations.get("font_size_pt"),
                # The compact form is explicitly a peak callout.  Do not let
                # ordinary labels (for example ``*`` or ``P = ...``) enter
                # the data-relative peak resolver by accident.
                "role": "peak_label",
            }
        ]
    lines = annotations.get("lines", [])
    if not isinstance(labels, list):
        labels = []
    if not isinstance(lines, list):
        lines = []
    x_range = _axis_range(spec, frame, "x")
    y_range = _axis_range(spec, frame, "y")
    if not x_range or not y_range:
        return spec

    # Only an explicit semantic role opts an annotation into peak resolution.
    # A horizontal line next to a text label is commonly a significance
    # bracket or a guide line; treating every such line as a peak marker moves
    # the author's coordinates to an unrelated data maximum.
    marker_lines = [
        item for item in lines
        if isinstance(item, dict)
        and str(item.get("role", "")).lower() in _PEAK_LINE_ROLES
    ]
    peak_labels = [
        item for item in labels
        if isinstance(item, dict)
        and str(item.get("role", "")).lower() in _PEAK_LABEL_ROLES
    ]
    if not marker_lines and not peak_labels:
        return spec

    primary_label = peak_labels[0] if peak_labels else None
    primary_line = marker_lines[0] if marker_lines else None
    resolved_label, resolved_line = _resolve_marker(spec, frame, primary_label, primary_line, x_range, y_range)
    if resolved_label is not None and primary_label is not None:
        index = labels.index(primary_label)
        labels[index] = resolved_label
    if resolved_line is not None and primary_line is not None:
        index = lines.index(primary_line)
        lines[index] = resolved_line
    annotations["text_labels"] = labels
    annotations.pop("labels", None)
    annotations["lines"] = lines
    annotations["resolution"] = {
        "policy": "data_relative_peak_marker",
        "label_alignment": "center",
        "source": "supplied_data_and_axis_ranges",
    }
    spec["annotations"] = annotations
    return spec

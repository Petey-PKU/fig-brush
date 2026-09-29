"""Resolve an editable physical page using tick text as the size anchor.

Reference measurements are ratios, never screenshot DPI.  The 0.72 glyph/em
factor is an approximation for numeric tick glyphs, not an exact font match.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


def _positive(value: Any, default: float) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else default
    except (TypeError, ValueError):
        return default


def resolve_layout(plot_spec: dict[str, Any]) -> dict[str, Any]:
    """Return an idempotent copy; do not mutate caller data or coordinate values."""
    spec = deepcopy(plot_spec)
    style = spec.setdefault("style", {})
    axes = spec.setdefault("axes", {})
    target = _positive(style.get("base_font_pt"), 12.0)
    current = _positive(style.get("tick_label_font_pt"), target)
    scale = target / current
    aspect = _positive(style.get("page_aspect_ratio", style.get("canvas_aspect_ratio")), 4 / 3)
    frame = style.setdefault("plot_frame", style.get("frame") or {
        "left": 18.0, "top": 12.0, "right": 12.0, "bottom": 18.0,
    })
    for key in ("left", "top", "right", "bottom"):
        if key not in frame:
            raise ValueError(f"plot_frame requires {key} as a percentage of the page.")
    fraction = 1 - (float(frame["top"]) + float(frame["bottom"])) / 100
    if fraction <= 0 or float(frame["left"]) + float(frame["right"]) >= 100:
        raise ValueError("Plot-frame margins leave no area for the graph.")

    # Prefer a measurement of tick glyphs, then the earlier general text hint.
    # If no reliable ratio is available, use a clearly recorded layout fallback.
    ratio = _positive(style.get("tick_label_height_ratio"), 0)
    source = "reference_tick_glyphs"
    if not ratio:
        ratio = _positive(style.get("estimated_text_height_ratio"), 0)
        source = "reference_text_estimate"
    if not ratio:
        ratio = 0.04
        source = "fallback_ratio"
    glyph_fraction = _positive(style.get("tick_glyph_em_ratio"), 0.72)
    height_pt = target * glyph_fraction / ratio / fraction
    raw_width_mm = height_pt * aspect * 25.4 / 72
    # A screenshot can be exported at arbitrary DPI.  Keep the ratio-derived
    # size, but cap it to a practical editable Origin page so the file is not
    # an unwieldy poster when the reference glyph detector underestimates text.
    min_width_mm = _positive(style.get("min_page_width_mm"), 180.0)
    max_width_mm = _positive(style.get("max_page_width_mm"), 360.0)
    if max_width_mm < min_width_mm:
        max_width_mm = min_width_mm
    width_mm = min(max(raw_width_mm, min_width_mm), max_width_mm)
    height_mm = width_mm / aspect

    style["base_font_pt"] = target
    style["tick_label_font_pt"] = target
    style["axis_title_font_pt"] = round(_positive(style.get("axis_title_font_pt"), current) * scale, 6)
    style["page_aspect_ratio"] = aspect
    style["page_width_mm"] = round(width_mm, 6)
    style["page_height_mm"] = round(height_mm, 6)
    style.setdefault("preview_width_px", 1600)
    # Save a useful initial Origin viewport zoom.  This controls on-screen
    # editing only; it does not change the physical page size or export scale.
    page_width_px = width_mm / 25.4 * 96
    page_height_px = height_mm / 25.4 * 96
    viewport_width = _positive(style.get("open_viewport_width_px"), 1100.0)
    viewport_height = _positive(style.get("open_viewport_height_px"), 700.0)
    fit_zoom = min(viewport_width / page_width_px, viewport_height / page_height_px) * 100
    # Origin's page zoom is capped at 100 on the supported versions. Use that
    # maximum by default so a physical-size page does not reopen as a tiny
    # thumbnail; callers can still provide a lower open_zoom_percent.
    requested_zoom = _positive(style.get("open_zoom_percent"), 100.0)
    style["open_zoom_percent"] = round(
        min(100.0, max(50.0, requested_zoom)), 1
    )
    style.setdefault("open_window_state", 3)
    style.setdefault("open_viewmode", 2)
    # Convert absolute drawing sizes together, leaving relative/coordinate
    # positions unchanged. On a second call current == target, so scale == 1.
    for key in ("line_width", "symbol_size", "axis_line_width", "tick_line_width",
                "major_tick_length", "minor_tick_length"):
        if key in style:
            style[key] = round(float(style[key]) * scale, 6)
    for name in ("x", "y"):
        axis = axes.setdefault(name, {})
        axis["tick_label_font_pt"] = target
        if "title_font_pt" in axis:
            axis["title_font_pt"] = round(float(axis["title_font_pt"]) * scale, 6)
        for key in ("axis_line_width", "tick_line_width", "major_tick_length", "minor_tick_length"):
            if key in axis:
                axis[key] = round(float(axis[key]) * scale, 6)
    legend = spec.setdefault("legend", {})
    legend["font_size_pt"] = round(_positive(legend.get("font_size_pt"), current) * scale, 6)
    annotations = spec.setdefault("annotations", {})
    if "peak_label" in annotations:
        annotations["font_size_pt"] = round(_positive(annotations.get("font_size_pt"), current) * scale, 6)
    for key in ("text_labels", "labels"):
        labels = annotations.get(key, [])
        if not isinstance(labels, list):
            continue
        for label in labels:
            if not isinstance(label, dict):
                continue
            label["font_size_pt"] = round(_positive(label.get("font_size_pt"), current) * scale, 6)
    lines = annotations.get("lines", [])
    if not isinstance(lines, list):
        lines = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        if "line_width" in line:
            line["line_width"] = round(float(line["line_width"]) * scale, 6)
    spec["layout_resolution"] = {
        "policy": "tick_font_anchor", "base_font_pt": target,
        "measurement_source": source, "tick_height_to_frame": ratio,
        "glyph_height_to_em": glyph_fraction,
        "page_width_mm": style["page_width_mm"], "page_height_mm": style["page_height_mm"],
        "raw_page_width_mm": round(raw_width_mm, 6),
        "page_width_clamped": abs(width_mm - raw_width_mm) > 1e-6,
        "open_zoom_percent": style["open_zoom_percent"],
        "open_window_state": style["open_window_state"],
        "open_viewmode": style["open_viewmode"],
        "open_viewport_px": {"width": viewport_width, "height": viewport_height},
        "fit_zoom_percent": round(fit_zoom, 1),
        "formula": "height_pt = font_pt * glyph_height_to_em / tick_height_to_frame / frame_height_fraction",
        "approximate": True,
    }
    return spec

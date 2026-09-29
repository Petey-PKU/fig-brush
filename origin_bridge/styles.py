from __future__ import annotations

from typing import Any

from .text_layout import TextLayout, layout_text_label, normalize_origin_markup, text_value


def _set_if_possible(obj: Any, attribute: str, value: Any, integer: bool = False) -> bool:
    """Set an Origin property without making an older Origin version fatal."""
    if value is None:
        return False
    try:
        # String and enum-like Origin properties (for example plot colors and
        # line styles) must be assigned directly.  Calling set_float() on a
        # color silently drops the value on some originpro versions.
        if isinstance(value, str) and not integer:
            setattr(obj, attribute, value)
            return True
        method = getattr(obj, "set_int" if integer else "set_float", None)
        if callable(method):
            method(attribute, int(value) if integer else float(value))
        else:
            setattr(obj, attribute, int(value) if integer else value)
        return True
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
        return False


def _set_axis_property(layer: Any, axis_name: str, property_name: str, value: Any, integer: bool = False) -> bool:
    return _set_if_possible(layer, f"{axis_name}.{property_name}", value, integer=integer)


def _apply_label_font(layer: Any, label_name: str, point_size: Any) -> bool:
    if point_size is None:
        return False
    try:
        label = layer.label(label_name)
        return bool(label and _set_if_possible(label, "fsize", point_size))
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
        return False


def apply_page_style(page: Any, style: dict[str, Any]) -> list[str]:
    """Set page dimensions from the reference canvas aspect ratio."""
    applied: list[str] = []
    ratio = style.get("page_aspect_ratio") or style.get("canvas_aspect_ratio")
    if ratio is None:
        return applied
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        return applied
    if ratio <= 0:
        return applied
    width_mm = style.get("page_width_mm")
    height_mm = style.get("page_height_mm")
    use_physical = width_mm is not None and height_mm is not None
    if use_physical:
        # page.width/page.height are stored in dots even when page.unit is set
        # to millimetres. Convert the requested physical size using the fixed
        # 96 dpi export basis before writing those properties.
        width = int(round(float(width_mm) / 25.4 * 96))
        height = int(round(float(height_mm) / 25.4 * 96))
    else:
        width = int(style.get("page_width_px", 1200))
        height = max(1, int(round(width / ratio)))
    # Prevent Origin from replacing the requested pixel resolution with the
    # active printer's default (often 600 dpi), which makes 8 pt labels render
    # six times larger in an exported preview.
    for prop, value in (("updatetoprinter", 0), ("kar", 0), ("unit", 3 if use_physical else 4)):
        if _set_if_possible(page, prop, value, integer=True):
            applied.append(f"page.{prop}")
    for prop, value in (("width", width), ("height", height)):
        if _set_if_possible(page, prop, value, integer=not use_physical):
            applied.append(f"page.{prop}")
    for prop, value in (("resx", 96), ("resy", 96)):
        if _set_if_possible(page, prop, value, integer=True):
            applied.append(f"page.{prop}")
    # ``page.zoom`` is the on-screen graph-page magnification, independent of
    # exported pixels. Leaving it at an Origin template default (often 14%)
    # opens a valid project as a tiny thumbnail in a large blank window.
    # Reference-sized pages should open at the whole-page 100% view unless a
    # caller measured a different preferred UI zoom.
    zoom = style.get("open_zoom_percent", 100)
    if zoom is not None and _set_if_possible(page, "zoom", float(zoom)):
        applied.append("page.zoom")
    window_state = style.get("open_window_state", 3)
    if _set_if_possible(page, "win", window_state, integer=True):
        applied.append("page.win")
    if _set_if_possible(page, "viewmode", style.get("open_viewmode", 2), integer=True):
        applied.append("page.viewmode")
    # Keep the graph page active when the project is opened so the user lands
    # directly on the editable figure instead of a hidden/minimized page.
    if _set_if_possible(page, "active", 1, integer=True):
        applied.append("page.active")
    return applied


def apply_plot_style(plot: Any, style: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    if "color" in style or "line_color" in style:
        if _set_if_possible(plot, "color", style.get("color", style.get("line_color"))):
            applied.append("plot.color")
    if "line_width" in style:
        if _set_if_possible(plot, "line.width", style["line_width"]):
            applied.append("plot.line_width")
    if "line_style" in style:
        if _set_if_possible(plot, "line.style", style["line_style"], integer=True):
            applied.append("plot.line_style")
    if "symbol" in style:
        if _set_if_possible(plot, "symbol.kind", style["symbol"], integer=True):
            applied.append("plot.symbol")
    if "symbol_size" in style:
        if _set_if_possible(plot, "symbol.size", style["symbol_size"]):
            applied.append("plot.symbol_size")
    if "transparency" in style:
        if _set_if_possible(plot, "transparency", style["transparency"], integer=True):
            applied.append("plot.transparency")
    return applied


def _apply_axis(layer: Any, axis_name: str, axis_spec: dict[str, Any], style: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    axis = getattr(layer, "axis", lambda *_: None)(axis_name)
    if axis is None:
        return applied
    title = axis_spec.get("title")
    if title is not None:
        try:
            axis.title = normalize_origin_markup(title)
            applied.append(f"{axis_name}.title")
        except (AttributeError, TypeError, RuntimeError, OSError):
            pass
    begin = axis_spec.get("min", axis_spec.get("from"))
    end = axis_spec.get("max", axis_spec.get("to"))
    step = axis_spec.get("major_tick_increment", axis_spec.get("step"))
    if begin is not None or end is not None or step is not None:
        try:
            axis.set_limits(begin=begin, end=end, step=step)
            applied.append(f"{axis_name}.limits")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    # TemplateSpecs use the canonical ``scale: log10`` field, while older
    # PlotSpecs used a boolean ``log`` hint.  Honour both spellings and set a
    # linear scale explicitly when requested so a reused Origin template
    # cannot leak its previous logarithmic transform into this panel.
    scale_value = axis_spec.get("scale", style.get(f"{axis_name}_scale"))
    if scale_value is None and axis_spec.get("log"):
        scale_value = "log10"
    if isinstance(scale_value, str):
        scale_key = scale_value.strip().lower().replace("-", "_")
        if scale_key in {"log", "log10", "logarithmic"}:
            scale_value = "log10"
        elif scale_key in {"linear", "lin"}:
            scale_value = "linear"
        else:
            scale_value = None
    if scale_value in {"log10", "linear"}:
        try:
            axis.scale = scale_value
            applied.append(f"{axis_name}.scale")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass

    aliases = {
        "major_tick_count": ("majorTicks", True),
        "minor_tick_count": ("minorTicks", True),
        "major_ticks": ("majorTicks", True),
        "minor_ticks": ("minorTicks", True),
        "major_tick_length": ("ticklength", False),
        "minor_tick_length": ("mticklength", False),
        "major_tick_line_width": ("tickthickness", False),
        "minor_tick_line_width": ("mtickthickness", False),
        "axis_line_width": ("thickness", False),
        "tick_line_width": ("tickthickness", False),
        "tick_direction_value": ("ticks", True),
        "show_labels": ("showLabels", True),
        "show_opposite": ("showopposite", True),
        "grid": ("grid.show", True),
        "decimals": ("decPlaces", True),
        "first_tick": ("firstTick", False),
        "tick_label_rotation": ("label.rotate", False),
        # Origin expresses tick-label spacing as a percentage of the
        # current label font height.  Exposing both directions is necessary
        # for screenshot reconstruction because the default gap changes
        # with the physical export size.
        "tick_label_offset_h": ("label.offsetH", False),
        "tick_label_offset_v": ("label.offsetV", False),
        # Origin exposes tick-label point size as axis.label.pt.  labeln is a
        # separate label object in LabTalk and returns NaN on current Origin.
        "tick_label_font_pt": ("label.pt", False),
    }
    for key, (prop, integer) in aliases.items():
        value = axis_spec.get(key)
        if value is None:
            value = style.get(key)
        if value is not None and _set_axis_property(layer, axis_name, prop, value, integer=integer):
            applied.append(f"{axis_name}.{key}")

    # Origin may recalculate the increment when majorTicks is written. Reapply
    # an explicit numeric increment through Axis.sstep after all tick-count
    # properties so minor ticks have a real interval to subdivide.
    if step is not None:
        try:
            axis.sstep = float(step)
            applied.append(f"{axis_name}.major_tick_increment_final")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    # Origin templates can reset the tick subdivision when sstep is written.
    # Reapply both the visible tick bitmask and the minor count after the
    # final interval so small ticks survive plot attachment and save/reopen.
    axis_tick_direction = str(axis_spec.get("tick_direction", style.get("tick_direction", "out"))).lower()
    tick_value = {"out": 10, "in": 5, "both": 15, "none": 0}.get(axis_tick_direction)
    if tick_value is not None:
        try:
            axis.set_int("ticks", int(tick_value))
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    if axis_spec.get("major_tick_count", style.get("major_tick_count")) is not None:
        try:
            axis.set_int("majorTicks", int(axis_spec.get("major_tick_count", style.get("major_tick_count"))))
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    if axis_spec.get("minor_tick_count", style.get("minor_tick_count")) is not None:
        try:
            axis.set_int("minorTicks", int(axis_spec.get("minor_tick_count", style.get("minor_tick_count"))))
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    minor_count = axis_spec.get("minor_tick_count", style.get("minor_tick_count"))
    minor_width = axis_spec.get("minor_tick_line_width", style.get("minor_tick_line_width"))
    if minor_count is not None and float(minor_count) > 0 and minor_width is None:
        minor_width = style.get("tick_line_width", 0.9)
    if minor_width is not None and _set_axis_property(layer, axis_name, "mtickthickness", minor_width):
        applied.append(f"{axis_name}.minor_tick_line_width")

    title_font = axis_spec.get("title_font_pt", style.get("axis_title_font_pt"))
    label_name = {"x": "xb", "y": "yl"}.get(axis_name)
    if label_name and _apply_label_font(layer, label_name, title_font):
        applied.append(f"{axis_name}.title_font_pt")
    return applied


def apply_layer_style(layer: Any, spec: dict[str, Any]) -> list[str]:
    """Apply frame, axes, tick, and typography settings inferred from the reference."""
    applied: list[str] = []
    style = spec.get("style", {}) or {}
    frame = style.get("plot_frame") or style.get("frame") or {}
    if isinstance(frame, dict) and all(key in frame for key in ("left", "top", "right", "bottom")):
        left = float(frame["left"])
        top = float(frame["top"])
        right = float(frame["right"])
        bottom = float(frame["bottom"])
        for prop, value in (
            ("unit", 1),
            ("left", left),
            ("top", top),
            ("width", max(1.0, 100.0 - left - right)),
            ("height", max(1.0, 100.0 - top - bottom)),
        ):
            if _set_if_possible(layer, prop, value, integer=prop == "unit"):
                applied.append(f"layer.{prop}")

    sides = style.get("frame_sides") or {}
    if isinstance(sides, dict):
        def side_options(side: str) -> tuple[bool, dict[str, Any]]:
            value = sides.get(side)
            if isinstance(value, dict):
                return bool(value.get("show", value.get("visible", True))), value
            return bool(value), {}

        bottom, bottom_options = side_options("bottom")
        top, top_options = side_options("top")
        left, left_options = side_options("left")
        right, right_options = side_options("right")

        # showAxes controls which of the primary/opposite axis lines are
        # visible.  This is more faithful than only toggling showopposite:
        # references can omit the left/bottom axis as well as the top/right
        # frame, especially in inset and annotation panels.
        if any(side in sides for side in ("bottom", "top")):
            _set_axis_property(layer, "x", "showAxes", int(bottom) + (2 if top else 0), integer=True)
            applied.append("x.frame_sides")
        if any(side in sides for side in ("left", "right")):
            _set_axis_property(layer, "y", "showAxes", int(left) + (2 if right else 0), integer=True)
            applied.append("y.frame_sides")

        frame_width = style.get("frame_line_width", style.get("axis_line_width"))
        for axis_name, side, options in (
            ("x", "bottom", bottom_options), ("x2", "top", top_options),
            ("y", "left", left_options), ("y2", "right", right_options),
        ):
            visible, _ = side_options(side)
            if side not in sides or not visible:
                continue
            width = options.get("line_width", options.get("width", frame_width))
            if width is not None and _set_axis_property(layer, axis_name, "thickness", width):
                applied.append(f"{axis_name}.frame_line_width")
            color = options.get("color")
            if color is not None and _set_axis_property(layer, axis_name, "color", color):
                applied.append(f"{axis_name}.frame_color")
    tick_direction = style.get("tick_direction", "out")
    # Origin's ``ticks`` bitmask controls major and minor marks separately:
    # major-in=1, major-out=2, minor-in=4, minor-out=8.  The old mapping
    # used ``2`` for ``out``, which explicitly disabled every minor mark even
    # when ``minorTicks`` was set.  Include the corresponding minor bit so
    # the small marks are actually rendered in the editable Origin graph.
    tick_value = {"out": 10, "in": 5, "both": 15, "none": 0}.get(str(tick_direction).lower())
    if tick_value is not None:
        for axis_name in ("x", "y"):
            if _set_axis_property(layer, axis_name, "ticks", tick_value, integer=True):
                applied.append(f"{axis_name}.tick_direction")
    # A reference can have a four-sided frame while showing tick marks only on
    # the primary bottom/left axes.  Hide ticks on the opposite axes unless the
    # extracted style explicitly requests them.
    opposite_tick_direction = str(style.get("opposite_tick_direction", "none")).lower()
    opposite_tick_value = {"out": 10, "in": 5, "both": 15, "none": 0}.get(opposite_tick_direction, 0)
    if isinstance(sides, dict):
        if sides.get("top"):
            _set_axis_property(layer, "x2", "ticks", opposite_tick_value, integer=True)
            applied.append("x2.tick_direction")
        if sides.get("right"):
            _set_axis_property(layer, "y2", "ticks", opposite_tick_value, integer=True)
            applied.append("y2.tick_direction")

    axes = spec.get("axes", {}) or {}
    for axis_name in ("x", "y"):
        axis_spec = axes.get(axis_name, {}) or {}
        if isinstance(axis_spec, dict):
            applied.extend(_apply_axis(layer, axis_name, axis_spec, style))

    tick_font = style.get("tick_label_font_pt")
    if tick_font is None:
        ratio = style.get("estimated_text_height_ratio")
        if isinstance(ratio, (int, float)) and ratio > 0:
            # The reference detector measures rendered text height as a ratio
            # of the plot frame.  0.045 maps the common ~8 pt scientific label
            # to 8 pt while still adapting for unusually large/small labels.
            tick_font = max(6, min(14, round(8 * float(ratio) / 0.045, 1)))
    if tick_font is not None:
        for axis_name in ("x", "y"):
            if _set_axis_property(layer, axis_name, "label.pt", tick_font):
                applied.append(f"{axis_name}.tick_label_font_pt")

    title_font = style.get("axis_title_font_pt")
    if title_font is None and tick_font is not None:
        title_font = max(7, round(float(tick_font) * 1.05, 1))
    if title_font is not None:
        for label_name in ("xb", "yl"):
            if _apply_label_font(layer, label_name, title_font):
                applied.append(f"{label_name}.font_pt")

    legend = spec.get("legend", {}) or {}
    if isinstance(legend, dict) and legend.get("visible") is False:
        try:
            legend_label = layer.label("Legend")
            if legend_label is not None:
                legend_label.show = False
                applied.append("legend.hidden")
        except (AttributeError, TypeError, RuntimeError, OSError):
            pass
    return applied


def _annotation_space(item: dict[str, Any]) -> str:
    """Return the requested Origin attachment space for one annotation."""

    value = str(item.get("coordinate_system", item.get("coordinate_space", "data"))).lower()
    return "page" if value in {"page", "paper", "page_fraction", "page_fractions"} else "data"


def _line_style(line: Any, item: dict[str, Any]) -> None:
    """Apply the small, version-tolerant line style contract."""

    if item.get("line_width") is not None:
        line.width = float(item["line_width"])
    if item.get("color") is not None:
        line.color = item["color"]
    # Origin's native graph-object line exposes ``linetype`` as an integer.
    # Keep both spellings so model-authored specs can use the more readable
    # ``line_type`` while older fixtures continue to work.
    line_type = item.get("line_type", item.get("linetype"))
    if line_type is not None:
        try:
            line.set_int("linetype", int(line_type))
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    if item.get("arrow_end"):
        try:
            line.set_int("arrowendshape", int(item.get("arrow_end_shape", 2)))
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass
    if item.get("arrow_start"):
        try:
            line.set_int("arrowstartshape", int(item.get("arrow_start_shape", 2)))
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            pass


def _bracket_segments(item: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Expand one significance bracket into three ordinary line specs.

    Brackets are deliberately expanded before rendering so they remain
    editable graph objects in Origin.  ``x1``/``x2`` and ``y`` are the
    horizontal segment; ``stem_height`` is positive and points down in page
    coordinates or down in data space (towards smaller Y values).
    """

    try:
        x1 = float(item.get("x1", item.get("left")))
        x2 = float(item.get("x2", item.get("right")))
        y = float(item.get("y", item.get("y1")))
    except (TypeError, ValueError):
        return [], None
    coordinate_space = _annotation_space(item)
    stem_value = item.get("stem_height", item.get("stem_height_data", item.get("height")))
    try:
        stem = abs(float(stem_value)) if stem_value is not None else 0.0
    except (TypeError, ValueError):
        stem = 0.0
    stem_y = item.get("stem_y")
    if stem_y is None:
        # Page coordinates have a top-left origin. Data coordinates have an
        # upward Y axis, so both use a positive ``stem_height`` to point down.
        direction = 1.0 if coordinate_space == "page" else -1.0
        if str(item.get("stem_direction", "down")).lower() == "up":
            direction *= -1.0
        stem_y = y + direction * stem
    try:
        stem_y = float(stem_y)
    except (TypeError, ValueError):
        stem_y = y
    shared = {
        "coordinate_system": coordinate_space,
        "line_width": item.get("line_width"),
        "color": item.get("color"),
        "line_type": item.get("line_type", item.get("linetype")),
        "arrow_end": item.get("arrow_end", False),
        "arrow_start": item.get("arrow_start", False),
    }
    segments = [
        {**shared, "role": "significance_bracket_segment", "x1": x1, "y1": stem_y, "x2": x1, "y2": y},
        {**shared, "role": "significance_bracket_segment", "x1": x1, "y1": y, "x2": x2, "y2": y},
        {**shared, "role": "significance_bracket_segment", "x1": x2, "y1": y, "x2": x2, "y2": stem_y},
    ]
    label = None
    if item.get("text") is not None:
        offset = item.get("text_offset", 0.0)
        try:
            offset = abs(float(offset))
        except (TypeError, ValueError):
            offset = 0.0
        if item.get("text_x") is None:
            text_x = (x1 + x2) / 2.0
        else:
            text_x = float(item["text_x"])
        if item.get("text_y") is None:
            # Place text above the horizontal segment by default.
            text_y = y - offset if coordinate_space == "page" else y + offset
        else:
            text_y = float(item["text_y"])
        label = {
            "role": "significance_label",
            "text": item["text"],
            "x": text_x,
            "y": text_y,
            "coordinate_system": coordinate_space,
            "h_anchor": item.get("h_anchor", "center"),
            "v_anchor": item.get("v_anchor", "bottom" if coordinate_space == "data" else "bottom"),
            "font_size_pt": item.get("font_size_pt"),
            "color": item.get("text_color", item.get("color")),
            "rotate": item.get("rotate"),
            "paragraph_align": item.get("paragraph_align"),
        }
    return segments, label


def apply_annotations(layer: Any, annotations: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    annotations = annotations if isinstance(annotations, dict) else {}
    labels = annotations.get("text_labels", annotations.get("labels", []))
    # Keep compatibility with the compact peak annotation emitted by earlier
    # PlotSpec versions.  New multimodal extraction should prefer text_labels,
    # but old projects must continue to render their peak callout.
    if not labels and annotations.get("peak_label") is not None:
        labels = [{
            "text": annotations.get("peak_label"),
            "x": annotations.get("peak_x"),
            "y": annotations.get("peak_y"),
            "font_size_pt": annotations.get("font_size_pt"),
            "role": "peak_label",
        }]
    if not isinstance(labels, list):
        labels = []
    else:
        labels = list(labels)

    lines = annotations.get("lines", [])
    if not isinstance(lines, list):
        lines = []
    # Accept a semantic list as well as a single role-bearing item in
    # ``lines``.  Existing ordinary line annotations are left untouched.
    brackets = annotations.get("significance_brackets", annotations.get("brackets", []))
    if isinstance(brackets, dict):
        brackets = [brackets]
    if not isinstance(brackets, list):
        brackets = []
    brackets = [item for item in brackets if isinstance(item, dict)]
    bracket_line_items = [item for item in lines if isinstance(item, dict) and str(item.get("role", "")).lower() in {"significance_bracket", "bracket"}]
    lines = [item for item in lines if item not in bracket_line_items]
    for bracket in brackets + bracket_line_items:
        segments, label = _bracket_segments(bracket)
        lines.extend(segments)
        if label is not None:
            labels.append(label)

    for item in labels:
        if not isinstance(item, dict) or item.get("text") is None:
            continue
        try:
            coordinate_space = _annotation_space(item)
            x = item.get("x", item.get("x1"))
            y = item.get("y", item.get("y1"))
            if x is None or y is None:
                continue
            # ``add_label`` initially takes data coordinates on all supported
            # Origin versions.  Page-attached labels are moved to x1/y1 after
            # creation, so this path also works on older Origin builds.
            label = layer.add_label(text_value(item), x if coordinate_space == "data" else 0, y if coordinate_space == "data" else 0)
            if not label:
                continue
            anchor_name = str(item.get("anchor", item.get("text_anchor", ""))).lower()
            anchor_map = {
                "center": ("center", "middle"),
                "middle": ("center", "middle"),
                "top_left": ("left", "top"),
                "top_center": ("center", "top"),
                "top_right": ("right", "top"),
                "bottom_left": ("left", "bottom"),
                "bottom_center": ("center", "bottom"),
                "bottom_right": ("right", "bottom"),
            }
            mapped_h, mapped_v = anchor_map.get(anchor_name, (None, None))
            alignment = str(item.get("align", "")).lower()
            h_anchor = item.get("h_anchor") or mapped_h or (
                "center" if alignment in {"center", "middle"} else "right" if alignment == "right" else "left"
            )
            v_anchor = item.get("v_anchor") or mapped_v or (
                "middle" if alignment in {"center", "middle"} else "top"
            )
            if coordinate_space == "page" and item.get("size_fraction") is not None:
                try:
                    size_fraction = tuple(float(v) for v in item["size_fraction"][:2])
                except (TypeError, ValueError, IndexError):
                    size_fraction = None
            else:
                size_fraction = None
            label.set_int("attach", 1 if coordinate_space == "page" else 2)
            if item.get("font_size_pt") is not None:
                _set_if_possible(label, "fsize", item["font_size_pt"])
            if coordinate_space == "page":
                if size_fraction is not None:
                    layout_text_label(
                        label,
                        TextLayout(x=float(x), y=float(y), coordinate_space="page",
                                   h_anchor=h_anchor, v_anchor=v_anchor,
                                   paragraph_align=item.get("paragraph_align"),
                                   rotation=item.get("rotate"), font_size_pt=item.get("font_size_pt")),
                        size_fraction=size_fraction,
                    )
                else:
                    label.set_float("x1", float(x))
                    label.set_float("y1", float(y))
                    if item.get("rotate") is not None:
                        _set_if_possible(label, "rotate", item["rotate"])
                    # Once attached to the page Origin reports dx/dy in page
                    # fractions.  Apply explicit anchors with those measured
                    # dimensions so annotations survive export-size changes.
                    try:
                        dx = float(label.get_float("dx"))
                        dy = float(label.get_float("dy"))
                        label.set_float("x1", float(x) - (dx / 2 if h_anchor == "center" else dx if h_anchor == "right" else 0.0))
                        label.set_float("y1", float(y) - (dy / 2 if v_anchor == "middle" else dy if v_anchor == "bottom" else 0.0))
                    except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                        pass
            else:
                try:
                    layout_text_label(
                        label,
                        TextLayout(
                            x=float(x), y=float(y), coordinate_space="data",
                            h_anchor=h_anchor, v_anchor=v_anchor,
                            paragraph_align=item.get("paragraph_align"),
                            rotation=item.get("rotate"), font_size_pt=item.get("font_size_pt"),
                        ),
                    )
                except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                    # Keep older Origin versions usable if a label does not expose
                    # the measured geometry API.
                    if alignment in {"center", "middle", "right"}:
                        try:
                            dx = float(label.get_float("dx"))
                            dy = float(label.get_float("dy"))
                            if alignment in {"center", "middle"}:
                                label.set_float("x1", float(x) - dx / 2)
                                label.set_float("y1", float(y) + dy / 2)
                            else:
                                label.set_float("x1", float(x) - dx)
                        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                            pass
            if item.get("color") is not None:
                _set_if_possible(label, "color", item["color"], integer=True)
            applied.append("annotation.text")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            continue
    for item in lines:
        if not isinstance(item, dict):
            continue
        if not all(item.get(key) is not None for key in ("x1", "y1", "x2", "y2")):
            continue
        try:
            coordinate_space = _annotation_space(item)
            line = layer.add_line(item["x1"], item["y1"], item["x2"], item["y2"])
            if not line:
                continue
            line.set_int("attach", 1 if coordinate_space == "page" else 2)
            if coordinate_space == "page":
                line.set_float("x1", float(item["x1"]))
                line.set_float("y1", float(item["y1"]))
                line.set_float("x2", float(item["x2"]))
                line.set_float("y2", float(item["y2"]))
            _line_style(line, item)
            applied.append("annotation.line")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            continue
    return applied
